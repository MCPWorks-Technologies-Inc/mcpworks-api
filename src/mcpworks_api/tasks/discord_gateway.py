"""Discord bot gateway — bidirectional messaging for agents.

Runs as a background task in the API server lifespan. Polls the database
for agents with Discord channels that have bot_token configured, connects
to Discord via the bot gateway, and routes messages to chat_with_agent.

Multiple agents can share a single bot token (same bot, different channels)
or use separate bots.
"""

import asyncio
import contextlib
from collections import defaultdict

import discord
import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from mcpworks_api.core.database import get_db_context
from mcpworks_api.core.encryption import decrypt_value
from mcpworks_api.models.agent import AgentChannel

logger = structlog.get_logger(__name__)

RELOAD_INTERVAL_SECONDS = 60


class AgentBot(discord.Client):
    """A Discord client that routes messages to MCPWorks agents."""

    def __init__(self, bot_token: str, channel_map: dict[int, dict], **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents, **kwargs)
        self.bot_token = bot_token
        self.channel_map = channel_map
        self._ready_event = asyncio.Event()

    async def on_ready(self):
        logger.info(
            "discord_bot_connected",
            bot_user=str(self.user),
            channels=list(self.channel_map.keys()),
        )
        self._ready_event.set()

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        channel_id = message.channel.id
        if channel_id not in self.channel_map:
            return

        self._current_channel_id = channel_id
        agent_info = self.channel_map[channel_id]
        agent_name = agent_info["agent_name"]
        account_id = agent_info["account_id"]

        logger.info(
            "discord_message_received",
            agent_name=agent_name,
            channel_id=channel_id,
            author=str(message.author),
            message_length=len(message.content),
        )

        async with message.channel.typing():
            try:
                response = await self._route_to_agent(
                    account_id=account_id,
                    agent_name=agent_name,
                    user_message=message.content,
                    discord_context={
                        "author": str(message.author),
                        "author_id": str(message.author.id),
                        "channel": str(message.channel),
                    },
                )
            except Exception:
                logger.exception(
                    "discord_chat_error",
                    agent_name=agent_name,
                    channel_id=channel_id,
                )
                response = "Sorry, I encountered an error processing your message."

        for chunk in _split_message(response):
            await message.reply(chunk, mention_author=False)

    async def _route_to_agent(
        self,
        account_id: str,  # noqa: ARG002
        agent_name: str,
        user_message: str,
        discord_context: dict,
    ) -> str:
        import httpx

        chat_token = self.channel_map[self._current_channel_id]["chat_token"]
        if not chat_token:
            return (
                "Chat is not configured for this agent. Ask the admin to run configure_chat_token."
            )

        url = f"http://localhost:8000/chat/{chat_token}"
        message = f"[Discord message from {discord_context['author']}]: {user_message}"

        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(
                url,
                json={"message": message},
                headers={"Host": f"{agent_name}.agent.mcpworks.io"},
            )

        if resp.status_code != 200:
            logger.error(
                "discord_chat_http_error",
                agent_name=agent_name,
                status=resp.status_code,
                body=resp.text[:500],
            )
            return f"Error: chat returned status {resp.status_code}"

        data = resp.json()
        return data.get("response", data.get("error", "No response"))


def _split_message(text: str, limit: int = 2000) -> list[str]:
    """Split a message into chunks that fit Discord's 2000 char limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


async def _load_discord_channels() -> dict[str, list[dict]]:
    """Load all agents with Discord channels that have bot_token configured.

    Returns: {bot_token: [{agent_name, account_id, channel_id, webhook_url}]}
    """
    token_map: dict[str, list[dict]] = defaultdict(list)

    async with get_db_context() as db:
        result = await db.execute(
            select(AgentChannel)
            .where(
                AgentChannel.channel_type == "discord",
                AgentChannel.enabled.is_(True),
            )
            .options(selectinload(AgentChannel.agent))
        )
        channels = result.scalars().all()

        for channel in channels:
            agent = channel.agent
            if not agent or agent.status != "running":
                continue

            try:
                config = decrypt_value(channel.config_encrypted, channel.config_dek_encrypted)
            except Exception:
                logger.warning("discord_channel_decrypt_failed", agent_name=agent.name)
                continue

            if not isinstance(config, dict):
                continue

            bot_token = config.get("bot_token")
            channel_id = config.get("channel_id")
            if not bot_token or not channel_id:
                continue

            try:
                channel_id_int = int(channel_id)
            except (ValueError, TypeError):
                logger.warning(
                    "discord_invalid_channel_id",
                    agent_name=agent.name,
                    channel_id=channel_id,
                )
                continue

            token_map[bot_token].append(
                {
                    "agent_name": agent.name,
                    "account_id": str(agent.account_id),
                    "channel_id": channel_id_int,
                    "webhook_url": config.get("webhook_url"),
                    "chat_token": agent.chat_token,
                }
            )

    return dict(token_map)


async def run_discord_gateway():
    """Main gateway loop — manages Discord bot connections for all configured agents."""
    logger.info("discord_gateway_starting")

    active_bots: dict[str, tuple[AgentBot, asyncio.Task]] = {}

    try:
        while True:
            try:
                token_map = await _load_discord_channels()
            except Exception:
                logger.exception("discord_gateway_load_failed")
                await asyncio.sleep(RELOAD_INTERVAL_SECONDS)
                continue

            current_tokens = set(token_map.keys())
            active_tokens = set(active_bots.keys())

            for token in active_tokens - current_tokens:
                bot, task = active_bots.pop(token)
                logger.info("discord_bot_stopping", bot_user=str(bot.user))
                task.cancel()
                await bot.close()

            for token in current_tokens - active_tokens:
                entries = token_map[token]
                channel_map = {e["channel_id"]: e for e in entries}
                bot = AgentBot(bot_token=token, channel_map=channel_map)
                task = asyncio.create_task(_run_bot(bot, token))
                active_bots[token] = (bot, task)
                agent_names = [e["agent_name"] for e in entries]
                logger.info(
                    "discord_bot_starting",
                    agents=agent_names,
                    channels=list(channel_map.keys()),
                )

            for token in current_tokens & active_tokens:
                entries = token_map[token]
                new_channel_map = {e["channel_id"]: e for e in entries}
                bot, task = active_bots[token]
                bot.channel_map = new_channel_map

            if active_bots:
                logger.debug(
                    "discord_gateway_status",
                    bots=len(active_bots),
                    channels=sum(len(b.channel_map) for b, _ in active_bots.values()),
                )

            await asyncio.sleep(RELOAD_INTERVAL_SECONDS)

    except asyncio.CancelledError:
        logger.info("discord_gateway_shutting_down", bots=len(active_bots))
        for _token, (bot, task) in active_bots.items():
            task.cancel()
            with contextlib.suppress(Exception):
                await bot.close()
        raise


async def _run_bot(bot: AgentBot, token: str):
    """Run a single bot with automatic reconnection."""
    while True:
        try:
            await bot.start(token)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("discord_bot_crashed")
            await asyncio.sleep(5)
            logger.info("discord_bot_reconnecting")

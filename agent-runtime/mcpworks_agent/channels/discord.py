"""Discord channel integration for agent containers.

Provides a Discord bot client that can receive messages and dispatch them
to handler functions, and send messages back to Discord channels.

Configuration is injected via the channel config (encrypted at rest,
decrypted by the API and passed as environment variables or config dict).
"""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.environ.get("AGENT_DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID = os.environ.get("AGENT_DISCORD_GUILD_ID", "")


class DiscordChannelError(Exception):
    pass


class DiscordChannel:
    """Discord bot integration for an agent.

    Connects to Discord as a bot, listens for messages in configured channels,
    and dispatches them to the agent's handler function.

    Usage:
        config = {"bot_token": "...", "channel_ids": ["123456789"]}
        channel = DiscordChannel(config)
        await channel.start(on_message=my_handler)
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.bot_token = config.get("bot_token") or DISCORD_BOT_TOKEN
        self.channel_ids: list[str] = config.get("channel_ids", [])
        self.command_prefix: str = config.get("command_prefix", "!")
        self._client: Any = None

        if not self.bot_token:
            raise DiscordChannelError("Discord bot_token not configured")

    async def start(
        self,
        on_message: Callable[[dict[str, Any]], Awaitable[str | None]],
    ) -> None:
        """Start the Discord bot and listen for messages.

        Args:
            on_message: Async callback called with message data dict.
                        Return a string to reply, or None to skip.
        """
        try:
            import discord
        except ImportError:
            raise DiscordChannelError("discord.py not installed: pip install discord.py")

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready() -> None:
            logger.info("discord_bot_ready", user=str(client.user))

        @client.event
        async def on_message(message: discord.Message) -> None:
            if message.author == client.user:
                return

            if self.channel_ids and str(message.channel.id) not in self.channel_ids:
                return

            message_data = {
                "id": str(message.id),
                "channel_id": str(message.channel.id),
                "author_id": str(message.author.id),
                "author_name": str(message.author),
                "content": message.content,
                "guild_id": str(message.guild.id) if message.guild else None,
            }

            try:
                reply = await on_message(message_data)
                if reply:
                    await message.channel.send(reply)
            except Exception as e:
                logger.error(
                    "discord_message_handler_failed",
                    message_id=str(message.id),
                    error=str(e),
                )

        await client.start(self.bot_token)

    async def send_message(self, channel_id: str, content: str) -> None:
        """Send a message to a Discord channel.

        Args:
            channel_id: The Discord channel ID.
            content: The message content.
        """
        if not self._client:
            raise DiscordChannelError("Discord client not started")

        channel = self._client.get_channel(int(channel_id))
        if not channel:
            channel = await self._client.fetch_channel(int(channel_id))
        if channel:
            await channel.send(content)
        else:
            raise DiscordChannelError(f"Channel {channel_id} not found")

    def stop(self) -> None:
        """Stop the Discord bot client."""
        if self._client:
            asyncio.create_task(self._client.close())
            logger.info("discord_bot_stopped")

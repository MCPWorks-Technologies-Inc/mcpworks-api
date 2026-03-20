"""Agent service — container lifecycle, scheduling, state, cloning."""

import contextlib
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import docker
import structlog
from docker.errors import APIError as DockerAPIError
from docker.errors import NotFound as DockerNotFound
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mcpworks_api.core.encryption import decrypt_value, encrypt_value
from mcpworks_api.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from mcpworks_api.models.agent import (
    Agent,
    AgentChannel,
    AgentRun,
    AgentSchedule,
    AgentState,
    AgentWebhook,
)
from mcpworks_api.models.namespace import Namespace
from mcpworks_api.models.subscription import AGENT_TIER_CONFIG
from mcpworks_api.services.namespace import NamespaceServiceManager

logger = structlog.get_logger(__name__)

_UNSET = type("_UNSET", (), {"__repr__": lambda _self: "_UNSET"})()

AGENT_NETWORK_NAME = "mcpworks-agents"
AGENT_CONTAINER_PREFIX = "agent-"
AGENT_IMAGE = "mcpworks/agent-runtime:latest"


class AgentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._docker: docker.DockerClient | None = None

    @property
    def docker_client(self) -> docker.DockerClient:
        if self._docker is None:
            self._docker = docker.from_env()
        return self._docker

    def _ensure_network(self) -> None:
        try:
            self.docker_client.networks.get(AGENT_NETWORK_NAME)
        except DockerNotFound:
            self.docker_client.networks.create(
                AGENT_NETWORK_NAME, driver="bridge", check_duplicate=True
            )

    def _get_tier_config(self, tier: str) -> dict:
        config = AGENT_TIER_CONFIG.get(tier)
        if not config:
            raise ForbiddenError(f"Tier '{tier}' is not agent-enabled")
        return config

    async def get_agent_count(self, account_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(Agent.id)).where(Agent.account_id == account_id)
        )
        return result.scalar_one()

    async def create_agent(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID,  # noqa: ARG002 - reserved for audit logging
        tier: str,
        name: str,
        display_name: str | None = None,
    ) -> Agent:
        tier_config = self._get_tier_config(tier)
        current_count = await self.get_agent_count(account_id)
        if current_count >= tier_config["max_agents"]:
            raise ConflictError(
                f"Agent slot limit reached ({tier_config['max_agents']} for {tier})"
            )

        existing = await self.db.execute(
            select(Agent).where(Agent.account_id == account_id, Agent.name == name)
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Agent '{name}' already exists")

        ns_manager = NamespaceServiceManager(self.db)
        namespace = await ns_manager.create(account_id=account_id, name=name)

        agent = Agent(
            account_id=account_id,
            namespace_id=namespace.id,
            name=name,
            display_name=display_name,
            status="creating",
            memory_limit_mb=tier_config["memory_limit_mb"],
            cpu_limit=tier_config["cpu_limit"],
        )
        self.db.add(agent)
        await self.db.flush()
        await self.db.refresh(agent)

        try:
            self._ensure_network()
            container = self.docker_client.containers.run(
                AGENT_IMAGE,
                name=f"{AGENT_CONTAINER_PREFIX}{name}",
                detach=True,
                network=AGENT_NETWORK_NAME,
                mem_limit=f"{tier_config['memory_limit_mb']}m",
                nano_cpus=int(tier_config["cpu_limit"] * 1e9),
                environment={
                    "AGENT_NAME": name,
                    "AGENT_ID": str(agent.id),
                    "MCPWORKS_API_URL": "http://mcpworks-api:8000",
                },
                restart_policy={"Name": "unless-stopped"},
                read_only=True,
                tmpfs={"/tmp": "size=64m,noexec,nosuid"},
                cap_drop=["ALL"],
                cap_add=["NET_BIND_SERVICE"],
                security_opt=["no-new-privileges"],
                user="1000:1000",
            )
            agent.container_id = container.id
            agent.status = "running"
        except DockerAPIError as e:
            logger.error("agent_container_create_failed", agent=name, error=str(e))
            agent.status = "error"
            agent.container_id = None

        await self.db.flush()
        await self.db.refresh(agent)

        logger.info(
            "agent_created",
            agent_id=str(agent.id),
            agent_name=name,
            account_id=str(account_id),
            status=agent.status,
        )
        return agent

    async def get_agent(self, account_id: uuid.UUID, agent_name: str) -> Agent:
        result = await self.db.execute(
            select(Agent).where(Agent.account_id == account_id, Agent.name == agent_name)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise NotFoundError(f"Agent '{agent_name}' not found")
        return agent

    async def get_agent_by_id(self, account_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
        result = await self.db.execute(
            select(Agent).where(Agent.account_id == account_id, Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise NotFoundError("Agent not found")
        return agent

    async def list_agents(self, account_id: uuid.UUID) -> list[Agent]:
        result = await self.db.execute(
            select(Agent).where(Agent.account_id == account_id).order_by(Agent.created_at.desc())
        )
        return list(result.scalars().all())

    async def start_agent(self, account_id: uuid.UUID, agent_name: str) -> Agent:
        agent = await self.get_agent(account_id, agent_name)
        if agent.status not in ("stopped", "error"):
            raise ConflictError(f"Agent '{agent_name}' is {agent.status}, cannot start")

        if agent.container_id:
            try:
                container = self.docker_client.containers.get(agent.container_id)
                container.start()
                agent.status = "running"
            except DockerNotFound:
                agent.status = "error"
                agent.container_id = None
            except DockerAPIError as e:
                logger.error("agent_start_failed", agent=agent_name, error=str(e))
                agent.status = "error"
        else:
            agent.status = "error"

        await self.db.flush()
        logger.info("agent_started", agent_id=str(agent.id), status=agent.status)
        return agent

    async def stop_agent(self, account_id: uuid.UUID, agent_name: str) -> Agent:
        agent = await self.get_agent(account_id, agent_name)
        if agent.status != "running":
            raise ConflictError(f"Agent '{agent_name}' is {agent.status}, cannot stop")

        if agent.container_id:
            try:
                container = self.docker_client.containers.get(agent.container_id)
                container.stop(timeout=10)
                agent.status = "stopped"
            except DockerNotFound:
                agent.status = "stopped"
                agent.container_id = None
            except DockerAPIError as e:
                logger.error("agent_stop_failed", agent=agent_name, error=str(e))
                agent.status = "error"
        else:
            agent.status = "stopped"

        await self.db.flush()
        logger.info("agent_stopped", agent_id=str(agent.id), status=agent.status)
        return agent

    async def destroy_agent(self, account_id: uuid.UUID, agent_name: str) -> Agent:
        agent = await self.get_agent(account_id, agent_name)
        agent.status = "destroying"
        await self.db.flush()

        if agent.container_id:
            try:
                container = self.docker_client.containers.get(agent.container_id)
                container.remove(force=True)
            except DockerNotFound:
                pass
            except DockerAPIError as e:
                logger.error("agent_container_remove_failed", agent=agent_name, error=str(e))

        ns_result = await self.db.execute(
            select(Namespace).where(Namespace.id == agent.namespace_id)
        )
        namespace = ns_result.scalar_one_or_none()

        from mcpworks_api.scratchpad import get_scratchpad_backend

        try:
            scratchpad_backend = get_scratchpad_backend()
            await scratchpad_backend.delete_all(agent.id)
        except Exception as e:
            logger.warning("scratchpad_cleanup_failed", agent=agent_name, error=str(e))

        logger.info("agent_destroyed", agent_id=str(agent.id), agent_name=agent_name)

        await self.db.delete(agent)
        if namespace:
            await self.db.delete(namespace)
        await self.db.flush()
        return agent

    async def get_agent_slots(self, account_id: uuid.UUID, tier: str) -> dict:
        tier_config = self._get_tier_config(tier)
        used = await self.get_agent_count(account_id)
        return {
            "slots_used": used,
            "slots_total": tier_config["max_agents"],
            "slots_available": tier_config["max_agents"] - used,
            "tier": tier,
        }

    async def get_container_stats(self, agent: Agent) -> dict | None:
        if not agent.container_id:
            return None
        try:
            container = self.docker_client.containers.get(agent.container_id)
            stats = container.stats(stream=False)
            return {
                "status": container.status,
                "memory_usage_mb": round(
                    stats.get("memory_stats", {}).get("usage", 0) / (1024 * 1024), 1
                ),
                "memory_limit_mb": agent.memory_limit_mb,
                "cpu_percent": self._calc_cpu_percent(stats),
            }
        except (DockerNotFound, DockerAPIError):
            return None

    async def force_restart_agent(self, agent: Agent) -> Agent:
        if agent.container_id:
            try:
                container = self.docker_client.containers.get(agent.container_id)
                container.restart(timeout=10)
                agent.status = "running"
            except (DockerNotFound, DockerAPIError) as e:
                logger.error("agent_force_restart_failed", agent=agent.name, error=str(e))
                agent.status = "error"
        else:
            agent.status = "error"

        await self.db.flush()
        logger.info("agent_force_restarted", agent_id=str(agent.id), status=agent.status)
        return agent

    @staticmethod
    def _calc_cpu_percent(stats: dict) -> float:
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})
        cpu_delta = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - precpu_stats.get(
            "cpu_usage", {}
        ).get("total_usage", 0)
        system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get(
            "system_cpu_usage", 0
        )
        if system_delta > 0 and cpu_delta > 0:
            num_cpus = len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", [1]))
            return round((cpu_delta / system_delta) * num_cpus * 100.0, 2)
        return 0.0

    @staticmethod
    def _cron_min_interval_seconds(cron_expression: str) -> int:
        """Estimate minimum interval in seconds for a cron expression.

        Only inspects the minutes field to derive the minimum repeat interval.
        Returns 60 for per-minute, 3600 for hourly, etc.
        """
        parts = cron_expression.strip().split()
        if len(parts) < 5:
            return 60
        minutes_field = parts[0]
        if minutes_field == "*":
            return 60
        if minutes_field.startswith("*/"):
            try:
                step = int(minutes_field[2:])
                return step * 60
            except ValueError:
                return 60
        hours_field = parts[1] if len(parts) > 1 else "*"
        if hours_field == "*":
            return 60
        if hours_field.startswith("*/"):
            try:
                step = int(hours_field[2:])
                return step * 3600
            except ValueError:
                return 3600
        return 3600

    async def add_schedule(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        function_name: str,
        cron_expression: str,
        timezone: str,
        failure_policy: dict,
        tier: str,
        orchestration_mode: str = "direct",
    ) -> AgentSchedule:
        agent = await self.get_agent(account_id, agent_name)
        tier_config = self._get_tier_config(tier)
        min_seconds = self._cron_min_interval_seconds(cron_expression)
        if min_seconds < tier_config["min_schedule_seconds"]:
            raise ForbiddenError(
                f"Minimum schedule interval for {tier} is {tier_config['min_schedule_seconds']}s; "
                f"cron expression resolves to {min_seconds}s"
            )
        from mcpworks_api.tasks.scheduler import _compute_next_run

        schedule = AgentSchedule(
            agent_id=agent.id,
            function_name=function_name,
            cron_expression=cron_expression,
            timezone=timezone,
            failure_policy=failure_policy,
            orchestration_mode=orchestration_mode,
            enabled=True,
            consecutive_failures=0,
            next_run_at=_compute_next_run(cron_expression, timezone),
        )
        self.db.add(schedule)
        await self.db.flush()
        await self.db.refresh(schedule)
        logger.info(
            "agent_schedule_added",
            agent_id=str(agent.id),
            schedule_id=str(schedule.id),
            cron_expression=cron_expression,
        )
        return schedule

    async def remove_schedule(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        schedule_id: uuid.UUID,
    ) -> None:
        agent = await self.get_agent(account_id, agent_name)
        result = await self.db.execute(
            select(AgentSchedule).where(
                AgentSchedule.id == schedule_id,
                AgentSchedule.agent_id == agent.id,
            )
        )
        schedule = result.scalar_one_or_none()
        if not schedule:
            raise NotFoundError(f"Schedule '{schedule_id}' not found")
        await self.db.delete(schedule)
        await self.db.flush()
        logger.info("agent_schedule_removed", schedule_id=str(schedule_id))

    async def list_schedules(
        self,
        account_id: uuid.UUID,
        agent_name: str,
    ) -> list[AgentSchedule]:
        agent = await self.get_agent(account_id, agent_name)
        result = await self.db.execute(
            select(AgentSchedule)
            .where(AgentSchedule.agent_id == agent.id)
            .order_by(AgentSchedule.created_at)
        )
        return list(result.scalars().all())

    async def list_runs(
        self,
        account_id: uuid.UUID,
        agent_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AgentRun], int]:
        agent = await self.get_agent_by_id(account_id, agent_id)
        total_result = await self.db.execute(
            select(func.count(AgentRun.id)).where(AgentRun.agent_id == agent.id)
        )
        total = total_result.scalar_one()
        result = await self.db.execute(
            select(AgentRun)
            .where(AgentRun.agent_id == agent.id)
            .order_by(AgentRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def add_webhook(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        path: str,
        handler_function_name: str,
        secret: str | None = None,
        orchestration_mode: str = "direct",
    ) -> AgentWebhook:
        agent = await self.get_agent(account_id, agent_name)
        existing = await self.db.execute(
            select(AgentWebhook).where(
                AgentWebhook.agent_id == agent.id,
                AgentWebhook.path == path,
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Webhook path '{path}' already exists for agent '{agent_name}'")

        secret_hash: str | None = None
        if secret:
            secret_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()

        webhook = AgentWebhook(
            agent_id=agent.id,
            path=path,
            handler_function_name=handler_function_name,
            secret_hash=secret_hash,
            orchestration_mode=orchestration_mode,
            enabled=True,
        )
        self.db.add(webhook)
        await self.db.flush()
        await self.db.refresh(webhook)
        logger.info(
            "agent_webhook_added",
            agent_id=str(agent.id),
            webhook_id=str(webhook.id),
            path=path,
        )
        return webhook

    async def remove_webhook(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        webhook_id: uuid.UUID,
    ) -> None:
        agent = await self.get_agent(account_id, agent_name)
        result = await self.db.execute(
            select(AgentWebhook).where(
                AgentWebhook.id == webhook_id,
                AgentWebhook.agent_id == agent.id,
            )
        )
        webhook = result.scalar_one_or_none()
        if not webhook:
            raise NotFoundError(f"Webhook '{webhook_id}' not found")
        await self.db.delete(webhook)
        await self.db.flush()
        logger.info("agent_webhook_removed", webhook_id=str(webhook_id))

    async def list_webhooks(
        self,
        account_id: uuid.UUID,
        agent_name: str,
    ) -> list[AgentWebhook]:
        agent = await self.get_agent(account_id, agent_name)
        result = await self.db.execute(
            select(AgentWebhook)
            .where(AgentWebhook.agent_id == agent.id)
            .order_by(AgentWebhook.created_at)
        )
        return list(result.scalars().all())

    async def resolve_webhook(
        self,
        agent_name: str,
        path: str,
    ) -> AgentWebhook | None:
        result = await self.db.execute(
            select(AgentWebhook)
            .join(Agent, AgentWebhook.agent_id == Agent.id)
            .where(
                Agent.name == agent_name,
                AgentWebhook.path == path,
                AgentWebhook.enabled.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def set_state(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        key: str,
        value: Any,
        tier: str,
    ) -> AgentState:
        agent = await self.get_agent(account_id, agent_name)
        tier_config = self._get_tier_config(tier)

        serialized = json.dumps(value).encode("utf-8")
        size_bytes = len(serialized)

        total_size_result = await self.db.execute(
            select(func.sum(AgentState.size_bytes)).where(AgentState.agent_id == agent.id)
        )
        current_total = total_size_result.scalar_one() or 0

        existing_result = await self.db.execute(
            select(AgentState).where(
                AgentState.agent_id == agent.id,
                AgentState.key == key,
            )
        )
        existing = existing_result.scalar_one_or_none()
        existing_size = existing.size_bytes if existing else 0

        projected_total = current_total - existing_size + size_bytes
        if projected_total > tier_config["max_state_bytes"]:
            raise ForbiddenError(
                f"State size limit exceeded: {projected_total} bytes > "
                f"{tier_config['max_state_bytes']} bytes for {tier}"
            )

        ciphertext, encrypted_dek = encrypt_value(value)

        if existing:
            existing.value_encrypted = ciphertext
            existing.value_dek_encrypted = encrypted_dek
            existing.size_bytes = size_bytes
            existing.updated_at = datetime.now(tz=UTC)
            state_entry = existing
        else:
            state_entry = AgentState(
                agent_id=agent.id,
                key=key,
                value_encrypted=ciphertext,
                value_dek_encrypted=encrypted_dek,
                size_bytes=size_bytes,
            )
            self.db.add(state_entry)

        await self.db.flush()
        return state_entry

    async def get_state(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        key: str,
    ) -> tuple[Any, AgentState]:
        agent = await self.get_agent(account_id, agent_name)
        result = await self.db.execute(
            select(AgentState).where(
                AgentState.agent_id == agent.id,
                AgentState.key == key,
            )
        )
        state_entry = result.scalar_one_or_none()
        if not state_entry:
            raise NotFoundError(f"State key '{key}' not found")
        value = decrypt_value(state_entry.value_encrypted, state_entry.value_dek_encrypted)
        return value, state_entry

    async def delete_state(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        key: str,
    ) -> None:
        agent = await self.get_agent(account_id, agent_name)
        result = await self.db.execute(
            select(AgentState).where(
                AgentState.agent_id == agent.id,
                AgentState.key == key,
            )
        )
        state_entry = result.scalar_one_or_none()
        if not state_entry:
            raise NotFoundError(f"State key '{key}' not found")
        await self.db.delete(state_entry)
        await self.db.flush()

    async def list_state_keys(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        tier: str,
    ) -> dict:
        agent = await self.get_agent(account_id, agent_name)
        tier_config = self._get_tier_config(tier)
        result = await self.db.execute(
            select(AgentState.key, AgentState.size_bytes)
            .where(AgentState.agent_id == agent.id)
            .order_by(AgentState.key)
        )
        rows = result.all()
        total_size = sum(r.size_bytes for r in rows)
        return {
            "keys": [r.key for r in rows],
            "total_size_bytes": total_size,
            "max_size_bytes": tier_config["max_state_bytes"],
        }

    async def get_all_state(self, agent_id: uuid.UUID) -> dict[str, Any]:
        result = await self.db.execute(select(AgentState).where(AgentState.agent_id == agent_id))
        state_entries = result.scalars().all()
        state = {}
        for entry in state_entries:
            with contextlib.suppress(Exception):
                state[entry.key] = decrypt_value(entry.value_encrypted, entry.value_dek_encrypted)
        return state

    async def configure_ai(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        engine: str,
        model: str,
        api_key: str | None = None,
        system_prompt=_UNSET,
        auto_channel=_UNSET,
    ) -> Agent:
        agent = await self.get_agent(account_id, agent_name)

        if api_key:
            await self._validate_api_key(engine, model, api_key)
            ciphertext, encrypted_dek = encrypt_value(api_key)
            agent.ai_api_key_encrypted = ciphertext
            agent.ai_api_key_dek_encrypted = encrypted_dek

        agent.ai_engine = engine
        agent.ai_model = model
        if system_prompt is not _UNSET:
            agent.system_prompt = system_prompt
        if auto_channel is not _UNSET:
            agent.auto_channel = auto_channel

        await self.db.flush()
        await self.db.refresh(agent)
        logger.info("agent_ai_configured", agent_id=str(agent.id), engine=engine, model=model)
        return agent

    @staticmethod
    async def _validate_api_key(engine: str, model: str, api_key: str) -> None:  # noqa: ARG004
        """Validate an API key by making a lightweight test call before saving."""
        import httpx

        engine_urls = {
            "openrouter": "https://openrouter.ai/api/v1/models",
            "openai": "https://api.openai.com/v1/models",
            "anthropic": "https://api.anthropic.com/v1/models",
            "google": None,
        }
        test_url = engine_urls.get(engine)
        if not test_url:
            return

        headers = {"Authorization": f"Bearer {api_key}"}
        if engine == "anthropic":
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(test_url, headers=headers)
            if resp.status_code == 401:
                raise ValueError(
                    f"API key validation failed: {engine} returned 401 Unauthorized. "
                    "The key is invalid or expired. The previous key has NOT been overwritten."
                )
            if resp.status_code == 403:
                raise ValueError(
                    f"API key validation failed: {engine} returned 403 Forbidden. "
                    "The key may lack required permissions."
                )
        except httpx.RequestError as e:
            logger.warning("api_key_validation_network_error", engine=engine, error=str(e)[:200])

    async def remove_ai(
        self,
        account_id: uuid.UUID,
        agent_name: str,
    ) -> Agent:
        agent = await self.get_agent(account_id, agent_name)
        agent.ai_engine = None
        agent.ai_model = None
        agent.ai_api_key_encrypted = None
        agent.ai_api_key_dek_encrypted = None
        agent.system_prompt = None
        await self.db.flush()
        await self.db.refresh(agent)
        logger.info("agent_ai_removed", agent_id=str(agent.id))
        return agent

    async def chat_with_agent(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        message: str,
        account: Any = None,
        *,
        public_only: bool = False,
    ) -> str:
        from mcpworks_api.core.ai_client import AIClientError, chat_with_tools
        from mcpworks_api.core.ai_tools import augment_system_prompt, build_tool_definitions
        from mcpworks_api.core.mcp_client import McpServerPool

        agent = await self.get_agent(account_id, agent_name)
        if not agent.ai_engine or not agent.ai_api_key_encrypted:
            raise NotFoundError("Agent has no AI engine configured")

        api_key = decrypt_value(agent.ai_api_key_encrypted, agent.ai_api_key_dek_encrypted)

        tools = await build_tool_definitions(agent.namespace_id, self.db, public_only=public_only)
        agent_state = await self.get_all_state(agent.id)

        mcp_pool: McpServerPool | None = None
        if agent.mcp_servers:
            try:
                mcp_pool = McpServerPool(agent.mcp_servers)
                await mcp_pool.__aenter__()
                tools.extend(mcp_pool.get_tool_definitions())
            except Exception:
                logger.exception("chat_mcp_pool_failed", agent_name=agent.name)
                mcp_pool = None

        import uuid as uuid_mod

        from mcpworks_api.core.conversation_memory import (
            build_history_messages,
            load_history,
        )
        from mcpworks_api.core.telemetry import make_event, telemetry_bus

        effective_system_prompt = augment_system_prompt(agent.system_prompt, tools)

        # Load conversation history and prepend to messages
        summary, history_turns = load_history(agent_state)
        history_messages = build_history_messages(summary, history_turns)
        messages: list[dict] = history_messages + [{"role": "user", "content": message}]

        chat_limits = self._resolve_chat_limits(agent)
        max_iterations = chat_limits["max_iterations"]
        consecutive_failures = 0

        agent_id_str = str(agent.id)
        run_id = str(uuid_mod.uuid4())

        def _emit(etype: str, **kw: object) -> None:
            telemetry_bus.emit(agent_id_str, make_event(etype, agent_id_str, run_id, **kw))

        _emit("orchestration_start", trigger_type="chat", tools_count=len(tools))
        max_consecutive_failures = 3

        logger.info(
            "chat_with_agent_tools",
            agent_name=agent.name,
            tool_count=len(tools),
            tool_names=[t["name"] for t in tools],
            engine=agent.ai_engine,
            model=agent.ai_model,
        )

        try:
            for iteration in range(max_iterations):
                try:
                    response = await chat_with_tools(
                        engine=agent.ai_engine,
                        model=agent.ai_model or "",
                        api_key=api_key,
                        messages=messages,
                        tools=tools,
                        system_prompt=effective_system_prompt,
                    )
                except AIClientError as exc:
                    _emit("error", message=str(exc)[:300], phase="ai_call")
                    logger.error(
                        "agent_chat_failed",
                        agent_id=str(agent.id),
                        engine=agent.ai_engine,
                        error=str(exc),
                    )
                    raise

                content_blocks = response.get("content", [])
                stop_reason = response.get("stop_reason", "end_turn")
                usage = response.get("usage", {})

                tool_call_names = [b["name"] for b in content_blocks if b.get("type") == "tool_use"]
                text_preview = " ".join(
                    b.get("text", "")[:100] for b in content_blocks if b.get("type") == "text"
                )[:300]

                _emit("ai_thinking", iteration=iteration, usage=usage)
                for block in content_blocks:
                    if block.get("type") == "text" and block.get("text"):
                        _emit("ai_text", text=block["text"][:500])

                logger.info(
                    "chat_iteration",
                    agent_name=agent.name,
                    iteration=iteration,
                    stop_reason=stop_reason,
                    tool_calls=tool_call_names,
                    text_preview=text_preview or None,
                )

                if stop_reason != "tool_use":
                    texts = [
                        b["text"]
                        for b in content_blocks
                        if b.get("type") == "text" and b.get("text")
                    ]
                    _emit("completion", success=True, iterations=iteration + 1)
                    response_text = "\n".join(texts) if texts else "(No response)"
                    await self._save_chat_turns(
                        agent, account, message, response_text, agent_state, api_key
                    )
                    return response_text

                messages.append({"role": "assistant", "content": content_blocks})

                tool_results = []
                iteration_had_success = False
                for block in content_blocks:
                    if block.get("type") != "tool_use":
                        continue
                    tool_name = block["name"]
                    tool_input = block.get("input", {})
                    tool_id = block["id"]

                    _emit("tool_call", name=tool_name, args=tool_input)
                    result_str = await self._dispatch_chat_tool(
                        tool_name,
                        tool_input,
                        agent,
                        account,
                        agent_state,
                        mcp_pool,
                        available_tools=tools,
                    )
                    _emit("tool_result", name=tool_name, result_preview=result_str[:200])
                    logger.info(
                        "chat_tool_dispatch",
                        agent_name=agent.name,
                        tool_name=tool_name,
                        tool_input_keys=list(tool_input.keys()) if tool_input else [],
                        result_preview=result_str[:300],
                        is_error='"error"' in result_str[:50],
                    )
                    if '"error"' not in result_str[:50]:
                        iteration_had_success = True
                    tool_results.append(
                        {
                            "role": "tool_result",
                            "tool_use_id": tool_id,
                            "tool_name": tool_name,
                            "content": result_str,
                        }
                    )
                messages.extend(tool_results)

                if iteration_had_success:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        return (
                            f"(Stopped: {consecutive_failures} consecutive iterations "
                            "where all tool calls failed. The AI model may not be "
                            "using the correct tool name format.)"
                        )

            return "(Max chat iterations reached)"
        finally:
            if mcp_pool is not None:
                try:
                    await mcp_pool.__aexit__(None, None, None)
                except Exception:
                    logger.exception("chat_mcp_pool_cleanup_failed")

    async def _save_chat_turns(
        self,
        agent: Any,
        account: Any,
        user_message: str,
        assistant_response: str,
        agent_state: dict,
        api_key: str,
    ) -> None:
        """Persist user/assistant turns and trigger compaction if needed."""
        from mcpworks_api.core.conversation_memory import (
            append_turn,
            compact_history,
            needs_compaction,
        )

        tier = (
            account.user.effective_tier
            if account and hasattr(account, "user") and account.user
            else "pro-agent"
        )
        try:
            await append_turn(
                agent.id, agent.account_id, agent.name, "user", user_message, tier, "chat"
            )
            await append_turn(
                agent.id,
                agent.account_id,
                agent.name,
                "assistant",
                assistant_response,
                tier,
                "chat",
            )
        except Exception:
            logger.warning("chat_turn_save_failed", agent_name=agent.name)
            return

        if needs_compaction(agent_state):
            try:
                # Re-read state to include the turns we just appended
                fresh_state = await self.get_all_state(agent.id)
                await compact_history(
                    agent.account_id,
                    agent.name,
                    agent.ai_engine,
                    agent.ai_model or "",
                    api_key,
                    fresh_state,
                    tier,
                )
            except Exception:
                logger.warning("chat_compaction_failed", agent_name=agent.name)

    async def generate_chat_token(self, account_id: uuid.UUID, agent_name: str) -> dict:
        import base64
        import secrets as secrets_mod

        agent = await self.get_agent(account_id, agent_name)
        token = base64.urlsafe_b64encode(secrets_mod.token_bytes(32)).rstrip(b"=").decode()
        agent.chat_token = token
        await self.db.flush()
        chat_url = f"https://{agent.name}.agent.mcpworks.io/chat/{token}"
        logger.info("agent_chat_token_generated", agent_name=agent.name)
        return {"chat_url": chat_url, "chat_token": token}

    async def revoke_chat_token(self, account_id: uuid.UUID, agent_name: str) -> None:
        agent = await self.get_agent(account_id, agent_name)
        agent.chat_token = None
        await self.db.flush()
        logger.info("agent_chat_token_revoked", agent_name=agent.name)

    async def resolve_agent_by_chat_token(self, token: str) -> Agent | None:
        from sqlalchemy import select

        result = await self.db.execute(select(Agent).where(Agent.chat_token == token))
        return result.scalar_one_or_none()

    @staticmethod
    def _resolve_chat_limits(agent: Agent) -> dict:
        """Resolve chat iteration limits from agent orchestration overrides or tier defaults."""
        from mcpworks_api.tasks.orchestrator import DEFAULT_LIMITS, ORCHESTRATION_TIER_LIMITS

        tier = getattr(agent, "tier", None) or "pro-agent"
        limits = dict(ORCHESTRATION_TIER_LIMITS.get(tier, DEFAULT_LIMITS))
        overrides = agent.orchestration_limits
        if overrides:
            for key in ("max_iterations", "max_functions_called"):
                if key in overrides and isinstance(overrides[key], int):
                    limits[key] = overrides[key]
        return limits

    async def _dispatch_chat_tool(
        self,
        tool_name: str,
        tool_input: dict,
        agent: Agent,
        account: Any,
        agent_state: dict | None,
        mcp_pool: Any,
        available_tools: list[dict] | None = None,
    ) -> str:
        from mcpworks_api.core.ai_tools import format_available_tools, parse_tool_name
        from mcpworks_api.core.mcp_client import is_mcp_tool

        if tool_name == "get_state":
            try:
                value, _ = await self.get_state(
                    agent.account_id,
                    agent.name,
                    tool_input.get("key", ""),
                )
                return json.dumps({"key": tool_input.get("key"), "value": value})
            except Exception:
                return json.dumps({"error": f"State key '{tool_input.get('key', '')}' not found"})
        elif tool_name == "set_state":
            tier = (
                account.user.effective_tier if account and hasattr(account, "user") else "pro-agent"
            )
            await self.set_state(
                agent.account_id,
                agent.name,
                tool_input.get("key", ""),
                tool_input.get("value"),
                tier,
            )
            return json.dumps({"key": tool_input.get("key"), "stored": True})
        elif tool_name == "send_to_channel":
            from mcpworks_api.tasks.orchestrator import _send_to_channel

            return await _send_to_channel(
                agent,
                tool_input.get("channel_type", ""),
                tool_input.get("message", ""),
            )
        elif tool_name == "list_state_keys":
            tier = (
                account.user.effective_tier if account and hasattr(account, "user") else "pro-agent"
            )
            keys_info = await self.list_state_keys(agent.account_id, agent.name, tier)
            return json.dumps(
                {
                    "keys": keys_info["keys"],
                    "count": len(keys_info["keys"]),
                    "total_size_bytes": keys_info["total_size_bytes"],
                }
            )
        elif tool_name == "search_state":
            query = tool_input.get("query", "").lower()
            if not query:
                return json.dumps({"error": "query is required"})
            matches = []
            for key, value in (agent_state or {}).items():
                value_str = json.dumps(value, default=str) if not isinstance(value, str) else value
                if query in key.lower() or query in value_str.lower():
                    preview = value_str[:100] + ("..." if len(value_str) > 100 else "")
                    matches.append({"key": key, "preview": preview})
            return json.dumps(
                {
                    "matches": matches[:20],
                    "query": query,
                    "total_searched": len(agent_state or {}),
                }
            )
        elif is_mcp_tool(tool_name):
            if mcp_pool is None:
                return json.dumps({"error": "MCP server pool not available"})
            return await mcp_pool.call_tool(tool_name, tool_input)
        else:
            parsed = parse_tool_name(tool_name)
            if not parsed:
                available = format_available_tools(available_tools) if available_tools else "none"
                return json.dumps(
                    {
                        "error": f"Unknown tool: '{tool_name}'. Tool names use the format "
                        "'service_name__function_name' (double underscore). "
                        f"Available tools: {available}",
                    }
                )
            service_name, function_name = parsed
            from mcpworks_api.tasks.orchestrator import _execute_namespace_function

            return await _execute_namespace_function(
                service_name,
                function_name,
                tool_input,
                agent,
                account or agent,
                agent_state=agent_state,
                db=self.db,
            )

    async def add_channel(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        channel_type: str,
        config: dict,
    ) -> AgentChannel:
        agent = await self.get_agent(account_id, agent_name)
        existing = await self.db.execute(
            select(AgentChannel).where(
                AgentChannel.agent_id == agent.id,
                AgentChannel.channel_type == channel_type,
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(
                f"Channel type '{channel_type}' already configured for agent '{agent_name}'"
            )
        ciphertext, encrypted_dek = encrypt_value(config)
        channel = AgentChannel(
            agent_id=agent.id,
            channel_type=channel_type,
            config_encrypted=ciphertext,
            config_dek_encrypted=encrypted_dek,
            enabled=True,
        )
        self.db.add(channel)
        await self.db.flush()
        await self.db.refresh(channel)
        logger.info(
            "agent_channel_added",
            agent_id=str(agent.id),
            channel_type=channel_type,
        )
        return channel

    async def remove_channel(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        channel_type: str,
    ) -> None:
        agent = await self.get_agent(account_id, agent_name)
        result = await self.db.execute(
            select(AgentChannel).where(
                AgentChannel.agent_id == agent.id,
                AgentChannel.channel_type == channel_type,
            )
        )
        channel = result.scalar_one_or_none()
        if not channel:
            raise NotFoundError(f"Channel type '{channel_type}' not found")
        await self.db.delete(channel)
        await self.db.flush()
        logger.info(
            "agent_channel_removed",
            agent_id=str(agent.id),
            channel_type=channel_type,
        )

    async def configure_mcp_servers(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        servers: dict,
    ) -> Agent:
        agent = await self.get_agent(account_id, agent_name)
        agent.mcp_servers = servers if servers else None
        await self.db.flush()
        await self.db.refresh(agent)
        logger.info(
            "agent_mcp_servers_configured",
            agent_id=str(agent.id),
            server_count=len(servers) if servers else 0,
        )
        return agent

    async def get_mcp_servers(
        self,
        account_id: uuid.UUID,
        agent_name: str,
    ) -> dict | None:
        agent = await self.get_agent(account_id, agent_name)
        return agent.mcp_servers

    async def remove_mcp_servers(
        self,
        account_id: uuid.UUID,
        agent_name: str,
    ) -> Agent:
        agent = await self.get_agent(account_id, agent_name)
        agent.mcp_servers = None
        await self.db.flush()
        await self.db.refresh(agent)
        logger.info("agent_mcp_servers_removed", agent_id=str(agent.id))
        return agent

    async def clone_agent(
        self,
        account_id: uuid.UUID,
        source_agent_name: str,
        new_name: str,
        tier: str,
    ) -> Agent:
        tier_config = self._get_tier_config(tier)
        current_count = await self.get_agent_count(account_id)
        if current_count >= tier_config["max_agents"]:
            raise ConflictError(
                f"Agent slot limit reached ({tier_config['max_agents']} for {tier})"
            )

        existing = await self.db.execute(
            select(Agent).where(Agent.account_id == account_id, Agent.name == new_name)
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Agent '{new_name}' already exists")

        source = await self.get_agent(account_id, source_agent_name)

        source_with_relations = await self.db.execute(
            select(Agent)
            .where(Agent.id == source.id)
            .options(
                selectinload(Agent.state_entries),
                selectinload(Agent.schedules),
                selectinload(Agent.channels),
            )
        )
        source = source_with_relations.scalar_one()

        ns_manager = NamespaceServiceManager(self.db)
        namespace = await ns_manager.create(account_id=account_id, name=new_name)

        new_agent = Agent(
            account_id=account_id,
            namespace_id=namespace.id,
            name=new_name,
            display_name=source.display_name,
            status="creating",
            memory_limit_mb=tier_config["memory_limit_mb"],
            cpu_limit=tier_config["cpu_limit"],
            ai_engine=source.ai_engine,
            ai_model=source.ai_model,
            ai_api_key_encrypted=source.ai_api_key_encrypted,
            ai_api_key_dek_encrypted=source.ai_api_key_dek_encrypted,
            system_prompt=source.system_prompt,
            auto_channel=source.auto_channel,
            mcp_servers=source.mcp_servers,
            cloned_from_id=source.id,
        )
        self.db.add(new_agent)
        await self.db.flush()
        await self.db.refresh(new_agent)

        for state_entry in source.state_entries:
            cloned_state = AgentState(
                agent_id=new_agent.id,
                key=state_entry.key,
                value_encrypted=state_entry.value_encrypted,
                value_dek_encrypted=state_entry.value_dek_encrypted,
                size_bytes=state_entry.size_bytes,
            )
            self.db.add(cloned_state)

        for schedule in source.schedules:
            cloned_schedule = AgentSchedule(
                agent_id=new_agent.id,
                function_name=schedule.function_name,
                cron_expression=schedule.cron_expression,
                timezone=schedule.timezone,
                failure_policy=schedule.failure_policy,
                orchestration_mode=schedule.orchestration_mode,
                enabled=False,
                consecutive_failures=0,
            )
            self.db.add(cloned_schedule)

        for channel in source.channels:
            cloned_channel = AgentChannel(
                agent_id=new_agent.id,
                channel_type=channel.channel_type,
                config_encrypted=channel.config_encrypted,
                config_dek_encrypted=channel.config_dek_encrypted,
                enabled=channel.enabled,
            )
            self.db.add(cloned_channel)

        await self.db.flush()

        try:
            self._ensure_network()
            container = self.docker_client.containers.run(
                AGENT_IMAGE,
                name=f"{AGENT_CONTAINER_PREFIX}{new_name}",
                detach=True,
                network=AGENT_NETWORK_NAME,
                mem_limit=f"{tier_config['memory_limit_mb']}m",
                nano_cpus=int(tier_config["cpu_limit"] * 1e9),
                environment={
                    "AGENT_NAME": new_name,
                    "AGENT_ID": str(new_agent.id),
                    "MCPWORKS_API_URL": "http://mcpworks-api:8000",
                },
                restart_policy={"Name": "unless-stopped"},
                read_only=True,
                tmpfs={"/tmp": "size=64m,noexec,nosuid"},
                cap_drop=["ALL"],
                cap_add=["NET_BIND_SERVICE"],
                security_opt=["no-new-privileges"],
                user="1000:1000",
            )
            new_agent.container_id = container.id
            new_agent.status = "running"
        except DockerAPIError as e:
            logger.error("agent_clone_container_failed", agent=new_name, error=str(e))
            new_agent.status = "error"

        await self.db.flush()
        await self.db.refresh(new_agent)

        logger.info(
            "agent_cloned",
            source_agent=source_agent_name,
            new_agent=new_name,
            new_agent_id=str(new_agent.id),
        )
        return new_agent

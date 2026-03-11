"""Agent service — container lifecycle, scheduling, state, cloning."""

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
    ) -> AgentSchedule:
        agent = await self.get_agent(account_id, agent_name)
        tier_config = self._get_tier_config(tier)
        min_seconds = self._cron_min_interval_seconds(cron_expression)
        if min_seconds < tier_config["min_schedule_seconds"]:
            raise ForbiddenError(
                f"Minimum schedule interval for {tier} is {tier_config['min_schedule_seconds']}s; "
                f"cron expression resolves to {min_seconds}s"
            )
        schedule = AgentSchedule(
            agent_id=agent.id,
            function_name=function_name,
            cron_expression=cron_expression,
            timezone=timezone,
            failure_policy=failure_policy,
            enabled=True,
            consecutive_failures=0,
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

    async def configure_ai(
        self,
        account_id: uuid.UUID,
        agent_name: str,
        engine: str,
        model: str,
        api_key: str,
        system_prompt: str | None = None,
    ) -> Agent:
        agent = await self.get_agent(account_id, agent_name)
        ciphertext, encrypted_dek = encrypt_value(api_key)
        agent.ai_engine = engine
        agent.ai_model = model
        agent.ai_api_key_encrypted = ciphertext
        agent.ai_api_key_dek_encrypted = encrypted_dek
        agent.system_prompt = system_prompt
        await self.db.flush()
        await self.db.refresh(agent)
        logger.info("agent_ai_configured", agent_id=str(agent.id), engine=engine, model=model)
        return agent

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

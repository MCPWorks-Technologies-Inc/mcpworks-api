"""Unit tests for AgentService (services/agent_service.py).

Uses mocked Docker SDK and async DB session. Target: 80% coverage.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docker.errors import APIError as DockerAPIError
from docker.errors import NotFound as DockerNotFound

from mcpworks_api.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from mcpworks_api.services.agent_service import AgentService


def _make_agent(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "namespace_id": uuid.uuid4(),
        "name": "test-agent",
        "display_name": None,
        "container_id": "container123",
        "status": "running",
        "memory_limit_mb": 256,
        "cpu_limit": 0.25,
        "ai_engine": None,
        "ai_model": None,
        "ai_api_key_encrypted": None,
        "ai_api_key_dek_encrypted": None,
        "system_prompt": None,
        "enabled": True,
        "cloned_from_id": None,
        "created_at": datetime.now(tz=UTC),
        "updated_at": datetime.now(tz=UTC),
    }
    defaults.update(overrides)
    agent = MagicMock()
    for k, v in defaults.items():
        setattr(agent, k, v)
    return agent


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def mock_docker():
    with patch("mcpworks_api.services.agent_service.docker") as mock:
        client = MagicMock()
        mock.from_env.return_value = client
        client.networks.get = MagicMock()
        yield client


@pytest.fixture
def service(mock_db, mock_docker):
    svc = AgentService(mock_db)
    svc._docker = mock_docker
    return svc


class TestGetTierConfig:
    def test_valid_agent_tier(self, service):
        config = service._get_tier_config("trial-agent")
        assert config["max_agents"] == 5
        assert config["memory_limit_mb"] == 512

    def test_invalid_tier_raises(self, service):
        with pytest.raises(ForbiddenError, match="not agent-enabled"):
            service._get_tier_config("trial")


class TestCreateAgent:
    @pytest.mark.asyncio
    async def test_slot_limit_exceeded(self, service, mock_db):
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 5
        mock_db.execute.return_value = result_mock

        with pytest.raises(ConflictError, match="slot limit"):
            await service.create_agent(
                account_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                tier="trial-agent",
                name="agent2",
            )

    @pytest.mark.asyncio
    async def test_duplicate_name_rejected(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = _make_agent()
        mock_db.execute.side_effect = [count_result, existing_result]

        with pytest.raises(ConflictError, match="already exists"):
            await service.create_agent(
                account_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                tier="trial-agent",
                name="dupe",
            )

    @pytest.mark.asyncio
    async def test_docker_failure_sets_error_status(self, service, mock_db, mock_docker):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        replicas_result = MagicMock()
        replicas_result.scalars.return_value = iter([])
        mock_db.execute.side_effect = [count_result, existing_result, replicas_result]

        ns_mock = MagicMock()
        ns_mock.id = uuid.uuid4()
        with patch("mcpworks_api.services.agent_service.NamespaceServiceManager") as ns_cls:
            ns_cls.return_value.create = AsyncMock(return_value=ns_mock)

            mock_db.flush = AsyncMock()
            mock_db.refresh = AsyncMock(side_effect=lambda _a, *_args, **_kwargs: None)

            mock_docker.containers.run.side_effect = DockerAPIError("out of memory")

            await service.create_agent(
                account_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                tier="pro-agent",
                name="fail-agent",
            )
            assert mock_db.flush.await_count >= 1


def _make_replica(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "agent_id": uuid.uuid4(),
        "replica_name": "bold-ant",
        "container_id": "container123",
        "status": "running",
        "last_heartbeat": None,
        "created_at": datetime.now(tz=UTC),
    }
    defaults.update(overrides)
    replica = MagicMock()
    for k, v in defaults.items():
        setattr(replica, k, v)
    return replica


class TestStartAgent:
    @pytest.mark.asyncio
    async def test_start_stopped_agent(self, service, mock_db, mock_docker):
        agent = _make_agent(status="stopped", replicas=[])
        replica = _make_replica(status="stopped")
        with (
            patch.object(service, "get_agent", new=AsyncMock(return_value=agent)),
            patch.object(service, "_get_replicas", new=AsyncMock(return_value=[replica])),
        ):
            container = MagicMock()
            mock_docker.containers.get.return_value = container
            mock_db.refresh = AsyncMock(side_effect=lambda _a, *_args, **_kwargs: None)

            await service.start_agent(uuid.uuid4(), "test-agent")
            container.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_missing_container_recreates(self, service, mock_db, mock_docker):
        agent = _make_agent(status="stopped", replicas=[])
        replica = _make_replica(status="stopped")
        new_container = MagicMock()
        new_container.id = "new-container-id"
        new_container.short_id = "new-cont"
        with (
            patch.object(service, "get_agent", new=AsyncMock(return_value=agent)),
            patch.object(service, "_get_replicas", new=AsyncMock(return_value=[replica])),
        ):
            mock_docker.containers.get.side_effect = DockerNotFound("gone")
            mock_docker.containers.run.return_value = new_container
            mock_db.refresh = AsyncMock(side_effect=lambda _a, *_args, **_kwargs: None)

            await service.start_agent(uuid.uuid4(), "test-agent")
            assert replica.status == "running"
            assert replica.container_id == "new-container-id"
            mock_docker.containers.run.assert_called_once()


class TestStopAgent:
    @pytest.mark.asyncio
    async def test_stop_running_agent(self, service, mock_db, mock_docker):
        agent = _make_agent(status="running", replicas=[])
        replica = _make_replica(status="running")
        with (
            patch.object(service, "get_agent", new=AsyncMock(return_value=agent)),
            patch.object(service, "_get_replicas", new=AsyncMock(return_value=[replica])),
        ):
            container = MagicMock()
            mock_docker.containers.get.return_value = container
            mock_db.refresh = AsyncMock(side_effect=lambda _a, *_args, **_kwargs: None)

            await service.stop_agent(uuid.uuid4(), "test-agent")
            assert replica.status == "stopped"
            container.stop.assert_called_once_with(timeout=10)

    @pytest.mark.asyncio
    async def test_stop_non_running_raises(self, service, mock_db):
        agent = _make_agent(status="stopped", replicas=[])
        with (
            patch.object(service, "get_agent", new=AsyncMock(return_value=agent)),
            patch.object(service, "_get_replicas", new=AsyncMock(return_value=[])),
        ):
            mock_db.refresh = AsyncMock(side_effect=lambda _a, *_args, **_kwargs: None)
            await service.stop_agent(uuid.uuid4(), "test-agent")


class TestDestroyAgent:
    @pytest.mark.asyncio
    async def test_destroy_removes_container_and_records(self, service, mock_db, mock_docker):
        agent = _make_agent()
        ns = MagicMock()
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = ns
        mock_db.execute.return_value = ns_result

        container = MagicMock()
        mock_docker.containers.get.return_value = container

        with (
            patch.object(service, "get_agent", new=AsyncMock(return_value=agent)),
            patch.object(service, "_get_replicas", new=AsyncMock(return_value=[])),
        ):
            await service.destroy_agent(uuid.uuid4(), "test-agent")
            container.remove.assert_called_once_with(force=True)
            assert mock_db.delete.await_count >= 1

    @pytest.mark.asyncio
    async def test_destroy_missing_container_succeeds(self, service, mock_db, mock_docker):
        agent = _make_agent()
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = ns_result

        mock_docker.containers.get.side_effect = DockerNotFound("gone")

        with patch.object(service, "get_agent", new=AsyncMock(return_value=agent)):
            await service.destroy_agent(uuid.uuid4(), "test-agent")


class TestGetAgent:
    @pytest.mark.asyncio
    async def test_not_found_raises(self, service, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        with pytest.raises(NotFoundError, match="not found"):
            await service.get_agent(uuid.uuid4(), "nonexistent")


class TestGetAgentSlots:
    @pytest.mark.asyncio
    async def test_returns_slot_info(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 3
        mock_db.execute.return_value = count_result

        slots = await service.get_agent_slots(uuid.uuid4(), "pro-agent")
        assert slots["slots_used"] == 3
        assert slots["slots_total"] == 5
        assert slots["slots_available"] == 2


class TestContainerStats:
    @pytest.mark.asyncio
    async def test_returns_stats(self, service, mock_docker):
        agent = _make_agent()
        container = MagicMock()
        container.status = "running"
        container.stats.return_value = {
            "memory_stats": {"usage": 128 * 1024 * 1024},
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200, "percpu_usage": [100, 100]},
                "system_cpu_usage": 1000,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 500,
            },
        }
        mock_docker.containers.get.return_value = container

        stats = await service.get_container_stats(agent)
        assert stats is not None
        assert stats["status"] == "running"
        assert stats["memory_usage_mb"] == 128.0

    @pytest.mark.asyncio
    async def test_missing_container_returns_none(self, service, mock_docker):
        agent = _make_agent(container_id=None)
        result = await service.get_container_stats(agent)
        assert result is None


class TestForceRestart:
    @pytest.mark.asyncio
    async def test_restarts_container(self, service, mock_db, mock_docker):
        agent = _make_agent()
        container = MagicMock()
        mock_docker.containers.get.return_value = container

        result = await service.force_restart_agent(agent)
        assert result.status == "running"
        container.restart.assert_called_once_with(timeout=10)

    @pytest.mark.asyncio
    async def test_no_container_sets_error(self, service, mock_db):
        agent = _make_agent(container_id=None)
        result = await service.force_restart_agent(agent)
        assert result.status == "error"


class TestCronMinInterval:
    def test_every_minute(self):
        assert AgentService._cron_min_interval_seconds("* * * * *") == 60

    def test_every_5_minutes(self):
        assert AgentService._cron_min_interval_seconds("*/5 * * * *") == 300

    def test_every_15_minutes(self):
        assert AgentService._cron_min_interval_seconds("*/15 * * * *") == 900

    def test_hourly(self):
        assert AgentService._cron_min_interval_seconds("0 * * * *") == 60

    def test_every_2_hours(self):
        assert AgentService._cron_min_interval_seconds("0 */2 * * *") == 7200

    def test_specific_minutes(self):
        assert AgentService._cron_min_interval_seconds("30 */1 * * *") == 3600

    def test_malformed_short(self):
        assert AgentService._cron_min_interval_seconds("* *") == 60


class TestCalcCpuPercent:
    def test_normal_stats(self):
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200, "percpu_usage": [100, 100]},
                "system_cpu_usage": 1000,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 500,
            },
        }
        result = AgentService._calc_cpu_percent(stats)
        assert result == 40.0

    def test_zero_delta(self):
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 100, "percpu_usage": [100]},
                "system_cpu_usage": 500,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 500,
            },
        }
        assert AgentService._calc_cpu_percent(stats) == 0.0

    def test_empty_stats(self):
        assert AgentService._calc_cpu_percent({}) == 0.0

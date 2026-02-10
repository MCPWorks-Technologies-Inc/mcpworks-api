"""Unit tests for router service."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.exceptions import (
    InsufficientCreditsError,
    InsufficientTierError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from mcpworks_api.models import Service, ServiceStatus
from mcpworks_api.services.router import (
    TIER_HIERARCHY,
    ServiceRouter,
    seed_default_services,
)


class TestTierHierarchy:
    """Tests for tier hierarchy constants."""

    def test_tier_levels(self):
        """Test tier levels are correctly defined."""
        assert TIER_HIERARCHY["free"] == 0
        assert TIER_HIERARCHY["starter"] == 1
        assert TIER_HIERARCHY["pro"] == 2
        assert TIER_HIERARCHY["enterprise"] == 3

    def test_tier_ordering(self):
        """Test tiers are ordered correctly."""
        assert TIER_HIERARCHY["free"] < TIER_HIERARCHY["starter"]
        assert TIER_HIERARCHY["starter"] < TIER_HIERARCHY["pro"]
        assert TIER_HIERARCHY["pro"] < TIER_HIERARCHY["enterprise"]


class TestServiceRouterInit:
    """Tests for ServiceRouter initialization."""

    def test_init_sets_db_and_settings(self):
        """Test initialization sets database and settings."""
        mock_db = MagicMock(spec=AsyncSession)

        with patch("mcpworks_api.services.router.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock()
            router = ServiceRouter(mock_db)

            assert router.db == mock_db
            assert router.settings is not None


class TestGetService:
    """Tests for get_service method."""

    @pytest.mark.asyncio
    async def test_get_existing_service(self, db: AsyncSession):
        """Test getting an existing service."""
        # Create test service
        service = Service(
            name="test-service",
            display_name="Test Service",
            description="Test description",
            url="http://localhost:8080",
            credit_cost=Decimal("1.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(service)
        await db.flush()

        router = ServiceRouter(db)
        result = await router.get_service("test-service")

        assert result is not None
        assert result.name == "test-service"

    @pytest.mark.asyncio
    async def test_get_nonexistent_service(self, db: AsyncSession):
        """Test getting a service that doesn't exist returns None."""
        router = ServiceRouter(db)
        result = await router.get_service("nonexistent")

        assert result is None


class TestListServices:
    """Tests for list_services method."""

    @pytest.mark.asyncio
    async def test_list_active_services(self, db: AsyncSession):
        """Test listing active services."""
        # Create test services
        active_service = Service(
            name="active-service",
            display_name="Active Service",
            description="Active",
            url="http://localhost:8080",
            credit_cost=Decimal("1.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        degraded_service = Service(
            name="degraded-service",
            display_name="Degraded Service",
            description="Degraded",
            url="http://localhost:8081",
            credit_cost=Decimal("1.00"),
            tier_required="free",
            status=ServiceStatus.DEGRADED.value,
        )
        inactive_service = Service(
            name="inactive-service",
            display_name="Inactive Service",
            description="Inactive",
            url="http://localhost:8082",
            credit_cost=Decimal("1.00"),
            tier_required="free",
            status=ServiceStatus.INACTIVE.value,
        )
        db.add_all([active_service, degraded_service, inactive_service])
        await db.flush()

        router = ServiceRouter(db)
        result = await router.list_services()

        # Should include active and degraded, but not inactive
        names = [s.name for s in result]
        assert "active-service" in names
        assert "degraded-service" in names
        assert "inactive-service" not in names


class TestCanAccessService:
    """Tests for can_access_service method."""

    @pytest.mark.asyncio
    async def test_free_user_accesses_free_service(self, db: AsyncSession):
        """Test free user can access free service."""
        router = ServiceRouter(db)
        service = MagicMock(tier_required="free")

        assert router.can_access_service("free", service) is True

    @pytest.mark.asyncio
    async def test_free_user_cannot_access_pro_service(self, db: AsyncSession):
        """Test free user cannot access pro service."""
        router = ServiceRouter(db)
        service = MagicMock(tier_required="pro")

        assert router.can_access_service("free", service) is False

    @pytest.mark.asyncio
    async def test_pro_user_accesses_starter_service(self, db: AsyncSession):
        """Test pro user can access starter service."""
        router = ServiceRouter(db)
        service = MagicMock(tier_required="starter")

        assert router.can_access_service("pro", service) is True

    @pytest.mark.asyncio
    async def test_enterprise_user_accesses_all_services(self, db: AsyncSession):
        """Test enterprise user can access all services."""
        router = ServiceRouter(db)

        for required_tier in ["free", "starter", "pro", "enterprise"]:
            service = MagicMock(tier_required=required_tier)
            assert router.can_access_service("enterprise", service) is True

    @pytest.mark.asyncio
    async def test_unknown_tier_defaults_to_zero(self, db: AsyncSession):
        """Test unknown tier defaults to level 0 (free)."""
        router = ServiceRouter(db)
        service = MagicMock(tier_required="starter")

        # Unknown tier should be treated as free (level 0)
        assert router.can_access_service("unknown_tier", service) is False


class TestRouteRequest:
    """Tests for route_request method."""

    @pytest.mark.asyncio
    async def test_route_request_service_not_found(self, db: AsyncSession):
        """Test routing to nonexistent service raises error."""
        router = ServiceRouter(db)
        user_id = uuid.uuid4()

        with pytest.raises(ServiceUnavailableError) as exc_info:
            await router.route_request(
                service_name="nonexistent",
                method="GET",
                path="/test",
                user_id=user_id,
                user_tier="free",
            )

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_route_request_service_unavailable(self, db: AsyncSession):
        """Test routing to unavailable service raises error."""
        service = Service(
            name="unavailable-service",
            display_name="Unavailable Service",
            description="Unavailable",
            url="http://localhost:8080",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.INACTIVE.value,
        )
        db.add(service)
        await db.flush()

        router = ServiceRouter(db)
        user_id = uuid.uuid4()

        with pytest.raises(ServiceUnavailableError):
            await router.route_request(
                service_name="unavailable-service",
                method="GET",
                path="/test",
                user_id=user_id,
                user_tier="free",
            )

    @pytest.mark.asyncio
    async def test_route_request_insufficient_tier(self, db: AsyncSession):
        """Test routing when tier is insufficient."""
        service = Service(
            name="pro-service",
            display_name="Pro Service",
            description="Pro only",
            url="http://localhost:8080",
            credit_cost=Decimal("0.00"),
            tier_required="pro",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(service)
        await db.flush()

        router = ServiceRouter(db)
        user_id = uuid.uuid4()

        with pytest.raises(InsufficientTierError) as exc_info:
            await router.route_request(
                service_name="pro-service",
                method="GET",
                path="/test",
                user_id=user_id,
                user_tier="free",
            )

        assert "pro" in str(exc_info.value)


class TestMakeRequest:
    """Tests for _make_request method."""

    @pytest.mark.asyncio
    async def test_make_request_success(self, db: AsyncSession):
        """Test successful HTTP request."""
        router = ServiceRouter(db)

        with patch.object(httpx.AsyncClient, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": "success"}
            mock_response.headers = {"content-type": "application/json"}
            mock_request.return_value = mock_response

            status, headers, body = await router._make_request(
                method="GET",
                url="http://localhost:8080/test",
            )

            assert status == 200
            assert body == {"result": "success"}

    @pytest.mark.asyncio
    async def test_make_request_timeout(self, db: AsyncSession):
        """Test request timeout raises ServiceTimeoutError."""
        router = ServiceRouter(db)

        with patch.object(httpx.AsyncClient, "request") as mock_request:
            mock_request.side_effect = httpx.TimeoutException("Timeout")

            with pytest.raises(ServiceTimeoutError) as exc_info:
                await router._make_request(
                    method="GET",
                    url="http://localhost:8080/test",
                )

            assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_make_request_connection_error(self, db: AsyncSession):
        """Test connection error raises ServiceUnavailableError."""
        router = ServiceRouter(db)

        with patch.object(httpx.AsyncClient, "request") as mock_request:
            mock_request.side_effect = httpx.ConnectError("Connection refused")

            with pytest.raises(ServiceUnavailableError) as exc_info:
                await router._make_request(
                    method="GET",
                    url="http://localhost:8080/test",
                )

            assert "Cannot connect" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_make_request_non_json_response(self, db: AsyncSession):
        """Test handling non-JSON response."""
        router = ServiceRouter(db)

        with patch.object(httpx.AsyncClient, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = ValueError("Not JSON")
            mock_response.text = "Plain text response"
            mock_response.headers = {"content-type": "text/plain"}
            mock_request.return_value = mock_response

            status, headers, body = await router._make_request(
                method="GET",
                url="http://localhost:8080/test",
            )

            assert status == 200
            assert body == {"raw": "Plain text response"}

    @pytest.mark.asyncio
    async def test_make_request_with_body_and_headers(self, db: AsyncSession):
        """Test request with body and custom headers."""
        router = ServiceRouter(db)

        with patch.object(httpx.AsyncClient, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"created": True}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            status, headers, body = await router._make_request(
                method="POST",
                url="http://localhost:8080/create",
                body={"name": "test"},
                headers={"X-Custom": "header"},
            )

            assert status == 201
            # Verify request was made with correct arguments
            call_args = mock_request.call_args
            assert call_args.kwargs["json"] == {"name": "test"}
            assert "X-Custom" in call_args.kwargs["headers"]


class TestCheckServiceHealth:
    """Tests for check_service_health method."""

    @pytest.mark.asyncio
    async def test_check_healthy_service(self, db: AsyncSession):
        """Test checking health of healthy service."""
        service = Service(
            name="healthy-service",
            display_name="Healthy Service",
            description="Healthy",
            url="http://localhost:8080",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(service)
        await db.flush()

        router = ServiceRouter(db)

        with patch.object(httpx.AsyncClient, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            is_healthy = await router.check_service_health(service)

            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_check_unhealthy_service(self, db: AsyncSession):
        """Test checking health of unhealthy service."""
        service = Service(
            name="unhealthy-service",
            display_name="Unhealthy Service",
            description="Unhealthy",
            url="http://localhost:8080",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(service)
        await db.flush()

        router = ServiceRouter(db)

        with patch.object(httpx.AsyncClient, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response

            is_healthy = await router.check_service_health(service)

            assert is_healthy is False

    @pytest.mark.asyncio
    async def test_check_service_connection_failure(self, db: AsyncSession):
        """Test checking health when connection fails."""
        service = Service(
            name="unreachable-service",
            display_name="Unreachable Service",
            description="Unreachable",
            url="http://localhost:9999",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(service)
        await db.flush()

        router = ServiceRouter(db)

        with patch.object(httpx.AsyncClient, "get") as mock_get:
            mock_get.side_effect = Exception("Connection refused")

            is_healthy = await router.check_service_health(service)

            assert is_healthy is False


class TestCheckAllServicesHealth:
    """Tests for check_all_services_health method."""

    @pytest.mark.asyncio
    async def test_check_multiple_services(self, db: AsyncSession):
        """Test checking health of multiple services."""
        service1 = Service(
            name="service-1",
            display_name="Service 1",
            description="Test",
            url="http://localhost:8080",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        service2 = Service(
            name="service-2",
            display_name="Service 2",
            description="Test",
            url="http://localhost:8081",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add_all([service1, service2])
        await db.flush()

        router = ServiceRouter(db)

        # Mock at the httpx level since check_service_health is async
        with patch.object(httpx.AsyncClient, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            results = await router.check_all_services_health()

            assert "service-1" in results
            assert "service-2" in results
            # Both return healthy since mock returns 200
            assert results["service-1"] is True
            assert results["service-2"] is True


class TestSeedDefaultServices:
    """Tests for seed_default_services function."""

    @pytest.mark.asyncio
    async def test_seeds_math_and_agent_services(self, db: AsyncSession):
        """Test seeding creates default services."""
        await seed_default_services(db)

        router = ServiceRouter(db)
        math_service = await router.get_service("math")
        agent_service = await router.get_service("agent")

        assert math_service is not None
        assert math_service.display_name == "Math MCP"
        assert math_service.credit_cost == Decimal("0.00")

        assert agent_service is not None
        assert agent_service.display_name == "Workflow Agent"
        assert agent_service.credit_cost == Decimal("1.00")

    @pytest.mark.asyncio
    async def test_seed_is_idempotent(self, db: AsyncSession):
        """Test seeding twice doesn't create duplicates."""
        await seed_default_services(db)
        await seed_default_services(db)

        router = ServiceRouter(db)
        services = await router.list_services()

        # Should only have 2 services
        math_count = sum(1 for s in services if s.name == "math")
        agent_count = sum(1 for s in services if s.name == "agent")

        assert math_count == 1
        assert agent_count == 1

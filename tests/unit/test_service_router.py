"""Unit tests for ServiceRouter."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcpworks_api.core.exceptions import (
    InsufficientTierError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from mcpworks_api.models import Service, ServiceStatus
from mcpworks_api.services.router import TIER_HIERARCHY, ServiceRouter


class TestTierHierarchy:
    """Tests for tier hierarchy per A0-SYSTEM-SPECIFICATION.md."""

    def test_tier_hierarchy_order(self):
        """Test that tier hierarchy has correct order."""
        assert TIER_HIERARCHY["free"] < TIER_HIERARCHY["founder"]
        assert TIER_HIERARCHY["founder"] < TIER_HIERARCHY["founder_pro"]
        assert TIER_HIERARCHY["founder_pro"] < TIER_HIERARCHY["enterprise"]


class TestCanAccessService:
    """Tests for can_access_service method."""

    @pytest.fixture
    def router(self):
        """Create router with mock db."""
        mock_db = AsyncMock()
        return ServiceRouter(mock_db)

    def test_free_user_can_access_free_service(self, router):
        """Test free tier can access free services."""
        service = MagicMock(spec=Service)
        service.tier_required = "free"

        assert router.can_access_service("free", service) is True

    def test_free_user_cannot_access_founder_service(self, router):
        """Test free tier cannot access founder services."""
        service = MagicMock(spec=Service)
        service.tier_required = "founder"

        assert router.can_access_service("free", service) is False

    def test_founder_pro_user_can_access_founder_service(self, router):
        """Test higher tier can access lower tier services."""
        service = MagicMock(spec=Service)
        service.tier_required = "founder"

        assert router.can_access_service("founder_pro", service) is True

    def test_enterprise_user_can_access_all_services(self, router):
        """Test enterprise can access all services."""
        for tier in ["free", "founder", "founder_pro", "enterprise"]:
            service = MagicMock(spec=Service)
            service.tier_required = tier
            assert router.can_access_service("enterprise", service) is True


class TestGetService:
    """Tests for get_service method."""

    @pytest.mark.asyncio
    async def test_get_existing_service(self):
        """Test getting an existing service."""
        mock_service = Service(
            name="math",
            url="http://math:8001",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_service
        mock_db.execute.return_value = mock_result

        router = ServiceRouter(mock_db)
        service = await router.get_service("math")

        assert service is not None
        assert service.name == "math"

    @pytest.mark.asyncio
    async def test_get_nonexistent_service(self):
        """Test getting a service that doesn't exist."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        router = ServiceRouter(mock_db)
        service = await router.get_service("nonexistent")

        assert service is None


class TestListServices:
    """Tests for list_services method."""

    @pytest.mark.asyncio
    async def test_list_active_services(self):
        """Test listing active and degraded services."""
        mock_services = [
            Service(
                name="math",
                url="http://math:8001",
                credit_cost=Decimal("0.00"),
                tier_required="free",
                status=ServiceStatus.ACTIVE.value,
            ),
            Service(
                name="agent",
                url="http://agent:8002",
                credit_cost=Decimal("1.00"),
                tier_required="free",
                status=ServiceStatus.DEGRADED.value,
            ),
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_services
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        router = ServiceRouter(mock_db)
        services = await router.list_services()

        assert len(services) == 2


class TestRouteRequest:
    """Tests for route_request method."""

    @pytest.mark.asyncio
    async def test_route_to_unavailable_service_raises_error(self):
        """Test routing to unavailable service raises ServiceUnavailableError."""
        mock_service = Service(
            name="math",
            url="http://math:8001",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.INACTIVE.value,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_service
        mock_db.execute.return_value = mock_result

        router = ServiceRouter(mock_db)

        with pytest.raises(ServiceUnavailableError):
            await router.route_request(
                service_name="math",
                method="POST",
                path="/verify",
                user_id=uuid.uuid4(),
                user_tier="free",
                body={"problem": "2+2=4"},
            )

    @pytest.mark.asyncio
    async def test_route_to_nonexistent_service_raises_error(self):
        """Test routing to nonexistent service raises ServiceUnavailableError."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        router = ServiceRouter(mock_db)

        with pytest.raises(ServiceUnavailableError):
            await router.route_request(
                service_name="nonexistent",
                method="POST",
                path="/verify",
                user_id=uuid.uuid4(),
                user_tier="free",
                body={},
            )

    @pytest.mark.asyncio
    async def test_route_with_insufficient_tier_raises_error(self):
        """Test routing with insufficient tier raises InsufficientTierError."""
        mock_service = Service(
            name="premium",
            url="http://premium:8003",
            credit_cost=Decimal("0.00"),
            tier_required="founder_pro",  # Requires founder_pro tier
            status=ServiceStatus.ACTIVE.value,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_service
        mock_db.execute.return_value = mock_result

        router = ServiceRouter(mock_db)

        with pytest.raises(InsufficientTierError):
            await router.route_request(
                service_name="premium",
                method="POST",
                path="/verify",
                user_id=uuid.uuid4(),
                user_tier="free",  # Free tier user
                body={},
            )

    @pytest.mark.asyncio
    async def test_route_successful_free_service(self):
        """Test successful routing to free service."""
        mock_service = Service(
            name="math",
            url="http://math:8001",
            credit_cost=Decimal("0.00"),  # Free
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_service
        mock_db.execute.return_value = mock_result

        router = ServiceRouter(mock_db)

        # Mock the HTTP request
        with patch.object(router, "_make_request") as mock_request:
            mock_request.return_value = (
                200,
                {"Content-Type": "application/json"},
                {"is_correct": True, "confidence": 0.95},
            )

            status_code, headers, body = await router.route_request(
                service_name="math",
                method="POST",
                path="/verify",
                user_id=uuid.uuid4(),
                user_tier="free",
                body={"problem": "2+2=4"},
            )

            assert status_code == 200
            assert body["is_correct"] is True

    @pytest.mark.asyncio
    async def test_route_commits_credits_on_2xx_response(self):
        """Test that credits are committed on successful (2xx) response."""
        mock_service = Service(
            name="agent",
            url="http://agent:8002",
            credit_cost=Decimal("1.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_service
        mock_db.execute.return_value = mock_result

        router = ServiceRouter(mock_db)
        user_id = uuid.uuid4()

        with (
            patch.object(router, "_make_request") as mock_request,
            patch("mcpworks_api.services.router.CreditService") as mock_credit_class,
        ):
            mock_request.return_value = (200, {}, {"result": "success"})

            mock_credit_service = MagicMock()
            mock_hold_txn = MagicMock()
            mock_hold_txn.id = uuid.uuid4()
            mock_credit_service.hold = AsyncMock(return_value=mock_hold_txn)
            mock_credit_service.commit = AsyncMock()
            mock_credit_service.release = AsyncMock()
            mock_credit_class.return_value = mock_credit_service

            status_code, _, _ = await router.route_request(
                service_name="agent",
                method="POST",
                path="/execute",
                user_id=user_id,
                user_tier="free",
                body={},
            )

            assert status_code == 200
            mock_credit_service.commit.assert_called_once()
            mock_credit_service.release.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_releases_credits_on_4xx_response(self):
        """Test that credits are released on client error (4xx) response."""
        mock_service = Service(
            name="agent",
            url="http://agent:8002",
            credit_cost=Decimal("1.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_service
        mock_db.execute.return_value = mock_result

        router = ServiceRouter(mock_db)
        user_id = uuid.uuid4()

        with (
            patch.object(router, "_make_request") as mock_request,
            patch("mcpworks_api.services.router.CreditService") as mock_credit_class,
        ):
            # Backend returns 400 Bad Request
            mock_request.return_value = (400, {}, {"error": "Invalid input"})

            mock_credit_service = MagicMock()
            mock_hold_txn = MagicMock()
            mock_hold_txn.id = uuid.uuid4()
            mock_credit_service.hold = AsyncMock(return_value=mock_hold_txn)
            mock_credit_service.commit = AsyncMock()
            mock_credit_service.release = AsyncMock()
            mock_credit_class.return_value = mock_credit_service

            status_code, _, _ = await router.route_request(
                service_name="agent",
                method="POST",
                path="/execute",
                user_id=user_id,
                user_tier="free",
                body={},
            )

            assert status_code == 400
            mock_credit_service.release.assert_called_once()
            mock_credit_service.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_releases_credits_on_5xx_response(self):
        """Test that credits are released on server error (5xx) response."""
        mock_service = Service(
            name="agent",
            url="http://agent:8002",
            credit_cost=Decimal("1.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_service
        mock_db.execute.return_value = mock_result

        router = ServiceRouter(mock_db)
        user_id = uuid.uuid4()

        with (
            patch.object(router, "_make_request") as mock_request,
            patch("mcpworks_api.services.router.CreditService") as mock_credit_class,
        ):
            # Backend returns 500 Internal Server Error
            mock_request.return_value = (500, {}, {"error": "Internal error"})

            mock_credit_service = MagicMock()
            mock_hold_txn = MagicMock()
            mock_hold_txn.id = uuid.uuid4()
            mock_credit_service.hold = AsyncMock(return_value=mock_hold_txn)
            mock_credit_service.commit = AsyncMock()
            mock_credit_service.release = AsyncMock()
            mock_credit_class.return_value = mock_credit_service

            status_code, _, _ = await router.route_request(
                service_name="agent",
                method="POST",
                path="/execute",
                user_id=user_id,
                user_tier="free",
                body={},
            )

            assert status_code == 500
            mock_credit_service.release.assert_called_once()
            mock_credit_service.commit.assert_not_called()


class TestMakeRequest:
    """Tests for _make_request method."""

    @pytest.mark.asyncio
    async def test_timeout_raises_error(self):
        """Test that timeout raises ServiceTimeoutError."""
        import httpx

        mock_db = AsyncMock()
        router = ServiceRouter(mock_db)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.request.side_effect = httpx.TimeoutException("Timeout")
            mock_client_class.return_value = mock_client

            with pytest.raises(ServiceTimeoutError):
                await router._make_request(
                    method="POST",
                    url="http://math:8001/verify",
                    body={"problem": "test"},
                )

    @pytest.mark.asyncio
    async def test_connection_error_raises_unavailable(self):
        """Test that connection error raises ServiceUnavailableError."""
        import httpx

        mock_db = AsyncMock()
        router = ServiceRouter(mock_db)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.request.side_effect = httpx.ConnectError("Connection refused")
            mock_client_class.return_value = mock_client

            with pytest.raises(ServiceUnavailableError):
                await router._make_request(
                    method="POST",
                    url="http://math:8001/verify",
                    body={"problem": "test"},
                )


class TestCheckServiceHealth:
    """Tests for check_service_health method."""

    @pytest.mark.asyncio
    async def test_healthy_service_updates_status(self):
        """Test that healthy service updates status to active."""
        mock_service = Service(
            id=uuid.uuid4(),
            name="math",
            url="http://math:8001",
            health_check_url="http://math:8001/health",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.DEGRADED.value,
        )

        mock_db = AsyncMock()
        router = ServiceRouter(mock_db)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            is_healthy = await router.check_service_health(mock_service)

            assert is_healthy is True
            mock_db.execute.assert_called()
            mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_unhealthy_service_updates_status(self):
        """Test that unhealthy service updates status to inactive."""
        mock_service = Service(
            id=uuid.uuid4(),
            name="math",
            url="http://math:8001",
            health_check_url="http://math:8001/health",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )

        mock_db = AsyncMock()
        router = ServiceRouter(mock_db)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = Exception("Connection refused")
            mock_client_class.return_value = mock_client

            is_healthy = await router.check_service_health(mock_service)

            assert is_healthy is False
            mock_db.execute.assert_called()
            mock_db.commit.assert_called()

"""Integration tests for service endpoints."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.security import create_access_token
from mcpworks_api.models import Service, ServiceStatus, User


@pytest.fixture
def auth_headers(test_settings):
    """Generate valid JWT auth headers for testing."""
    user_id = str(uuid.uuid4())
    access_token = create_access_token(
        user_id=user_id,
        scopes=["read", "write", "execute"],
    )
    return {"Authorization": f"Bearer {access_token}"}, user_id


class TestListServices:
    """Tests for GET /v1/services endpoint."""

    @pytest.mark.asyncio
    async def test_list_services_empty(self, client: AsyncClient, db: AsyncSession, auth_headers):
        """Test listing services when none exist."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="services_empty@example.com",
            password_hash="test_hash",
            name="Services Test User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.get("/v1/services", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        assert isinstance(data["services"], list)

    @pytest.mark.asyncio
    async def test_list_services_with_active_services(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test listing services returns active and degraded services."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="services_list@example.com",
            password_hash="test_hash",
            name="Services Test User",
            tier="free",
            status="active",
        )
        db.add(user)

        # Create test services
        math_service = Service(
            name="test_math",
            display_name="Test Math MCP",
            description="Test math service",
            url="http://math:8001",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(math_service)

        agent_service = Service(
            name="test_agent",
            display_name="Test Agent",
            description="Test agent service",
            url="http://agent:8002",
            credit_cost=Decimal("1.00"),
            tier_required="starter",
            status=ServiceStatus.DEGRADED.value,
        )
        db.add(agent_service)

        # Inactive service should not appear
        inactive_service = Service(
            name="test_inactive",
            display_name="Inactive Service",
            url="http://inactive:8003",
            credit_cost=Decimal("5.00"),
            tier_required="pro",
            status=ServiceStatus.INACTIVE.value,
        )
        db.add(inactive_service)

        await db.commit()

        response = await client.get("/v1/services", headers=headers)

        assert response.status_code == 200
        data = response.json()
        service_names = [s["name"] for s in data["services"]]
        assert "test_math" in service_names
        assert "test_agent" in service_names
        assert "test_inactive" not in service_names

    @pytest.mark.asyncio
    async def test_list_services_no_auth(self, client: AsyncClient):
        """Test listing services requires authentication."""
        response = await client.get("/v1/services")
        assert response.status_code == 401


class TestMathVerify:
    """Tests for POST /v1/services/math/verify endpoint."""

    @pytest.mark.asyncio
    async def test_math_verify_success(self, client: AsyncClient, db: AsyncSession, auth_headers):
        """Test successful math verification."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="math_verify@example.com",
            password_hash="test_hash",
            name="Math Test User",
            tier="free",
            status="active",
        )
        db.add(user)

        # Delete any existing math service to avoid conflicts
        await db.execute(delete(Service).where(Service.name == "math"))

        # Create math service
        math_service = Service(
            name="math",
            display_name="Math MCP",
            url="http://math:8001",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(math_service)
        await db.commit()

        # Mock the HTTP request to math service
        with patch("mcpworks_api.services.router.httpx.AsyncClient") as mock_client_class:
            from unittest.mock import MagicMock

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Use MagicMock for response since response.json() is synchronous
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "is_correct": True,
                "confidence": 0.95,
                "solution": "2 + 2 = 4 is correct",
                "correct_answer": "4",
                "model_used": "qwen2.5-math-1.5b",
            }
            mock_response.text = ""
            mock_response.headers = {"Content-Type": "application/json"}
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client

            response = await client.post(
                "/v1/services/math/verify",
                headers=headers,
                json={
                    "problem": "2 + 2 = 4",
                    "show_work": True,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_correct"] is True
            assert data["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_math_verify_service_unavailable(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test math verify returns 503 when service is unavailable."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="math_unavailable@example.com",
            password_hash="test_hash",
            name="Math Test User",
            tier="free",
            status="active",
        )
        db.add(user)

        # Delete any existing math service to avoid conflicts
        await db.execute(delete(Service).where(Service.name == "math"))

        # Create inactive math service
        math_service = Service(
            name="math",
            display_name="Math MCP",
            url="http://math:8001",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.INACTIVE.value,
        )
        db.add(math_service)
        await db.commit()

        response = await client.post(
            "/v1/services/math/verify",
            headers=headers,
            json={"problem": "2 + 2 = 4"},
        )

        assert response.status_code == 503
        data = response.json()
        assert data["error"] == "SERVICE_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_math_verify_no_service_registered(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test math verify returns 503 when no service is registered."""
        headers, user_id = auth_headers

        # Create user but NO service
        user = User(
            id=uuid.UUID(user_id),
            email="math_no_service@example.com",
            password_hash="test_hash",
            name="Math Test User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.post(
            "/v1/services/math/verify",
            headers=headers,
            json={"problem": "2 + 2 = 4"},
        )

        assert response.status_code == 503


class TestMathHelp:
    """Tests for POST /v1/services/math/help endpoint."""

    @pytest.mark.asyncio
    async def test_math_help_success(self, client: AsyncClient, db: AsyncSession, auth_headers):
        """Test successful math help request."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="math_help@example.com",
            password_hash="test_hash",
            name="Math Help User",
            tier="free",
            status="active",
        )
        db.add(user)

        # Delete any existing math service to avoid conflicts
        await db.execute(delete(Service).where(Service.name == "math"))

        # Create math service
        math_service = Service(
            name="math",
            display_name="Math MCP",
            url="http://math:8001",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(math_service)
        await db.commit()

        # Mock the HTTP request to math service
        with patch("mcpworks_api.services.router.httpx.AsyncClient") as mock_client_class:
            from unittest.mock import MagicMock

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Use MagicMock for response since response.json() is synchronous
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "answer": "To solve quadratic equations, use the quadratic formula...",
                "guidance_type": "explanation",
                "related_topics": ["algebra", "polynomials"],
            }
            mock_response.text = ""
            mock_response.headers = {"Content-Type": "application/json"}
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client

            response = await client.post(
                "/v1/services/math/help",
                headers=headers,
                json={
                    "question": "How do I solve quadratic equations?",
                    "guidance_type": "explanation",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert data["guidance_type"] == "explanation"


class TestServiceHealth:
    """Tests for GET /v1/services/{service_name}/health endpoint."""

    @pytest.mark.asyncio
    async def test_service_health_check_healthy(self, client: AsyncClient, db: AsyncSession):
        """Test health check for healthy service."""
        # Create service
        math_service = Service(
            name="math_health_test",
            display_name="Math MCP",
            url="http://math:8001",
            health_check_url="http://math:8001/health",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(math_service)
        await db.commit()

        # Mock the health check request
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            response = await client.get("/v1/services/math_health_test/health")

            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "math_health_test"
            assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_service_health_check_unhealthy(self, client: AsyncClient, db: AsyncSession):
        """Test health check for unhealthy service."""
        # Create service
        unhealthy_service = Service(
            name="unhealthy_test",
            display_name="Unhealthy Service",
            url="http://unhealthy:8001",
            health_check_url="http://unhealthy:8001/health",
            credit_cost=Decimal("0.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(unhealthy_service)
        await db.commit()

        # Mock the health check to fail
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = Exception("Connection refused")
            mock_client_class.return_value = mock_client

            response = await client.get("/v1/services/unhealthy_test/health")

            assert response.status_code == 503
            data = response.json()
            assert data["error"] == "SERVICE_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_service_health_check_not_found(self, client: AsyncClient):
        """Test health check for non-existent service."""
        response = await client.get("/v1/services/nonexistent/health")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "SERVICE_NOT_FOUND"

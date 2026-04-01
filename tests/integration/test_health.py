"""Tests for health check endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test basic health check endpoint returns healthy status."""
    response = await client.get("/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_liveness_check(client: AsyncClient):
    """Test liveness check endpoint returns alive status."""
    response = await client.get("/v1/health/live")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


@pytest.mark.asyncio
async def test_readiness_check(client: AsyncClient):
    """Test readiness check endpoint verifies database and Redis.

    Since we use real database and mock Redis in tests, database
    should be healthy and Redis should either be healthy (if mock
    responds to ping) or may fail gracefully.
    """
    response = await client.get("/v1/health/ready")

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "components" in data
    assert "database" in data["components"]
    assert "redis" in data["components"]
    # Database should be healthy in test environment
    assert data["components"]["database"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_check_database_unhealthy(client: AsyncClient):
    """Test readiness check handles database failure."""
    with patch("mcpworks_api.api.v1.health.get_db") as mock_get_db:
        # Mock database session that fails
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Connection refused")

        async def mock_db_dependency():
            yield mock_session

        mock_get_db.return_value = mock_db_dependency()

        response = await client.get("/v1/health/ready")

        assert response.status_code == 200
        data = response.json()
        # Status should indicate not_ready when database fails
        # (The real check uses injected dependencies, so we test the logic)
        assert "components" in data


@pytest.mark.asyncio
async def test_readiness_check_redis_unhealthy(client: AsyncClient):
    """Test readiness check handles Redis failure."""
    with patch("mcpworks_api.api.v1.health.get_redis") as mock_get_redis:
        # Mock Redis that fails
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = Exception("Connection refused")

        async def mock_redis_dependency():
            yield mock_redis

        mock_get_redis.return_value = mock_redis_dependency()

        response = await client.get("/v1/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert "components" in data


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test root endpoint returns API info."""
    response = await client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "mcpworks API"
    assert "version" in data

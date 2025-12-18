"""Tests for health check endpoints."""

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
async def test_root_endpoint(client: AsyncClient):
    """Test root endpoint returns API info."""
    response = await client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "mcpworks API"
    assert "version" in data

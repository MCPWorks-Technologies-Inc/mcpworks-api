"""Tests for LLM instruction endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_llm_instructions_returns_structure(client: AsyncClient):
    """Test LLM endpoint returns expected structure."""
    response = await client.get("/v1/llm")

    assert response.status_code == 200
    data = response.json()

    # Check top-level keys
    assert "api" in data
    assert "version" in data
    assert "auth" in data
    assert "endpoints" in data
    assert "mcp" in data
    assert "errors" in data
    assert "quick_start" in data


@pytest.mark.asyncio
async def test_llm_instructions_auth_section(client: AsyncClient):
    """Test auth section has required info."""
    response = await client.get("/v1/llm")
    data = response.json()

    auth = data["auth"]
    assert auth["method"] == "Bearer token"
    assert "Authorization" in auth["header"]
    assert "get_token" in auth


@pytest.mark.asyncio
async def test_llm_instructions_endpoints_section(client: AsyncClient):
    """Test endpoints section covers main areas."""
    response = await client.get("/v1/llm")
    data = response.json()

    endpoints = data["endpoints"]
    assert "account" in endpoints
    assert "credits" in endpoints
    assert "namespaces" in endpoints
    assert "functions" in endpoints


@pytest.mark.asyncio
async def test_llm_instructions_mcp_section(client: AsyncClient):
    """Test MCP section has endpoint patterns."""
    response = await client.get("/v1/llm")
    data = response.json()

    mcp = data["mcp"]
    assert "{namespace}" in mcp["create_endpoint"]
    assert "{namespace}" in mcp["run_endpoint"]
    assert "JSON-RPC" in mcp["protocol"]


@pytest.mark.asyncio
async def test_llm_instructions_quick_start(client: AsyncClient):
    """Test quick_start is a list of steps."""
    response = await client.get("/v1/llm")
    data = response.json()

    quick_start = data["quick_start"]
    assert isinstance(quick_start, list)
    assert len(quick_start) >= 3
    assert any("register" in step.lower() for step in quick_start)

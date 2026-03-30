"""Unit tests for PathRoutingMiddleware."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.datastructures import URL

from mcpworks_api.middleware.routing import (
    PathRoutingMiddleware,
    _NAMESPACE_RE,
    _VALID_ENDPOINTS,
)
from mcpworks_api.middleware.subdomain import EndpointType


class MockRequest:
    """Mock request for testing."""

    def __init__(self, path="/mcp/create/acme"):
        self.url = URL(f"http://test{path}")
        self.state = MagicMock()
        self.state.namespace = None
        self.state.endpoint_type = None
        self.state.is_local = None


class MockResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


class TestNamespaceRegex:
    """Tests for namespace validation regex."""

    def test_simple_namespace(self):
        assert _NAMESPACE_RE.match("acme")

    def test_numeric_namespace(self):
        assert _NAMESPACE_RE.match("ns123")

    def test_hyphenated_namespace(self):
        assert _NAMESPACE_RE.match("my-namespace")

    def test_single_char(self):
        assert _NAMESPACE_RE.match("a")

    def test_max_length_63(self):
        assert _NAMESPACE_RE.match("a" * 63)

    def test_too_long_64(self):
        assert not _NAMESPACE_RE.match("a" * 64)

    def test_uppercase_rejected(self):
        assert not _NAMESPACE_RE.match("UPPERCASE")

    def test_mixed_case_rejected(self):
        assert not _NAMESPACE_RE.match("camelCase")

    def test_leading_hyphen_rejected(self):
        assert not _NAMESPACE_RE.match("-starts-bad")

    def test_trailing_hyphen_rejected(self):
        assert not _NAMESPACE_RE.match("ends-bad-")

    def test_empty_rejected(self):
        assert not _NAMESPACE_RE.match("")

    def test_spaces_rejected(self):
        assert not _NAMESPACE_RE.match("has space")

    def test_dots_rejected(self):
        assert not _NAMESPACE_RE.match("has.dot")

    def test_underscores_rejected(self):
        assert not _NAMESPACE_RE.match("has_underscore")

    def test_slash_rejected(self):
        assert not _NAMESPACE_RE.match("has/slash")


class TestValidEndpoints:
    def test_valid_set(self):
        assert _VALID_ENDPOINTS == frozenset({"create", "run", "agent"})


class TestPathRoutingMiddlewareDispatch:
    """Tests for PathRoutingMiddleware.dispatch."""

    @pytest.fixture
    def middleware(self):
        return PathRoutingMiddleware(app=MagicMock())

    @pytest.mark.asyncio
    async def test_create_endpoint(self, middleware):
        request = MockRequest("/mcp/create/acme")
        call_next = AsyncMock(return_value=MockResponse(200))

        await middleware.dispatch(request, call_next)

        assert request.state.namespace == "acme"
        assert request.state.endpoint_type == EndpointType.CREATE
        assert request.state.is_local is False
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_endpoint(self, middleware):
        request = MockRequest("/mcp/run/myns")
        call_next = AsyncMock(return_value=MockResponse(200))

        await middleware.dispatch(request, call_next)

        assert request.state.namespace == "myns"
        assert request.state.endpoint_type == EndpointType.RUN

    @pytest.mark.asyncio
    async def test_agent_endpoint(self, middleware):
        request = MockRequest("/mcp/agent/mybot")
        call_next = AsyncMock(return_value=MockResponse(200))

        await middleware.dispatch(request, call_next)

        assert request.state.namespace == "mybot"
        assert request.state.endpoint_type == EndpointType.AGENT

    @pytest.mark.asyncio
    async def test_agent_webhook_subpath(self, middleware):
        request = MockRequest("/mcp/agent/mybot/webhook/github/push")
        call_next = AsyncMock(return_value=MockResponse(200))

        await middleware.dispatch(request, call_next)

        assert request.state.namespace == "mybot"
        assert request.state.endpoint_type == EndpointType.AGENT
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_chat_subpath(self, middleware):
        request = MockRequest("/mcp/agent/mybot/chat/tok123abc")
        call_next = AsyncMock(return_value=MockResponse(200))

        await middleware.dispatch(request, call_next)

        assert request.state.namespace == "mybot"
        assert request.state.endpoint_type == EndpointType.AGENT

    @pytest.mark.asyncio
    async def test_agent_view_subpath(self, middleware):
        request = MockRequest("/mcp/agent/mybot/view/tok123/")
        call_next = AsyncMock(return_value=MockResponse(200))

        await middleware.dispatch(request, call_next)

        assert request.state.namespace == "mybot"
        assert request.state.endpoint_type == EndpointType.AGENT

    @pytest.mark.asyncio
    async def test_passes_through_non_mcp_paths(self, middleware):
        request = MockRequest("/v1/health")
        call_next = AsyncMock(return_value=MockResponse(200))

        await middleware.dispatch(request, call_next)

        assert request.state.namespace is None
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_through_root(self, middleware):
        request = MockRequest("/")
        call_next = AsyncMock(return_value=MockResponse(200))

        await middleware.dispatch(request, call_next)

        assert request.state.namespace is None
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_through_mcp_root(self, middleware):
        """GET /mcp (discovery) should pass through — only 2 segments."""
        request = MockRequest("/mcp")
        call_next = AsyncMock(return_value=MockResponse(200))

        await middleware.dispatch(request, call_next)

        assert request.state.namespace is None
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_through_mcp_with_endpoint_no_ns(self, middleware):
        """/mcp/create has only 3 segments — no namespace."""
        request = MockRequest("/mcp/create")
        call_next = AsyncMock(return_value=MockResponse(200))

        await middleware.dispatch(request, call_next)

        assert request.state.namespace is None
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_endpoint_raises_404(self, middleware):
        from fastapi import HTTPException

        request = MockRequest("/mcp/invalid/acme")
        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["code"] == "INVALID_ENDPOINT"
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_namespace_raises_400(self, middleware):
        from fastapi import HTTPException

        request = MockRequest("/mcp/create/UPPERCASE")
        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_NAMESPACE"
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_namespace_with_leading_hyphen_raises(self, middleware):
        from fastapi import HTTPException

        request = MockRequest("/mcp/create/-bad")
        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_hyphenated_namespace_works(self, middleware):
        request = MockRequest("/mcp/create/my-namespace")
        call_next = AsyncMock(return_value=MockResponse(200))

        await middleware.dispatch(request, call_next)

        assert request.state.namespace == "my-namespace"
        assert request.state.endpoint_type == EndpointType.CREATE

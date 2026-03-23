"""Unit tests for SubdomainMiddleware."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.datastructures import URL, Headers, QueryParams

from mcpworks_api.middleware.subdomain import (
    EndpointType,
    SubdomainMiddleware,
    get_endpoint_type,
    get_namespace,
    is_create_endpoint,
    is_run_endpoint,
)

DEFAULT_DOMAIN = "mcpworks.io"
_dummy_app = AsyncMock()
_mw = SubdomainMiddleware(_dummy_app, domain=DEFAULT_DOMAIN)
SUBDOMAIN_PATTERN = _mw.subdomain_pattern


class MockRequest:
    """Mock request for testing."""

    def __init__(self, path="/mcp", host="localhost:8000", query_params=None):
        self.url = URL(f"http://test{path}")
        self.headers = Headers({"host": host})
        self.query_params = QueryParams(query_params or {})
        self.state = MagicMock()
        # Clear state attributes
        self.state.namespace = None
        self.state.endpoint_type = None
        self.state.is_local = None


class MockResponse:
    """Mock response for testing."""

    def __init__(self, status_code=200):
        self.status_code = status_code


@pytest.fixture
def subdomain_middleware():
    """Create subdomain middleware instance."""
    return SubdomainMiddleware(app=MagicMock())


class TestSubdomainPattern:
    """Tests for SUBDOMAIN_PATTERN regex."""

    def test_pattern_matches_valid_create_endpoint(self):
        """Test pattern matches create endpoint."""
        match = SUBDOMAIN_PATTERN.match("acme.create.mcpworks.io")
        assert match is not None
        assert match.group("namespace") == "acme"
        assert match.group("endpoint") == "create"
        assert match.group("domain") == "mcpworks.io"

    def test_pattern_matches_valid_run_endpoint(self):
        """Test pattern matches run endpoint."""
        match = SUBDOMAIN_PATTERN.match("acme.run.mcpworks.io")
        assert match is not None
        assert match.group("namespace") == "acme"
        assert match.group("endpoint") == "run"

    def test_pattern_matches_hyphenated_namespace(self):
        """Test pattern matches namespace with hyphens."""
        match = SUBDOMAIN_PATTERN.match("my-company-namespace.create.mcpworks.io")
        assert match is not None
        assert match.group("namespace") == "my-company-namespace"

    def test_pattern_matches_numeric_namespace(self):
        """Test pattern matches namespace with numbers."""
        match = SUBDOMAIN_PATTERN.match("acme123.run.mcpworks.io")
        assert match is not None
        assert match.group("namespace") == "acme123"

    def test_pattern_rejects_invalid_endpoint(self):
        """Test pattern rejects invalid endpoint."""
        match = SUBDOMAIN_PATTERN.match("acme.invalid.mcpworks.io")
        assert match is None

    def test_pattern_rejects_missing_endpoint(self):
        """Test pattern rejects missing endpoint."""
        match = SUBDOMAIN_PATTERN.match("acme.mcpworks.io")
        assert match is None

    def test_pattern_rejects_uppercase(self):
        """Test pattern rejects uppercase characters."""
        match = SUBDOMAIN_PATTERN.match("ACME.create.mcpworks.io")
        assert match is None

    def test_pattern_rejects_starting_hyphen(self):
        """Test pattern rejects namespace starting with hyphen."""
        match = SUBDOMAIN_PATTERN.match("-acme.create.mcpworks.io")
        assert match is None

    def test_pattern_rejects_ending_hyphen(self):
        """Test pattern rejects namespace ending with hyphen."""
        match = SUBDOMAIN_PATTERN.match("acme-.create.mcpworks.io")
        assert match is None

    def test_pattern_matches_localhost(self):
        """Test pattern matches localhost domain."""
        match = SUBDOMAIN_PATTERN.match("acme.create.localhost")
        assert match is not None
        assert match.group("domain") == "localhost"

    def test_pattern_matches_127_0_0_1_with_port(self):
        """Test pattern matches 127.0.0.1 with port."""
        match = SUBDOMAIN_PATTERN.match("acme.create.127.0.0.1:8000")
        assert match is not None
        assert match.group("domain") == "127.0.0.1:8000"


class TestEndpointType:
    """Tests for EndpointType enum."""

    def test_create_value(self):
        """Test CREATE enum value."""
        assert EndpointType.CREATE.value == "create"

    def test_run_value(self):
        """Test RUN enum value."""
        assert EndpointType.RUN.value == "run"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        assert EndpointType("create") == EndpointType.CREATE
        assert EndpointType("run") == EndpointType.RUN


class TestSubdomainMiddlewareInit:
    """Tests for SubdomainMiddleware initialization."""

    def test_default_domain(self):
        """Test default domain is mcpworks.io."""
        assert DEFAULT_DOMAIN == "mcpworks.io"

    def test_custom_domain(self):
        """Test custom domain can be set."""
        middleware = SubdomainMiddleware(app=MagicMock(), domain="custom.io")
        assert middleware.domain == "custom.io"

    def test_default_exempt_paths(self, subdomain_middleware):
        """Test default exempt paths."""
        assert "/" in subdomain_middleware.exempt_paths
        assert "/health" in subdomain_middleware.exempt_paths
        assert "/health/ready" in subdomain_middleware.exempt_paths
        assert "/health/live" in subdomain_middleware.exempt_paths
        assert "/metrics" in subdomain_middleware.exempt_paths
        assert "/docs" in subdomain_middleware.exempt_paths
        assert "/redoc" in subdomain_middleware.exempt_paths
        assert "/openapi.json" in subdomain_middleware.exempt_paths

    def test_custom_exempt_paths(self):
        """Test custom exempt paths."""
        middleware = SubdomainMiddleware(app=MagicMock(), exempt_paths={"/custom", "/paths"})
        assert middleware.exempt_paths == {"/custom", "/paths"}


class TestSubdomainMiddlewareDispatch:
    """Tests for dispatch method."""

    @pytest.mark.asyncio
    async def test_dispatch_skips_exempt_paths(self, subdomain_middleware):
        """Test that exempt paths skip subdomain processing."""
        request = MockRequest(path="/health")
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await subdomain_middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_skips_root_path(self, subdomain_middleware):
        """Test that root path skips subdomain processing."""
        request = MockRequest(path="/")
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await subdomain_middleware.dispatch(request, call_next)

        call_next.assert_called_once()
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_skips_v1_api_paths(self, subdomain_middleware):
        """Test that /v1/ paths skip subdomain processing."""
        request = MockRequest(path="/v1/auth/token")
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await subdomain_middleware.dispatch(request, call_next)

        call_next.assert_called_once()
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_localhost_uses_query_params(self, subdomain_middleware):
        """Test that localhost uses query parameters."""
        request = MockRequest(
            path="/mcp",
            host="localhost:8000",
            query_params={"namespace": "testns", "endpoint": "create"},
        )
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await subdomain_middleware.dispatch(request, call_next)

        assert request.state.namespace == "testns"
        assert request.state.endpoint_type == EndpointType.CREATE
        assert request.state.is_local is True
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_localhost_default_values(self, subdomain_middleware):
        """Test localhost defaults when query params missing."""
        request = MockRequest(path="/mcp", host="localhost:8000")
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await subdomain_middleware.dispatch(request, call_next)

        assert request.state.namespace == "default"
        assert request.state.endpoint_type == EndpointType.CREATE
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_localhost_run_endpoint(self, subdomain_middleware):
        """Test localhost with run endpoint."""
        request = MockRequest(
            path="/mcp",
            host="127.0.0.1:8000",
            query_params={"namespace": "myns", "endpoint": "run"},
        )
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await subdomain_middleware.dispatch(request, call_next)

        assert request.state.namespace == "myns"
        assert request.state.endpoint_type == EndpointType.RUN
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_localhost_invalid_endpoint_raises(self, subdomain_middleware):
        """Test that invalid endpoint on localhost raises 400."""
        from fastapi import HTTPException

        request = MockRequest(
            path="/mcp",
            host="localhost:8000",
            query_params={"namespace": "test", "endpoint": "invalid"},
        )
        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await subdomain_middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_ENDPOINT"
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_production_extracts_subdomain(self, subdomain_middleware):
        """Test production host extracts subdomain info."""
        request = MockRequest(path="/mcp", host="acme.create.mcpworks.io")
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await subdomain_middleware.dispatch(request, call_next)

        assert request.state.namespace == "acme"
        assert request.state.endpoint_type == EndpointType.CREATE
        assert request.state.is_local is False
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_production_run_endpoint(self, subdomain_middleware):
        """Test production run endpoint extraction."""
        request = MockRequest(path="/mcp", host="mycompany.run.mcpworks.io")
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await subdomain_middleware.dispatch(request, call_next)

        assert request.state.namespace == "mycompany"
        assert request.state.endpoint_type == EndpointType.RUN
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_invalid_host_raises(self, subdomain_middleware):
        """Test that invalid host raises 400."""
        from fastapi import HTTPException

        request = MockRequest(path="/mcp", host="invalid.host.example.com")
        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await subdomain_middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_HOST"


class TestIsLocalHost:
    """Tests for _is_local_host method."""

    def test_localhost(self, subdomain_middleware):
        """Test localhost is recognized."""
        assert subdomain_middleware._is_local_host("localhost") is True

    def test_localhost_with_port(self, subdomain_middleware):
        """Test localhost with port is recognized."""
        assert subdomain_middleware._is_local_host("localhost:8000") is True

    def test_127_0_0_1(self, subdomain_middleware):
        """Test 127.0.0.1 is recognized."""
        assert subdomain_middleware._is_local_host("127.0.0.1") is True

    def test_127_0_0_1_with_port(self, subdomain_middleware):
        """Test 127.0.0.1 with port is recognized."""
        assert subdomain_middleware._is_local_host("127.0.0.1:8000") is True

    def test_0_0_0_0(self, subdomain_middleware):
        """Test 0.0.0.0 is recognized."""
        assert subdomain_middleware._is_local_host("0.0.0.0") is True

    def test_any_host_with_8000(self, subdomain_middleware):
        """Test any host with :8000 is recognized."""
        assert subdomain_middleware._is_local_host("example.com:8000") is True

    def test_production_host(self, subdomain_middleware):
        """Test production host is not local."""
        assert subdomain_middleware._is_local_host("acme.create.mcpworks.io") is False


class TestGetNamespace:
    """Tests for get_namespace helper function."""

    def test_get_namespace_returns_value(self):
        """Test get_namespace returns namespace from state."""
        request = MagicMock()
        request.state.namespace = "testns"

        result = get_namespace(request)

        assert result == "testns"

    def test_get_namespace_raises_when_not_set(self):
        """Test get_namespace raises when namespace not set."""
        from fastapi import HTTPException

        request = MagicMock()
        request.state.namespace = None

        with pytest.raises(HTTPException) as exc_info:
            get_namespace(request)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["code"] == "INTERNAL_ERROR"


class TestGetEndpointType:
    """Tests for get_endpoint_type helper function."""

    def test_get_endpoint_type_returns_value(self):
        """Test get_endpoint_type returns endpoint from state."""
        request = MagicMock()
        request.state.endpoint_type = EndpointType.CREATE

        result = get_endpoint_type(request)

        assert result == EndpointType.CREATE

    def test_get_endpoint_type_raises_when_not_set(self):
        """Test get_endpoint_type raises when not set."""
        from fastapi import HTTPException

        request = MagicMock()
        request.state.endpoint_type = None

        with pytest.raises(HTTPException) as exc_info:
            get_endpoint_type(request)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["code"] == "INTERNAL_ERROR"


class TestIsCreateEndpoint:
    """Tests for is_create_endpoint helper function."""

    def test_is_create_endpoint_true(self):
        """Test is_create_endpoint returns True for create."""
        request = MagicMock()
        request.state.endpoint_type = EndpointType.CREATE

        assert is_create_endpoint(request) is True

    def test_is_create_endpoint_false(self):
        """Test is_create_endpoint returns False for run."""
        request = MagicMock()
        request.state.endpoint_type = EndpointType.RUN

        assert is_create_endpoint(request) is False


class TestIsRunEndpoint:
    """Tests for is_run_endpoint helper function."""

    def test_is_run_endpoint_true(self):
        """Test is_run_endpoint returns True for run."""
        request = MagicMock()
        request.state.endpoint_type = EndpointType.RUN

        assert is_run_endpoint(request) is True

    def test_is_run_endpoint_false(self):
        """Test is_run_endpoint returns False for create."""
        request = MagicMock()
        request.state.endpoint_type = EndpointType.CREATE

        assert is_run_endpoint(request) is False

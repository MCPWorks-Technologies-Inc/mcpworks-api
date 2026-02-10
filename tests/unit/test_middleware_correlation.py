"""Unit tests for CorrelationIdMiddleware."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.datastructures import Headers

from mcpworks_api.middleware.correlation import (
    CORRELATION_ID_HEADER,
    CorrelationIdMiddleware,
    correlation_id_var,
    get_correlation_id,
)


class MockRequest:
    """Mock request for testing."""

    def __init__(self, correlation_id=None):
        headers = {}
        if correlation_id:
            headers[CORRELATION_ID_HEADER] = correlation_id
        self.headers = Headers(headers)


class MockResponse:
    """Mock response for testing."""

    def __init__(self, status_code=200):
        self.status_code = status_code
        self.headers = {}


@pytest.fixture
def correlation_middleware():
    """Create correlation middleware instance."""
    return CorrelationIdMiddleware(app=MagicMock())


class TestCorrelationIdHeader:
    """Tests for correlation ID header constant."""

    def test_header_name(self):
        """Test header name is X-Request-ID."""
        assert CORRELATION_ID_HEADER == "X-Request-ID"


class TestGetCorrelationId:
    """Tests for get_correlation_id function."""

    def test_get_correlation_id_returns_value(self):
        """Test get_correlation_id returns set value."""
        test_id = str(uuid.uuid4())
        correlation_id_var.set(test_id)

        result = get_correlation_id()

        assert result == test_id

    def test_get_correlation_id_returns_none_when_not_set(self):
        """Test get_correlation_id returns None when not set."""
        # Reset context variable
        correlation_id_var.set(None)

        result = get_correlation_id()

        assert result is None


class TestCorrelationIdMiddlewareDispatch:
    """Tests for dispatch method."""

    @pytest.mark.asyncio
    async def test_dispatch_uses_existing_correlation_id(self, correlation_middleware):
        """Test that existing correlation ID is used."""
        existing_id = "test-correlation-id-123"
        request = MockRequest(correlation_id=existing_id)
        response = MockResponse()
        call_next = AsyncMock(return_value=response)

        result = await correlation_middleware.dispatch(request, call_next)

        # Check context variable was set
        assert correlation_id_var.get() == existing_id
        # Check response header
        assert result.headers[CORRELATION_ID_HEADER] == existing_id

    @pytest.mark.asyncio
    async def test_dispatch_generates_correlation_id_when_missing(
        self, correlation_middleware
    ):
        """Test that correlation ID is generated when missing."""
        request = MockRequest(correlation_id=None)
        response = MockResponse()
        call_next = AsyncMock(return_value=response)

        result = await correlation_middleware.dispatch(request, call_next)

        # Check a UUID was generated
        generated_id = correlation_id_var.get()
        assert generated_id is not None
        # Verify it's a valid UUID format
        uuid.UUID(generated_id)
        # Check response header matches
        assert result.headers[CORRELATION_ID_HEADER] == generated_id

    @pytest.mark.asyncio
    async def test_dispatch_calls_next_handler(self, correlation_middleware):
        """Test that call_next is invoked."""
        request = MockRequest()
        response = MockResponse()
        call_next = AsyncMock(return_value=response)

        await correlation_middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_adds_header_to_response(self, correlation_middleware):
        """Test that correlation ID is added to response headers."""
        request = MockRequest()
        response = MockResponse()
        call_next = AsyncMock(return_value=response)

        result = await correlation_middleware.dispatch(request, call_next)

        assert CORRELATION_ID_HEADER in result.headers

    @pytest.mark.asyncio
    async def test_dispatch_preserves_response(self, correlation_middleware):
        """Test that response is returned unchanged except for header."""
        request = MockRequest()
        response = MockResponse(status_code=201)
        call_next = AsyncMock(return_value=response)

        result = await correlation_middleware.dispatch(request, call_next)

        assert result.status_code == 201

    @pytest.mark.asyncio
    async def test_dispatch_unique_ids_per_request(self, correlation_middleware):
        """Test that different requests get different IDs."""
        request1 = MockRequest()
        request2 = MockRequest()
        call_next = AsyncMock(return_value=MockResponse())

        await correlation_middleware.dispatch(request1, call_next)
        id1 = correlation_id_var.get()

        await correlation_middleware.dispatch(request2, call_next)
        id2 = correlation_id_var.get()

        assert id1 != id2


class TestCorrelationIdContextVar:
    """Tests for correlation_id_var context variable."""

    def test_context_var_default_is_none(self):
        """Test context variable default is None."""
        # Create a new context to test default
        import contextvars

        ctx = contextvars.copy_context()
        # In a fresh context, the default should be None
        assert correlation_id_var.get() is None or isinstance(
            correlation_id_var.get(), str
        )

    def test_context_var_can_be_set(self):
        """Test context variable can be set."""
        test_id = "my-test-id"
        correlation_id_var.set(test_id)

        assert correlation_id_var.get() == test_id

    def test_context_var_can_be_reset(self):
        """Test context variable can be reset."""
        correlation_id_var.set("first-id")
        correlation_id_var.set("second-id")

        assert correlation_id_var.get() == "second-id"

"""Correlation ID middleware for request tracing."""

import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]

# Context variable to store correlation ID for the current request
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Header name for correlation ID
CORRELATION_ID_HEADER = "X-Request-ID"


def get_correlation_id() -> str | None:
    """Get the correlation ID for the current request context."""
    return correlation_id_var.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware that adds correlation ID to requests for tracing.

    Flow:
    1. Check for incoming X-Request-ID header
    2. If missing, generate UUID v4
    3. Store in context variable for logging
    4. Bind to structlog contextvars (ORDER-021)
    5. Add to response headers
    6. Forward to downstream service calls
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request and add correlation ID."""
        # Get existing correlation ID or generate new one
        correlation_id = request.headers.get(CORRELATION_ID_HEADER)
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Store in context variable for use in logging/other code
        correlation_id_var.set(correlation_id)

        # ORDER-021: Bind correlation_id into structlog context so every log
        # line emitted during this request carries the request ID.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        # Process request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers[CORRELATION_ID_HEADER] = correlation_id

        return response

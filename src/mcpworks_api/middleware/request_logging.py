"""ORDER-021: Structured per-request logging middleware."""

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("mcpworks.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit a single structured log entry per request.

    Fields: method, path, status, duration_ms, namespace, endpoint_type,
    account_id, request_size, response_size.

    Skips health checks and metrics to keep logs focused.
    """

    SKIP_PATHS = frozenset({
        "/v1/health",
        "/v1/health/live",
        "/v1/health/ready",
        "/metrics",
    })

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        namespace = getattr(request.state, "namespace", None)
        endpoint_type = getattr(request.state, "endpoint_type", None)
        account = getattr(request.state, "account", None)
        account_id = str(account.id) if account and hasattr(account, "id") else None

        request_size = int(request.headers.get("content-length", 0))
        response_size = int(response.headers.get("content-length", 0))

        log = logger.info if response.status_code < 400 else logger.warning
        log(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            namespace=namespace,
            endpoint_type=str(endpoint_type) if endpoint_type else None,
            account_id=account_id,
            request_bytes=request_size,
            response_bytes=response_size,
        )

        return response

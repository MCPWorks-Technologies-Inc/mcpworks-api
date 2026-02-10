"""Subdomain middleware for namespace and endpoint type extraction.

Parse Host header to extract namespace and endpoint type.

Examples:
  acme.create.mcpworks.io → namespace="acme", endpoint="create"
  acme.run.mcpworks.io → namespace="acme", endpoint="run"
"""

import re
from enum import Enum

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

# Configurable domain for testing
# In production: mcpworks.io
# In testing: localhost, 127.0.0.1, or custom domain
DEFAULT_DOMAIN = "mcpworks.io"

# Pattern for production subdomain matching
# Format: {namespace}.{endpoint}.mcpworks.io
# Where:
#   - namespace: 1-63 chars, lowercase alphanumeric with hyphens, starts/ends with alphanum
#   - endpoint: "create" or "run"
SUBDOMAIN_PATTERN = re.compile(
    r"^(?P<namespace>[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)"
    r"\.(?P<endpoint>create|run)"
    r"\.(?P<domain>mcpworks\.io|localhost|127\.0\.0\.1(?::\d+)?)$"
)


class EndpointType(str, Enum):
    """MCP endpoint types."""

    CREATE = "create"  # Management endpoint (CRUD operations)
    RUN = "run"  # Execution endpoint (function invocation)


class SubdomainMiddleware(BaseHTTPMiddleware):
    """Extract namespace and endpoint type from Host header.

    Sets the following on request.state:
    - namespace: The namespace name (e.g., "acme")
    - endpoint_type: The endpoint type ("create" or "run")

    For local development (localhost/127.0.0.1), uses query parameters:
    - ?namespace=acme&endpoint=create

    Raises HTTPException 400 for invalid host format.
    """

    def __init__(
        self,
        app,
        domain: str = DEFAULT_DOMAIN,
        exempt_paths: set[str] | None = None,
    ):
        """Initialize subdomain middleware.

        Args:
            app: The ASGI application.
            domain: The expected domain (default: mcpworks.io).
            exempt_paths: Paths to skip subdomain checking (e.g., /health).
        """
        super().__init__(app)
        self.domain = domain
        self.exempt_paths = exempt_paths or {
            "/",
            "/health",
            "/health/ready",
            "/health/live",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request and extract subdomain information."""
        # Skip exempt paths
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        # Also skip paths starting with /v1/ (existing REST API)
        if request.url.path.startswith("/v1/"):
            return await call_next(request)

        host = request.headers.get("host", "").lower()

        # Handle local development
        if self._is_local_host(host):
            namespace = request.query_params.get("namespace", "default")
            endpoint = request.query_params.get("endpoint", "create")

            if endpoint not in ("create", "run"):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "INVALID_ENDPOINT",
                        "message": f"Invalid endpoint: {endpoint}. Must be 'create' or 'run'",
                    },
                )

            request.state.namespace = namespace
            request.state.endpoint_type = EndpointType(endpoint)
            request.state.is_local = True
            return await call_next(request)

        # Parse production subdomain
        match = SUBDOMAIN_PATTERN.match(host)
        if not match:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_HOST",
                    "message": f"Invalid host: {host}. Expected {{namespace}}.{{create|run}}.{self.domain}",
                },
            )

        request.state.namespace = match.group("namespace")
        request.state.endpoint_type = EndpointType(match.group("endpoint"))
        request.state.is_local = False

        return await call_next(request)

    def _is_local_host(self, host: str) -> bool:
        """Check if host is a local development address."""
        return (
            host.startswith("localhost")
            or host.startswith("127.0.0.1")
            or host.startswith("0.0.0.0")
            or ":8000" in host  # Common dev port
        )


def get_namespace(request: Request) -> str:
    """Get namespace from request state.

    Helper function for route handlers.

    Raises:
        HTTPException: If namespace not set (middleware not applied).
    """
    namespace = getattr(request.state, "namespace", None)
    if not namespace:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "Namespace not set. SubdomainMiddleware may not be applied.",
            },
        )
    return namespace


def get_endpoint_type(request: Request) -> EndpointType:
    """Get endpoint type from request state.

    Helper function for route handlers.

    Raises:
        HTTPException: If endpoint_type not set (middleware not applied).
    """
    endpoint_type = getattr(request.state, "endpoint_type", None)
    if not endpoint_type:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "Endpoint type not set. SubdomainMiddleware may not be applied.",
            },
        )
    return endpoint_type


def is_create_endpoint(request: Request) -> bool:
    """Check if this is a create (management) endpoint."""
    return get_endpoint_type(request) == EndpointType.CREATE


def is_run_endpoint(request: Request) -> bool:
    """Check if this is a run (execution) endpoint."""
    return get_endpoint_type(request) == EndpointType.RUN

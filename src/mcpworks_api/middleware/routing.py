"""Path-based routing middleware for namespace and endpoint type extraction.

Parse URL path to extract namespace and endpoint type.

Examples:
  /mcp/create/acme → namespace="acme", endpoint="create"
  /mcp/run/acme    → namespace="acme", endpoint="run"
  /mcp/agent/mybot → namespace="acme", endpoint="agent"
  /mcp/agent/mybot/webhook/github/push → namespace="mybot", endpoint="agent"
"""

import re

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from mcpworks_api.middleware.subdomain import EndpointType

_VALID_ENDPOINTS = frozenset({"create", "run", "agent"})
_NAMESPACE_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class PathRoutingMiddleware(BaseHTTPMiddleware):
    """Extract namespace and endpoint type from URL path.

    Matches paths like:
      /mcp/{endpoint}/{namespace}         — MCP protocol (create/run/agent)
      /mcp/agent/{namespace}/webhook/...  — agent webhook ingress
      /mcp/agent/{namespace}/chat/...     — agent public chat
      /mcp/agent/{namespace}/view/...     — agent scratchpad view

    Sets the following on request.state:
    - namespace: The namespace name (e.g., "acme")
    - endpoint_type: The endpoint type ("create", "run", or "agent")
    - is_local: Always False (path routing doesn't distinguish)

    Passes through requests that don't start with /mcp/.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        if not path.startswith("/mcp/"):
            return await call_next(request)

        segments = path.split("/")
        # segments[0] = "", segments[1] = "mcp", segments[2] = endpoint, segments[3] = namespace, ...
        if len(segments) < 4:
            return await call_next(request)

        endpoint = segments[2]
        namespace = segments[3]

        if endpoint not in _VALID_ENDPOINTS:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "INVALID_ENDPOINT",
                    "message": f"Invalid endpoint '{endpoint}'. Must be one of: create, run, agent",
                },
            )

        if not namespace or not _NAMESPACE_RE.match(namespace):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_NAMESPACE",
                    "message": f"Invalid namespace '{namespace}'. Must match [a-z0-9]([a-z0-9-]{{0,61}}[a-z0-9])?",
                },
            )

        request.state.namespace = namespace
        request.state.endpoint_type = EndpointType(endpoint)
        request.state.is_local = False

        return await call_next(request)

"""MCP Streamable HTTP transport using the MCP Python SDK.

Replaces the custom JSON-RPC handler with the SDK's StreamableHTTPSessionManager
for native MCP protocol support (compatible with Claude Code's ``type: "http"``).

A single shared ``mcp.server.Server`` instance runs in **stateless mode** — each
POST creates a fresh transport session.  Per-request context (namespace, endpoint
type, auth) is threaded into handlers via a ``ContextVar`` that stores the
Starlette ``Request`` whose ``state`` was already populated by
``SubdomainMiddleware``.
"""

import contextvars
import logging
from typing import Any

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool
from starlette.requests import Request

from mcpworks_api.core.database import get_db_context
from mcpworks_api.mcp.create_handler import CreateMCPHandler
from mcpworks_api.mcp.protocol import MCPTool
from mcpworks_api.mcp.run_handler import RunMCPHandler
from mcpworks_api.middleware.subdomain import EndpointType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ORDER-017: Token savings measurement — Prometheus instrumentation
# ---------------------------------------------------------------------------
try:
    from prometheus_client import Counter, Histogram

    mcp_tool_calls_total = Counter(
        "mcpworks_mcp_tool_calls_total",
        "Total MCP tool calls",
        ["endpoint_type", "tool_name"],
    )
    mcp_response_bytes = Histogram(
        "mcpworks_mcp_response_bytes",
        "MCP tool response size in bytes (proxy for token usage)",
        ["endpoint_type", "tool_name"],
        buckets=[100, 250, 500, 1000, 2500, 5000, 10000, 50000],
    )
except ImportError:
    mcp_tool_calls_total = None  # type: ignore[assignment]
    mcp_response_bytes = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# ContextVar – set by the ASGI wrapper, read by MCP handlers
# ---------------------------------------------------------------------------
_current_request: contextvars.ContextVar[Request | None] = contextvars.ContextVar(
    "_current_request", default=None
)

# ---------------------------------------------------------------------------
# MCP server + session manager (module-level singletons)
# ---------------------------------------------------------------------------
mcp_server = Server("mcpworks")
session_manager = StreamableHTTPSessionManager(mcp_server, stateless=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_sdk_tools(tools: list[MCPTool]) -> list[Tool]:
    """Convert internal MCPTool Pydantic models to MCP SDK Tool objects."""
    return [Tool(name=t.name, description=t.description, inputSchema=t.inputSchema) for t in tools]


async def _authenticate(request: Request, db: Any) -> Any:
    """Authenticate request via API key, returning the Account.

    Raises ``ValueError`` on auth failure so the MCP SDK can surface
    the error to the client.
    """
    from fastapi import HTTPException

    from mcpworks_api.mcp.router import get_account_from_api_key

    try:
        return await get_account_from_api_key(request, db)
    except HTTPException as e:
        raise ValueError(f"Authentication failed: {e.detail}") from e


# ---------------------------------------------------------------------------
# MCP handler: tools/list
# ---------------------------------------------------------------------------
@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """Return available tools based on namespace and endpoint type."""
    request = _current_request.get()
    if not request:
        return []

    namespace = getattr(request.state, "namespace", None)
    endpoint_type = getattr(request.state, "endpoint_type", None)
    if not namespace or not endpoint_type:
        return []

    try:
        async with get_db_context() as db:
            account = await _authenticate(request, db)

            if endpoint_type == EndpointType.CREATE:
                return _to_sdk_tools(CreateMCPHandler.get_tools())
            else:
                run_mode = request.query_params.get("mode", "code")
                handler = RunMCPHandler(namespace=namespace, account=account, db=db, mode=run_mode)
                return _to_sdk_tools(await handler.get_tools())
    except Exception as e:
        logger.error("list_tools error: %s", e, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# MCP handler: tools/call
# ---------------------------------------------------------------------------
@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    """Dispatch a tool invocation to the appropriate handler."""
    request = _current_request.get()
    if not request:
        raise ValueError("No request context available")

    namespace = getattr(request.state, "namespace", None)
    endpoint_type = getattr(request.state, "endpoint_type", None)
    if not namespace or not endpoint_type:
        raise ValueError(
            "Missing namespace or endpoint type. Use {namespace}.{create|run}.mcpworks.io"
        )

    args = arguments or {}

    async with get_db_context() as db:
        account = await _authenticate(request, db)

        if endpoint_type == EndpointType.CREATE:
            handler = CreateMCPHandler(namespace=namespace, account=account, db=db)
        else:
            run_mode = request.query_params.get("mode", "code")
            handler = RunMCPHandler(namespace=namespace, account=account, db=db, mode=run_mode)

        result = await handler.dispatch_tool(name, args)
        contents = [TextContent(type="text", text=c.text) for c in result.content]

        # ORDER-017: Record token metrics
        if mcp_tool_calls_total is not None:
            ep = endpoint_type.value if hasattr(endpoint_type, "value") else str(endpoint_type)
            mcp_tool_calls_total.labels(endpoint_type=ep, tool_name=name).inc()
            total_bytes = sum(len(c.text.encode()) for c in contents)
            mcp_response_bytes.labels(endpoint_type=ep, tool_name=name).observe(total_bytes)

        return contents


# ---------------------------------------------------------------------------
# ASGI middleware – intercepts /mcp before Starlette routing (avoids 307 redirect)
# ---------------------------------------------------------------------------
class MCPTransportMiddleware:
    """ASGI middleware that intercepts ``/mcp`` requests for MCP transport.

    Added as the innermost middleware so that SubdomainMiddleware, RateLimit,
    and Billing have already run.  Handles POST/GET/DELETE at ``/mcp``
    directly via the SDK session manager, bypassing Starlette's ``Mount``
    redirect from ``/mcp`` → ``/mcp/``.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope.get("path", "") in ("/mcp", "/mcp/"):
            request = Request(scope, receive, send)
            token = _current_request.set(request)
            try:
                # Session manager expects root-relative path
                inner_scope = dict(scope)
                inner_scope["path"] = "/"
                await session_manager.handle_request(inner_scope, receive, send)
            finally:
                _current_request.reset(token)
        else:
            await self.app(scope, receive, send)

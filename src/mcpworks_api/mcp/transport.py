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
from typing import Any

import structlog
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool
from sqlalchemy import update as sa_update
from starlette.requests import Request

from mcpworks_api.core.database import get_db_context
from mcpworks_api.mcp.create_handler import CreateMCPHandler
from mcpworks_api.mcp.env_passthrough import EnvPassthroughError, extract_env_vars
from mcpworks_api.mcp.protocol import MCPTool
from mcpworks_api.mcp.run_handler import RunMCPHandler
from mcpworks_api.middleware.subdomain import EndpointType
from mcpworks_api.models.function import Function
from mcpworks_api.models.namespace import Namespace
from mcpworks_api.models.namespace_service import NamespaceService

logger = structlog.get_logger(__name__)

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
    env_passthrough_requests_total = Counter(
        "mcpworks_env_passthrough_requests_total",
        "Requests with X-MCPWorks-Env header present",
    )
    env_passthrough_vars_count = Histogram(
        "mcpworks_env_passthrough_vars_count",
        "Number of env vars per request",
        buckets=[0, 1, 2, 5, 10, 20, 50, 64],
    )
    env_passthrough_errors_total = Counter(
        "mcpworks_env_passthrough_errors_total",
        "Env passthrough validation errors",
        ["error_type"],
    )
except ImportError:
    mcp_tool_calls_total = None  # type: ignore[assignment]
    mcp_response_bytes = None  # type: ignore[assignment]
    env_passthrough_requests_total = None  # type: ignore[assignment]
    env_passthrough_vars_count = None  # type: ignore[assignment]
    env_passthrough_errors_total = None  # type: ignore[assignment]

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


async def _increment_call_counts(
    namespace_name: str,
    endpoint_type: EndpointType,
    tool_name: str,
) -> None:
    """Atomically increment call_count on namespace (and service/function for run endpoints).

    Uses a separate DB session so failures never roll back the tool response (fail-open).
    """
    try:
        async with get_db_context() as db:
            # Always increment namespace
            await db.execute(
                sa_update(Namespace)
                .where(Namespace.name == namespace_name)
                .values(call_count=Namespace.call_count + 1)
            )

            # For run endpoint, tool_name is "service_name.function_name"
            if endpoint_type == EndpointType.RUN and "." in tool_name:
                service_name, function_name = tool_name.split(".", 1)

                # Increment service (PostgreSQL UPDATE ... FROM ... WHERE ...)
                await db.execute(
                    sa_update(NamespaceService)
                    .where(
                        NamespaceService.namespace_id == Namespace.id,
                        Namespace.name == namespace_name,
                        NamespaceService.name == service_name,
                    )
                    .values(call_count=NamespaceService.call_count + 1)
                )

                # Increment function
                await db.execute(
                    sa_update(Function)
                    .where(
                        Function.service_id == NamespaceService.id,
                        NamespaceService.namespace_id == Namespace.id,
                        Namespace.name == namespace_name,
                        NamespaceService.name == service_name,
                        Function.name == function_name,
                    )
                    .values(call_count=Function.call_count + 1)
                )
            # Session auto-commits via get_db_context()
    except Exception:
        logger.exception("call_count_increment_failed", tool=tool_name)


async def _increment_function_counts(
    namespace_name: str,
    called_functions: list[str],
) -> None:
    """Increment service and function call_counts for code-mode sandbox calls.

    ``called_functions`` is a list of ``"service.function"`` strings captured
    from the sandbox's ``_call_log``.  Uses a single DB session for the batch.
    """
    if not called_functions:
        return
    try:
        async with get_db_context() as db:
            for tool_name in called_functions:
                if "." not in tool_name:
                    continue
                service_name, function_name = tool_name.split(".", 1)

                await db.execute(
                    sa_update(NamespaceService)
                    .where(
                        NamespaceService.namespace_id == Namespace.id,
                        Namespace.name == namespace_name,
                        NamespaceService.name == service_name,
                    )
                    .values(call_count=NamespaceService.call_count + 1)
                )

                await db.execute(
                    sa_update(Function)
                    .where(
                        Function.service_id == NamespaceService.id,
                        NamespaceService.namespace_id == Namespace.id,
                        Namespace.name == namespace_name,
                        NamespaceService.name == service_name,
                        Function.name == function_name,
                    )
                    .values(call_count=Function.call_count + 1)
                )
    except Exception:
        logger.exception("function_count_increment_failed", called_functions=called_functions)


async def _authenticate(request: Request, db: Any) -> tuple[Any, Any]:
    """Authenticate request via API key, returning (Account, APIKey).

    Raises ``ValueError`` on auth failure so the MCP SDK can surface
    the error to the client.
    """
    from fastapi import HTTPException

    from mcpworks_api.mcp.router import get_account_from_api_key

    try:
        return await get_account_from_api_key(request, db)
    except HTTPException as e:
        raise ValueError(f"Authentication failed: {e.detail}") from e


def _check_namespace_scope_mcp(api_key: Any, namespace: str) -> None:
    """Wrap check_namespace_scope for the MCP SDK path (raises ValueError)."""
    from fastapi import HTTPException

    from mcpworks_api.mcp.router import check_namespace_scope

    try:
        check_namespace_scope(api_key, namespace)
    except HTTPException as e:
        raise ValueError(e.detail) from e


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
            account, api_key = await _authenticate(request, db)
            _check_namespace_scope_mcp(api_key, namespace)

            if not api_key.has_scope("read"):
                return []

            if endpoint_type == EndpointType.CREATE:
                return _to_sdk_tools(CreateMCPHandler.get_tools())
            else:
                run_mode = request.query_params.get("mode", "code")
                handler = RunMCPHandler(
                    namespace=namespace, account=account, db=db, mode=run_mode, api_key=api_key
                )
                return _to_sdk_tools(await handler.get_tools())
    except ValueError:
        raise
    except Exception as e:
        logger.error("list_tools_error", error=str(e), exc_info=True)
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

    # Extract user-provided env vars from header (run endpoints only)
    sandbox_env: dict[str, str] | None = None
    if endpoint_type == EndpointType.RUN:
        try:
            sandbox_env = extract_env_vars(request) or None
            if sandbox_env and env_passthrough_requests_total is not None:
                env_passthrough_requests_total.inc()
                env_passthrough_vars_count.observe(len(sandbox_env))
        except EnvPassthroughError as e:
            if env_passthrough_errors_total is not None:
                env_passthrough_errors_total.labels(error_type=type(e).__name__).inc()
            raise ValueError(str(e)) from e

    async with get_db_context() as db:
        account, api_key = await _authenticate(request, db)
        _check_namespace_scope_mcp(api_key, namespace)

        if endpoint_type == EndpointType.CREATE:
            handler = CreateMCPHandler(namespace=namespace, account=account, db=db, api_key=api_key)
        else:
            run_mode = request.query_params.get("mode", "code")
            handler = RunMCPHandler(
                namespace=namespace, account=account, db=db, mode=run_mode, api_key=api_key
            )

        result = await handler.dispatch_tool(name, args, sandbox_env=sandbox_env)
        contents = [TextContent(type="text", text=c.text) for c in result.content]

        # Increment call counts (fail-open — errors logged, not raised)
        await _increment_call_counts(namespace, endpoint_type, name)

        # Code-mode: also increment per-function counts from sandbox call log
        called_functions = (result.metadata or {}).get("called_functions", [])
        if called_functions:
            await _increment_function_counts(namespace, called_functions)

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

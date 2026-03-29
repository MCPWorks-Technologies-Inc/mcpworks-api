# Gateway Architecture Specification

**Version:** 1.0.0
**Last Updated:** 2026-02-09
**Status:** Active
**Related Documents:**
- [Database Models Specification](./database-models-specification.md)
- [Code Sandbox Specification](./code-sandbox-specification.md)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Module Structure](#module-structure)
4. [Middleware Chain](#middleware-chain)
5. [MCP Protocol Layer](#mcp-protocol-layer)
6. [Create MCP Handler](#create-mcp-handler)
7. [Run MCP Handler](#run-mcp-handler)
8. [Backend Abstraction](#backend-abstraction)
9. [Error Handling](#error-handling)
10. [Implementation Checklist](#implementation-checklist)

---

## 1. Overview

The Gateway is the **single entrypoint** for all MCPWorks requests. It handles:

- **Subdomain Parsing:** Extract namespace and endpoint type from Host header
- **Authentication:** Validate API keys from Authorization header
- **Authorization:** Check key scopes (create, run, admin)
- **Rate Limiting:** Enforce per-account request limits
- **Billing:** Track usage and check quotas
- **MCP Protocol:** Handle JSON-RPC 2.0 requests
- **Backend Dispatch:** Route function calls to appropriate backend

**Technology Stack:**
- Python 3.11+
- FastAPI (ASGI framework)
- PostgreSQL (async via asyncpg)
- Redis (rate limiting, caching)
- Pydantic (request/response validation)

---

## 2. Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  AI Assistant (Claude Code / Copilot / Codex)                                │
│  .mcp.json: { "url": "https://acme.create.mcpworks.io", "headers": {...} }   │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │ HTTPS + Authorization header
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Cloudflare Tunnel                                                           │
│  *.create.mcpworks.io → localhost:8000                                       │
│  *.run.mcpworks.io → localhost:8000                                          │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Gateway (FastAPI)                                                           │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  Middleware Chain                                                      │  │
│  │  subdomain.py → auth.py → rate_limit.py → billing.py                   │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                 │                                            │
│                    ┌────────────┴────────────┐                               │
│                    ▼                         ▼                               │
│  ┌─────────────────────────────┐   ┌─────────────────────────────────┐       │
│  │  Create MCP Handler         │   │  Run MCP Handler                │       │
│  │  (*.create.mcpworks.io)     │   │  (*.run.mcpworks.io)            │       │
│  │                             │   │                                 │       │
│  │  13 Management Tools:       │   │  Two modes (?mode= query param):│       │
│  │  • make_namespace           │   │                                 │       │
│  │  • list_namespaces          │   │  Code mode (DEFAULT):           │       │
│  │  • make_service             │   │  • Single "execute" tool        │       │
│  │  • list_services            │   │  • AI writes Python code        │       │
│  │  • delete_service           │   │  • Imports from functions/ pkg  │       │
│  │  • make_function            │   │                                 │       │
│  │  • update_function          │   │  Tool mode (?mode=tools):       │       │
│  │  • delete_function          │   │  • One tool per function        │       │
│  │  • list_functions           │   │  • {service}.{function}         │       │
│  │  • describe_function        │   │  • Generated from DB            │       │
│  │  • list_packages            │   │                                 │       │
│  │  • list_templates           │   │  Response includes:             │       │
│  │  • describe_template        │   │  • result                       │       │
│  │                             │   │  • execution metadata           │       │
│  └─────────────────────────────┘   └──────────────┬──────────────────┘       │
│                                                    │                          │
└────────────────────────────────────────────────────┼──────────────────────────┘
                                                     │
                                                     ▼
                                    ┌───────────────────────────────────┐
                                    │  Function Backends                │
                                    │                                   │
                                    │  ┌─────────────────────────────┐  │
                                    │  │ Code Sandbox (A0)           │  │
                                    │  │ • nsjail isolation          │  │
                                    │  │ • Seccomp ALLOWLIST         │  │
                                    │  │ • Egress proxy (allowlist)  │  │
                                    │  └─────────────────────────────┘  │
                                    │                                   │
                                    │  ┌─────────────────────────────┐  │
                                    │  │ nanobot.ai (A2)             │  │
                                    │  │ • TBD                       │  │
                                    │  └─────────────────────────────┘  │
                                    │                                   │
                                    │  ┌─────────────────────────────┐  │
                                    │  │ GitHub Repo (A3)            │  │
                                    │  │ • MCPWorks Framework        │  │
                                    │  └─────────────────────────────┘  │
                                    └───────────────────────────────────┘
```

---

## 3. Module Structure

```
src/mcpworks_api/
├── main.py                        # FastAPI app entry (existing)
├── config.py                      # Settings (existing)
│
├── middleware/                    # Request processing pipeline
│   ├── __init__.py
│   ├── subdomain.py              # NEW: Parse Host header
│   ├── auth.py                   # API key validation
│   ├── rate_limit.py             # Redis-based limits (existing)
│   └── billing.py                # NEW: Usage tracking
│
├── mcp/                          # NEW: MCP protocol layer
│   ├── __init__.py
│   ├── protocol.py               # JSON-RPC 2.0 handling
│   ├── create_handler.py         # Management MCP handler
│   ├── run_handler.py            # Execution MCP handler
│   └── router.py                 # MCP endpoint router
│
├── backends/                     # NEW: Function backends
│   ├── __init__.py
│   ├── base.py                   # Abstract backend interface
│   ├── sandbox.py                # Code Sandbox backend
│   └── nanobot.py                # nanobot.ai backend (A2)
│
├── models/                       # SQLAlchemy models
│   ├── namespace.py              # NEW
│   ├── service.py                # Extend existing
│   ├── function.py               # NEW
│   ├── function_version.py       # NEW
│   └── ...                       # Existing models
│
├── schemas/                      # Pydantic schemas
│   ├── mcp.py                    # NEW: MCP protocol schemas
│   ├── namespace.py              # NEW
│   ├── function.py               # NEW
│   └── ...
│
├── services/                     # Business logic
│   ├── namespace_service.py      # NEW
│   ├── function_service.py       # NEW
│   └── ...
│
└── core/                         # Infrastructure (existing)
    ├── database.py
    ├── redis.py
    └── security.py
```

---

## 4. Middleware Chain

### 4.1 Subdomain Middleware

```python
# src/mcpworks_api/middleware/subdomain.py
"""
Parse Host header to extract namespace and endpoint type.

Examples:
  acme.create.mcpworks.io → namespace="acme", endpoint="create"
  acme.run.mcpworks.io → namespace="acme", endpoint="run"
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import re

SUBDOMAIN_PATTERN = re.compile(
    r"^(?P<namespace>[a-z][a-z0-9-]{2,62})\.(?P<endpoint>create|run)\.mcpworks\.io$"
)


class SubdomainMiddleware(BaseHTTPMiddleware):
    """Extract namespace and endpoint type from Host header."""

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()

        # Allow localhost for development
        if host.startswith("localhost") or host.startswith("127.0.0.1"):
            # Use query params for local testing
            request.state.namespace = request.query_params.get("namespace", "default")
            request.state.endpoint_type = request.query_params.get("endpoint", "create")
            return await call_next(request)

        match = SUBDOMAIN_PATTERN.match(host)
        if not match:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_HOST",
                    "message": f"Invalid host: {host}. Expected {{namespace}}.{{create|run}}.mcpworks.io"
                }
            )

        request.state.namespace = match.group("namespace")
        request.state.endpoint_type = match.group("endpoint")

        return await call_next(request)
```

### 4.2 Auth Middleware

```python
# src/mcpworks_api/middleware/auth.py
"""
Validate API key from Authorization header.

Supports:
  Authorization: Bearer mcpw_abc123...
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_session_factory
from ..core.security import verify_api_key_hash
from ..models import APIKey, Account


class AuthMiddleware(BaseHTTPMiddleware):
    """Validate API key and attach account to request."""

    EXEMPT_PATHS = {"/health", "/health/ready", "/health/live", "/metrics"}

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health endpoints
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Extract API key
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Missing or invalid Authorization header"}
            )

        api_key = auth_header[7:]  # Remove "Bearer " prefix

        if not api_key.startswith("mcpw_"):
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Invalid API key format"}
            )

        # Validate key
        key_prefix = api_key[:12]  # mcpw_ + first 7 chars

        async with get_session_factory()() as session:
            stmt = select(APIKey).where(
                APIKey.key_prefix == key_prefix,
                APIKey.revoked_at.is_(None)
            )
            result = await session.execute(stmt)
            api_key_record = result.scalar_one_or_none()

            if not api_key_record:
                raise HTTPException(
                    status_code=401,
                    detail={"code": "UNAUTHORIZED", "message": "Invalid API key"}
                )

            # Verify full key hash
            if not verify_api_key_hash(api_key, api_key_record.key_hash):
                raise HTTPException(
                    status_code=401,
                    detail={"code": "UNAUTHORIZED", "message": "Invalid API key"}
                )

            # Check expiry
            if api_key_record.expires_at and api_key_record.expires_at < datetime.utcnow():
                raise HTTPException(
                    status_code=401,
                    detail={"code": "UNAUTHORIZED", "message": "API key expired"}
                )

            # Load account
            stmt = select(Account).where(Account.id == api_key_record.account_id)
            result = await session.execute(stmt)
            account = result.scalar_one_or_none()

            if not account:
                raise HTTPException(
                    status_code=401,
                    detail={"code": "UNAUTHORIZED", "message": "Account not found"}
                )

            # Attach to request
            request.state.account = account
            request.state.api_key = api_key_record

            # Update last_used_at (async, don't wait)
            api_key_record.last_used_at = datetime.utcnow()
            await session.commit()

        return await call_next(request)
```

### 4.3 Billing Middleware

```python
# src/mcpworks_api/middleware/billing.py
"""
Track usage and enforce quotas.
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import date

from ..core.redis import get_redis
from ..models import Account


class BillingMiddleware(BaseHTTPMiddleware):
    """Track usage and check quotas."""

    # Tier limits (executions per month)
    TIER_LIMITS = {
        "free": 500,
        "founder": 10_000,
        "founder_pro": 50_000,
        "enterprise": float("inf"),
    }

    async def dispatch(self, request: Request, call_next):
        # Only track for run endpoint
        if getattr(request.state, "endpoint_type", None) != "run":
            return await call_next(request)

        account: Account = getattr(request.state, "account", None)
        if not account:
            return await call_next(request)

        # Check quota
        redis = await get_redis()
        today = date.today()
        month_key = f"usage:{account.id}:{today.year}:{today.month}"

        current_usage = await redis.get(month_key)
        current_usage = int(current_usage) if current_usage else 0

        limit = self.TIER_LIMITS.get(account.tier, 500)

        if current_usage >= limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "QUOTA_EXCEEDED",
                    "message": f"Monthly execution limit ({limit}) exceeded",
                    "usage": current_usage,
                    "limit": limit,
                }
            )

        # Increment usage (after successful execution)
        response = await call_next(request)

        if response.status_code < 400:
            await redis.incr(month_key)
            # Set expiry to end of next month
            await redis.expireat(month_key, self._end_of_next_month())

        return response

    def _end_of_next_month(self):
        """Get timestamp for end of next month."""
        from datetime import datetime, timedelta
        today = datetime.utcnow()
        # Add 62 days to be safe (covers current + next month)
        return int((today + timedelta(days=62)).timestamp())
```

### 4.4 Middleware Registration Order

```python
# src/mcpworks_api/main.py

def create_app() -> FastAPI:
    app = FastAPI(...)

    # Middleware order: first added = outermost = last executed on request
    # So add in reverse order of desired execution

    # 4. Billing (innermost, runs last on request, first on response)
    app.add_middleware(BillingMiddleware)

    # 3. Rate Limiting
    app.add_middleware(RateLimitMiddleware)

    # 2. Authentication
    app.add_middleware(AuthMiddleware)

    # 1. Subdomain Parsing (outermost, runs first)
    app.add_middleware(SubdomainMiddleware)

    # Include MCP router
    app.include_router(mcp_router)

    return app
```

---

## 5. MCP Protocol Layer

### 5.1 Protocol Helpers

```python
# src/mcpworks_api/mcp/protocol.py
"""
MCP Protocol (JSON-RPC 2.0) helpers.
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request."""
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None


class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 error."""
    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response."""
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None
    id: Optional[Union[str, int]] = None


class MCPTool(BaseModel):
    """MCP tool definition."""
    name: str
    description: str
    inputSchema: Dict[str, Any]


class MCPToolsListResult(BaseModel):
    """Result of tools/list method."""
    tools: List[MCPTool]


class MCPToolCallParams(BaseModel):
    """Parameters for tools/call method."""
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class MCPContent(BaseModel):
    """MCP content block."""
    type: str = "text"
    text: str


class MCPToolResult(BaseModel):
    """Result of tools/call method."""
    content: List[MCPContent]
    isError: bool = False
    metadata: Optional[Dict[str, Any]] = None


# Error codes
class MCPErrorCodes:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Custom errors
    UNAUTHORIZED = -32001
    FORBIDDEN = -32002
    NOT_FOUND = -32003
    RATE_LIMITED = -32004
    QUOTA_EXCEEDED = -32005
    EXECUTION_ERROR = -32006


def make_error_response(
    code: int,
    message: str,
    data: Any = None,
    request_id: Optional[Union[str, int]] = None
) -> JSONRPCResponse:
    """Create an error response."""
    return JSONRPCResponse(
        error=JSONRPCError(code=code, message=message, data=data),
        id=request_id
    )


def make_success_response(
    result: Any,
    request_id: Optional[Union[str, int]] = None
) -> JSONRPCResponse:
    """Create a success response."""
    return JSONRPCResponse(result=result, id=request_id)
```

### 5.2 MCP Router

```python
# src/mcpworks_api/mcp/router.py
"""
MCP endpoint router.
"""

from fastapi import APIRouter, Request, Depends
from typing import Dict, Any

from .protocol import JSONRPCRequest, JSONRPCResponse, MCPErrorCodes, make_error_response
from .create_handler import CreateMCPHandler
from .run_handler import RunMCPHandler

router = APIRouter()


@router.post("/mcp")
async def handle_mcp(request: Request, body: JSONRPCRequest) -> JSONRPCResponse:
    """
    Main MCP endpoint. Routes to appropriate handler based on endpoint type.
    """
    endpoint_type = getattr(request.state, "endpoint_type", None)
    namespace = getattr(request.state, "namespace", None)
    account = getattr(request.state, "account", None)

    if not all([endpoint_type, namespace, account]):
        return make_error_response(
            MCPErrorCodes.UNAUTHORIZED,
            "Missing request context",
            request_id=body.id
        )

    # Select handler
    if endpoint_type == "create":
        handler = CreateMCPHandler(namespace=namespace, account=account)
    elif endpoint_type == "run":
        handler = RunMCPHandler(namespace=namespace, account=account)
    else:
        return make_error_response(
            MCPErrorCodes.INVALID_REQUEST,
            f"Unknown endpoint type: {endpoint_type}",
            request_id=body.id
        )

    # Dispatch method
    return await handler.handle(body)
```

---

## 6. Create MCP Handler

### 6.1 Handler Implementation

```python
# src/mcpworks_api/mcp/create_handler.py
"""
Create MCP Handler - Management interface for namespaces, services, functions.

Exposes 10 tools:
- make_namespace, list_namespaces
- make_service, list_services, delete_service
- make_function, update_function, delete_function, list_functions, describe_function
"""

from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json

from .protocol import (
    JSONRPCRequest, JSONRPCResponse, MCPTool, MCPToolsListResult,
    MCPToolCallParams, MCPToolResult, MCPContent,
    MCPErrorCodes, make_error_response, make_success_response
)
from ..core.database import get_session_factory
from ..models import Account, Namespace, Service, Function, FunctionVersion
from ..services.namespace_service import NamespaceService
from ..services.function_service import FunctionService


class CreateMCPHandler:
    """Handler for *.create.mcpworks.io endpoints."""

    def __init__(self, namespace: str, account: Account):
        self.namespace_name = namespace
        self.account = account
        self.namespace_service = NamespaceService()
        self.function_service = FunctionService()

    async def handle(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """Handle MCP request."""
        method = request.method
        params = request.params or {}

        if method == "initialize":
            return await self._handle_initialize(request.id)
        elif method == "tools/list":
            return await self._handle_tools_list(request.id)
        elif method == "tools/call":
            return await self._handle_tools_call(params, request.id)
        else:
            return make_error_response(
                MCPErrorCodes.METHOD_NOT_FOUND,
                f"Unknown method: {method}",
                request_id=request.id
            )

    async def _handle_initialize(self, request_id) -> JSONRPCResponse:
        """Handle initialize method."""
        return make_success_response({
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": f"mcpworks-create-{self.namespace_name}",
                "version": "1.0.0"
            }
        }, request_id)

    async def _handle_tools_list(self, request_id) -> JSONRPCResponse:
        """Return list of available management tools."""
        tools = [
            MCPTool(
                name="make_namespace",
                description="Create a new namespace for organizing services and functions",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Namespace name (lowercase, alphanumeric, hyphens, 3-63 chars)",
                            "pattern": "^[a-z][a-z0-9-]{2,62}$"
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional description"
                        }
                    },
                    "required": ["name"]
                }
            ),
            MCPTool(
                name="list_namespaces",
                description="List all namespaces for the current account",
                inputSchema={"type": "object", "properties": {}}
            ),
            MCPTool(
                name="make_service",
                description="Create a new service within the current namespace",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Service name"
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional description"
                        }
                    },
                    "required": ["name"]
                }
            ),
            MCPTool(
                name="list_services",
                description="List all services in the current namespace",
                inputSchema={"type": "object", "properties": {}}
            ),
            MCPTool(
                name="delete_service",
                description="Delete a service and all its functions",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Service name"}
                    },
                    "required": ["name"]
                }
            ),
            MCPTool(
                name="make_function",
                description="Create a new function in a service",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string", "description": "Service name"},
                        "name": {"type": "string", "description": "Function name"},
                        "backend": {
                            "type": "string",
                            "enum": ["code_sandbox", "nanobot", "github_repo"],
                            "description": "Execution backend"
                        },
                        "code": {"type": "string", "description": "Function code (for code_sandbox)"},
                        "input_schema": {"type": "object", "description": "JSON Schema for input"},
                        "output_schema": {"type": "object", "description": "JSON Schema for output"},
                        "description": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["service", "name", "backend"]
                }
            ),
            MCPTool(
                name="update_function",
                description="Update a function (creates new version)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "name": {"type": "string"},
                        "backend": {"type": "string"},
                        "code": {"type": "string"},
                        "input_schema": {"type": "object"},
                        "output_schema": {"type": "object"},
                        "description": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "restore_version": {
                            "type": "integer",
                            "description": "Restore from a previous version number"
                        }
                    },
                    "required": ["service", "name"]
                }
            ),
            MCPTool(
                name="delete_function",
                description="Delete a function",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "name": {"type": "string"}
                    },
                    "required": ["service", "name"]
                }
            ),
            MCPTool(
                name="list_functions",
                description="List functions in a service",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "tag": {"type": "string", "description": "Filter by tag"}
                    },
                    "required": ["service"]
                }
            ),
            MCPTool(
                name="describe_function",
                description="Get detailed function info including version history",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "name": {"type": "string"}
                    },
                    "required": ["service", "name"]
                }
            ),
        ]

        result = MCPToolsListResult(tools=tools)
        return make_success_response(result.model_dump(), request_id)

    async def _handle_tools_call(
        self, params: Dict[str, Any], request_id
    ) -> JSONRPCResponse:
        """Dispatch tool call to appropriate method."""
        try:
            call_params = MCPToolCallParams(**params)
        except Exception as e:
            return make_error_response(
                MCPErrorCodes.INVALID_PARAMS,
                f"Invalid tool call params: {e}",
                request_id=request_id
            )

        tool_name = call_params.name
        args = call_params.arguments

        # Dispatch to handler method
        handlers = {
            "make_namespace": self._make_namespace,
            "list_namespaces": self._list_namespaces,
            "make_service": self._make_service,
            "list_services": self._list_services,
            "delete_service": self._delete_service,
            "make_function": self._make_function,
            "update_function": self._update_function,
            "delete_function": self._delete_function,
            "list_functions": self._list_functions,
            "describe_function": self._describe_function,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return make_error_response(
                MCPErrorCodes.METHOD_NOT_FOUND,
                f"Unknown tool: {tool_name}",
                request_id=request_id
            )

        try:
            result = await handler(**args)
            return make_success_response(result.model_dump(), request_id)
        except Exception as e:
            return make_error_response(
                MCPErrorCodes.EXECUTION_ERROR,
                str(e),
                request_id=request_id
            )

    # Tool implementations
    async def _make_namespace(self, name: str, description: str = None) -> MCPToolResult:
        """Create a new namespace."""
        namespace = await self.namespace_service.create(
            name=name,
            account_id=self.account.id,
            description=description
        )
        return MCPToolResult(
            content=[MCPContent(text=json.dumps({
                "id": str(namespace.id),
                "name": namespace.name,
                "created_at": namespace.created_at.isoformat()
            }))]
        )

    async def _list_namespaces(self) -> MCPToolResult:
        """List all namespaces for account."""
        namespaces = await self.namespace_service.list_for_account(self.account.id)
        return MCPToolResult(
            content=[MCPContent(text=json.dumps([
                {"name": ns.name, "description": ns.description}
                for ns in namespaces
            ]))]
        )

    async def _make_service(self, name: str, description: str = None) -> MCPToolResult:
        """Create a new service."""
        service = await self.namespace_service.create_service(
            namespace_name=self.namespace_name,
            account_id=self.account.id,
            name=name,
            description=description
        )
        return MCPToolResult(
            content=[MCPContent(text=json.dumps({
                "name": service.name,
                "namespace": self.namespace_name
            }))]
        )

    async def _list_services(self) -> MCPToolResult:
        """List services in namespace."""
        services = await self.namespace_service.list_services(
            namespace_name=self.namespace_name,
            account_id=self.account.id
        )
        return MCPToolResult(
            content=[MCPContent(text=json.dumps([
                {"name": s.name, "description": s.description}
                for s in services
            ]))]
        )

    async def _delete_service(self, name: str) -> MCPToolResult:
        """Delete a service."""
        await self.namespace_service.delete_service(
            namespace_name=self.namespace_name,
            account_id=self.account.id,
            service_name=name
        )
        return MCPToolResult(
            content=[MCPContent(text=f"Deleted service: {name}")]
        )

    async def _make_function(
        self,
        service: str,
        name: str,
        backend: str,
        code: str = None,
        input_schema: dict = None,
        output_schema: dict = None,
        description: str = None,
        tags: List[str] = None
    ) -> MCPToolResult:
        """Create a new function."""
        function = await self.function_service.create(
            namespace_name=self.namespace_name,
            account_id=self.account.id,
            service_name=service,
            name=name,
            backend=backend,
            code=code,
            input_schema=input_schema,
            output_schema=output_schema,
            description=description,
            tags=tags
        )
        return MCPToolResult(
            content=[MCPContent(text=json.dumps({
                "name": f"{service}.{name}",
                "version": 1,
                "backend": backend
            }))]
        )

    async def _update_function(
        self,
        service: str,
        name: str,
        backend: str = None,
        code: str = None,
        input_schema: dict = None,
        output_schema: dict = None,
        description: str = None,
        tags: List[str] = None,
        restore_version: int = None
    ) -> MCPToolResult:
        """Update a function (creates new version)."""
        function = await self.function_service.update(
            namespace_name=self.namespace_name,
            account_id=self.account.id,
            service_name=service,
            function_name=name,
            backend=backend,
            code=code,
            input_schema=input_schema,
            output_schema=output_schema,
            description=description,
            tags=tags,
            restore_version=restore_version
        )
        return MCPToolResult(
            content=[MCPContent(text=json.dumps({
                "name": f"{service}.{name}",
                "version": function.active_version,
                "message": "Created new version" if not restore_version else f"Restored from v{restore_version}"
            }))]
        )

    async def _delete_function(self, service: str, name: str) -> MCPToolResult:
        """Delete a function."""
        await self.function_service.delete(
            namespace_name=self.namespace_name,
            account_id=self.account.id,
            service_name=service,
            function_name=name
        )
        return MCPToolResult(
            content=[MCPContent(text=f"Deleted function: {service}.{name}")]
        )

    async def _list_functions(self, service: str, tag: str = None) -> MCPToolResult:
        """List functions in a service."""
        functions = await self.function_service.list(
            namespace_name=self.namespace_name,
            account_id=self.account.id,
            service_name=service,
            tag=tag
        )
        return MCPToolResult(
            content=[MCPContent(text=json.dumps([
                {
                    "name": f"{service}.{f.name}",
                    "description": f.description,
                    "version": f.active_version,
                    "tags": f.tags
                }
                for f in functions
            ]))]
        )

    async def _describe_function(self, service: str, name: str) -> MCPToolResult:
        """Get detailed function info."""
        function, versions = await self.function_service.describe(
            namespace_name=self.namespace_name,
            account_id=self.account.id,
            service_name=service,
            function_name=name
        )
        return MCPToolResult(
            content=[MCPContent(text=json.dumps({
                "name": f"{service}.{name}",
                "description": function.description,
                "active_version": function.active_version,
                "tags": function.tags,
                "versions": [
                    {
                        "version": v.version,
                        "backend": v.backend,
                        "created_at": v.created_at.isoformat()
                    }
                    for v in versions
                ]
            }))]
        )
```

---

## 7. Run MCP Handler

The run handler operates in two modes, controlled by the `?mode=` query parameter on the MCP endpoint URL:

| Mode | URL | Behavior |
|------|-----|----------|
| **Code mode** (default) | `.../mcp` or `.../mcp?mode=code` | Single `execute` tool — AI writes Python that imports from a generated `functions/` package |
| **Tool mode** | `.../mcp?mode=tools` | One MCP tool per function, named `service.function` |

Code mode is the default because it enables function composition, data transformation between calls, and on-demand tool discovery without loading all function schemas into the AI's context window. See [Anthropic's code execution research](https://www.anthropic.com/engineering/code-execution-with-mcp) for the 70-98% token savings this achieves.

### 7.1 Code Mode (default)

In code mode, `tools/list` returns a single tool:

```json
{
  "name": "execute",
  "description": "Execute Python code in a sandbox with access to all namespace functions. ...",
  "inputSchema": {
    "type": "object",
    "properties": {
      "code": { "type": "string", "description": "Python code to execute." }
    },
    "required": ["code"]
  }
}
```

When `execute` is called, the handler:

1. Loads all functions from the namespace's database records
2. Generates a `functions/` Python package via `code_mode.py` (wrappers, registry, `__init__.py` with catalog docstring)
3. Writes the package into the sandbox directory as `extra_files`
4. Appends a call-log capture snippet to the user's code (for per-function billing)
5. Executes via the `code_sandbox` backend
6. Parses the call log from stderr to record which functions were invoked

The AI discovers functions with `import functions; print(functions.__doc__)` and calls them with `from functions import hello; result = hello(name="World")`.

### 7.2 Tool Mode (`?mode=tools`)

In tool mode, `tools/list` generates one MCP tool per function in the namespace, plus the `_env_status` diagnostic tool. Each tool is named `service.function` with the function's `input_schema` as parameters.

### 7.3 Handler Implementation

```python
# src/mcpworks_api/mcp/run_handler.py

class RunMCPHandler:
    """Handler for *.run.mcpworks.io endpoints."""

    def __init__(self, namespace, account, db, mode="code"):
        # mode: "code" (default) or "tools"
        self.mode = mode
        ...

    async def get_tools(self) -> list[MCPTool]:
        if self.mode == "code":
            return self._get_code_mode_tools()
        # else: generate per-function tools from DB + _env_status
        ...

    async def dispatch_tool(self, name, arguments, sandbox_env=None):
        if name == "execute" and self.mode == "code":
            return await self._execute_code_mode(arguments.get("code", ""), ...)
        if name == "_env_status":
            return await self._handle_env_status(sandbox_env)
        # else: look up service.function in DB and execute via backend
        ...
```

The mode is selected by the transport layer from the query parameter:

```python
# src/mcpworks_api/mcp/transport.py
run_mode = request.query_params.get("mode", "code")  # default: code
handler = RunMCPHandler(namespace=namespace, account=account, db=db, mode=run_mode)
```

---

## 8. Backend Abstraction

### 8.1 Base Backend Interface

```python
# src/mcpworks_api/backends/base.py
"""
Abstract base class for function backends.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..models import Account


@dataclass
class ExecutionResult:
    """Result from backend execution."""
    success: bool
    output: Any
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None


class Backend(ABC):
    """Abstract backend interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier."""
        pass

    @abstractmethod
    async def execute(
        self,
        code: Optional[str],
        config: Optional[Dict[str, Any]],
        input_data: Dict[str, Any],
        account: Account,
        execution_id: str,
    ) -> ExecutionResult:
        """Execute function code/config with input data."""
        pass

    @abstractmethod
    async def validate(
        self,
        code: Optional[str],
        config: Optional[Dict[str, Any]],
    ) -> None:
        """Validate code/config before saving. Raises ValueError if invalid."""
        pass
```

### 8.2 Backend Registry

```python
# src/mcpworks_api/backends/__init__.py
"""
Backend registry and factory.
"""

from typing import Dict, Optional

from .base import Backend
from .sandbox import SandboxBackend

# Registry of available backends
_backends: Dict[str, Backend] = {}


def register_backend(backend: Backend) -> None:
    """Register a backend."""
    _backends[backend.name] = backend


def get_backend(name: str) -> Optional[Backend]:
    """Get a backend by name."""
    return _backends.get(name)


def list_backends() -> list[str]:
    """List available backend names."""
    return list(_backends.keys())


# Register default backends
register_backend(SandboxBackend())

# Future backends (A2, A3)
# register_backend(NanobotBackend())
# register_backend(GitHubRepoBackend())
```

---

## 9. Error Handling

### 9.1 Error Codes

| Code | HTTP | MCP Error Code | Description |
|------|------|----------------|-------------|
| `UNAUTHORIZED` | 401 | -32001 | Invalid or missing API key |
| `FORBIDDEN` | 403 | -32002 | API key lacks required scope |
| `NOT_FOUND` | 404 | -32003 | Namespace/service/function not found |
| `RATE_LIMITED` | 429 | -32004 | Too many requests |
| `QUOTA_EXCEEDED` | 429 | -32005 | Monthly limit exceeded |
| `EXECUTION_ERROR` | 500 | -32006 | Function execution failed |
| `VALIDATION_ERROR` | 400 | -32602 | Invalid input data |
| `NETWORK_BLOCKED` | 403 | -32007 | Egress to non-allowlisted host |
| `ALLOWLIST_RATE_LIMITED` | 429 | -32008 | Allowlist changed too frequently |

### 9.2 Error Response Format

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32003,
    "message": "Function not found: data-processing.unknown-function",
    "data": {
      "namespace": "acme",
      "service": "data-processing",
      "function": "unknown-function"
    }
  },
  "id": "request-123"
}
```

---

## 10. Implementation Checklist

### Phase 1: Core Gateway (Week 1-2)

- [ ] Add SubdomainMiddleware
- [ ] Enhance AuthMiddleware for API key validation
- [ ] Add BillingMiddleware for usage tracking
- [ ] Create MCP protocol helpers
- [ ] Create MCP router endpoint
- [ ] Test middleware chain with curl

### Phase 2: Management MCP Server (Week 2-3)

- [ ] Implement CreateMCPHandler
- [ ] Create NamespaceService for DB operations
- [ ] Create FunctionService for DB operations
- [ ] Implement all 10 management tools
- [ ] Test with Claude Code

### Phase 3: Execution MCP Server (Week 3-4)

- [ ] Implement RunMCPHandler
- [ ] Dynamic tool generation from DB
- [ ] Backend abstraction layer
- [ ] Integrate SandboxBackend
- [ ] Response metadata (execution_time, version, etc.)

### Phase 4: Integration (Week 4-5)

- [ ] End-to-end testing (create → run)
- [ ] Error handling for all edge cases
- [ ] Rate limiting per tier
- [ ] Quota enforcement
- [ ] Audit logging

---

## Changelog

**v1.0.0 (2026-02-09):**
- Initial specification
- Middleware chain architecture
- MCP protocol layer
- Create and Run handlers
- Backend abstraction

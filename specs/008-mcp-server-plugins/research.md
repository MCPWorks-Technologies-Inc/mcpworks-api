# Research: Third-Party MCP Server Integration

**Feature**: 008-mcp-server-plugins
**Date**: 2026-03-26

## R1: Connection Pool Architecture

**Decision**: In-memory per-worker pool using the existing `McpServerPool` class, refactored to read from `NamespaceMcpServer` records.

**Rationale**:
- `McpServerPool` already handles SSE, Streamable HTTP, and stdio transports
- Already manages session lifecycle (connect, list tools, call, disconnect)
- Refactoring to read from DB instead of agent JSONB is straightforward
- Per-worker is acceptable for single-server deployment (current architecture)

**Pool keying**: `(namespace_id, server_name)` → `ClientSession`
**TTL**: 5 minutes (configurable via settings). Stale connections detected on next call and reconnected.

**Alternatives considered**:
- Redis-backed pool: shared across workers, but MCP sessions are stateful TCP connections — can't be serialized to Redis
- Sidecar process: dedicated MCP connection manager, over-engineered for current scale
- No pool (connect per call): 200-500ms handshake overhead per call, unacceptable for sandbox with multiple calls

## R2: Proxy Endpoint Design

**Decision**: New FastAPI endpoint at `POST /v1/internal/mcp-proxy`, authenticated via bridge key.

**Rationale**:
- Follows the same pattern as the TypeScript cross-language bridge
- Bridge key already maps to an active execution, which has the namespace ID
- Internal endpoint — not exposed in OpenAPI docs, not rate-limited by the public rate limiter
- Separate from the MCP protocol endpoints (not a JSON-RPC handler)

**Request/response format**:
```python
# Request
{
    "server": "slack",
    "tool": "send_message",
    "arguments": {"channel": "C01234", "text": "hello"}
}

# Response (success)
{
    "result": "Message sent to #general",
    "truncated": false
}

# Response (error)
{
    "error": "MCP server 'slack' is unreachable",
    "error_type": "ConnectionError"
}
```

**Alternatives considered**:
- Tunnel through the MCP run handler: would mix internal proxy calls with user-facing execution, complicating auth and metering
- WebSocket: unnecessary complexity for request/response calls
- gRPC: adds a protocol dependency, no benefit over HTTP for this use case

## R3: Wrapper Generation for Sandbox

**Decision**: Extend `generate_functions_package()` in `code_mode.py` to query namespace MCP servers and generate wrapper functions.

**Rationale**:
- The functions package already generates wrappers for native functions and TypeScript bridges
- MCP tool wrappers follow the same pattern: build signature from schema, call an HTTP endpoint
- Wrappers go in `functions/_mcp/{server_name}.py` (separate from native `functions/{service}.py`)
- The `__init__.py` docstring includes a `[RemoteMCP]` section for discovery

**Wrapper template** (per tool):
```python
def mcp__{server}__{tool}(**kwargs):
    """Tool description from cached schema"""
    from functions._mcp_bridge import _call_mcp_tool
    return _call_mcp_tool("{server}", "{tool}", kwargs)
```

**Bridge module** (`functions/_mcp_bridge.py`):
```python
import json, os, httpx

_PROXY_URL = "{api_base}/v1/internal/mcp-proxy"
_BRIDGE_KEY = os.environ.get("__MCPWORKS_BRIDGE_KEY__", "")

def _call_mcp_tool(server: str, tool: str, arguments: dict) -> object:
    response = httpx.post(
        _PROXY_URL,
        headers={"Authorization": f"Bearer {_BRIDGE_KEY}"},
        json={"server": server, "tool": tool, "arguments": arguments},
        timeout=60,
    )
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"MCP tool {server}.{tool} failed: {data['error']}")
    return data.get("result")
```

**Alternatives considered**:
- Generate wrappers at sandbox build time (Dockerfile): tool schemas change per namespace, can't bake in
- Inject as env vars: too large for 200+ tools, pollutes environment
- Lazy discovery in sandbox: adds latency to first call, sandbox may not have network (free tier)

## R4: Tool Schema Caching

**Decision**: Cache tool schemas in `NamespaceMcpServer.tool_schemas` JSONB column at add/refresh time.

**Rationale**:
- Tool discovery requires connecting to the MCP server — can't do this on every sandbox setup
- Cached schemas are used to generate wrapper function signatures
- Refresh is explicit (`refresh_mcp_server` tool) — user controls when schemas update
- Schema drift between refreshes is acceptable; the proxy routes calls regardless of cached schemas

**Cache format**:
```json
[
    {
        "name": "send_message",
        "description": "Send a message to a channel",
        "input_schema": {"type": "object", "properties": {...}}
    }
]
```

**Alternatives considered**:
- Redis cache with TTL: adds complexity, schemas rarely change, JSONB is sufficient
- File-based cache: not shared across containers in future multi-worker setup
- No cache (discover on every sandbox setup): 200-500ms per setup, multiplied by every execution

## R5: Settings Enforcement in Proxy

**Decision**: The proxy reads per-server settings from `NamespaceMcpServer.settings` before each call and enforces them.

**Settings enforcement**:
| Setting | Enforcement |
|---------|-------------|
| `response_limit_bytes` | Truncate MCP server response if it exceeds limit. Set `truncated: true` in proxy response. |
| `timeout_seconds` | `asyncio.wait_for` on the MCP tool call. Return timeout error if exceeded. |
| `max_calls_per_execution` | Counter tracked per `(execution_id, server_name)` in memory. Return error if exceeded. |
| `retry_on_failure` / `retry_count` | Retry on connection errors (not on application errors). Exponential backoff (0.5s, 1s, 2s). |
| `enabled` | If false, proxy returns "MCP server 'X' is disabled" without connecting. |

**Alternatives considered**:
- Enforce in the wrapper (sandbox-side): sandbox could be patched to bypass limits, server-side is authoritative
- Global settings only: per-server is more flexible and matches user expectations
- No enforcement (advisory only): defeats the purpose of LLM-tunable settings

## R6: Console UI Approach

**Decision**: Add a "Remote MCP Servers" section to the existing `console.html` below the services/functions list.

**Rationale**:
- Same page reinforces the parallel hierarchy (Services | RemoteMCP as siblings)
- The console is a single-page app with vanilla JS — no framework, just fetch calls
- Each MCP server rendered as a collapsible card showing: name, URL, status, tool count
- Expanding the card shows: settings table (editable), env vars table (editable), tool list

**Data source**: New REST endpoint `GET /v1/namespaces/{ns}/mcp-servers` returns all servers with settings/env/tools for the console to render.

**Alternatives considered**:
- Separate page: fragments the namespace view
- React component: console is vanilla JS, adding React for one section is overkill
- Admin-only view: settings are LLM-tunable, should be visible to all namespace users

## R7: Agent JSONB Deprecation

**Decision**: Stop reading `agent.mcp_servers` JSONB in the orchestrator. Add `mcp_server_names` ARRAY column. Leave old column nullable, drop in future migration.

**Rationale**:
- Only a handful of agents have MCP server configs currently
- Re-adding via the new tools takes 30 seconds each
- No complex migration logic, no deduplication edge cases
- Clean cut: new code reads from `NamespaceMcpServer` exclusively

**Migration steps**:
1. Add `mcp_server_names` ARRAY column to agents table
2. Add `namespace_mcp_servers` table
3. Modify orchestrator to read from namespace registry
4. Leave `mcp_servers` JSONB column in place (nullable)
5. Future migration: drop `mcp_servers` column after confirming all agents updated

## R8: Execution Record Lookup for Bridge Key

**Decision**: The proxy resolves namespace from the bridge key using the existing execution tracking infrastructure.

**Rationale** (from clarification):
- Bridge key is already generated per-execution in `sandbox.py` (ORDER-003)
- Execution records are written to the DB with namespace context
- The proxy does: bridge key → execution_id → execution record → namespace_id
- No new auth mechanism needed

**Implementation**: The bridge key is an `exec_token` stored in the execution directory. The proxy needs a way to look up which namespace an execution belongs to. Currently, the token is verified by file existence (`/sandbox/.exec_token`). For the proxy, we need a lightweight in-memory or Redis mapping of `exec_token → (namespace_id, execution_id)` set at sandbox creation time and cleared at cleanup.

**Alternatives considered**:
- JWT-encoded bridge key: more complex, adds crypto to every proxy call
- Pass namespace as request parameter: allows namespace spoofing from sandbox code
- Lookup via DB: too slow for per-call proxy (need in-memory or Redis)

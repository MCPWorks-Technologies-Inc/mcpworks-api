# Research: MCP Proxy Analytics

**Feature**: 010-mcp-proxy-analytics
**Date**: 2026-03-26

## R1: Async Telemetry Insert Pattern

**Decision**: Use `asyncio.create_task` with a dedicated async function that opens a DB session, inserts the record, and commits. Same pattern as `fire_security_event`.

**Rationale**: The proxy must return the response to the sandbox immediately. Telemetry capture cannot add latency. Fire-and-forget async task is the established pattern in the codebase.

**Pattern**:
```python
async def _record_proxy_call(namespace_id, server, tool, latency_ms, ...):
    async with get_db_context() as db:
        call = McpProxyCall(...)
        db.add(call)
        await db.commit()

# In proxy_mcp_call, after returning result:
asyncio.create_task(_record_proxy_call(...))
```

## R2: SQL Aggregation Strategy

**Decision**: Use standard PostgreSQL aggregate functions with `WHERE called_at > now() - interval` for time windows.

**Rationale**: PostgreSQL handles this natively. With a composite index on `(namespace_id, server_name, tool_name, called_at)`, a 24h aggregation over 1000 rows completes in < 10ms. No need for materialized views or pre-computed rollups at this scale.

**Query pattern for get_mcp_server_stats**:
```sql
SELECT tool_name,
       COUNT(*) as calls,
       AVG(latency_ms) as avg_latency,
       AVG(response_bytes) as avg_bytes,
       SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
       SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) as timeouts,
       SUM(CASE WHEN truncated THEN 1 ELSE 0 END) as truncations,
       SUM(injections_found) as total_injections
FROM mcp_proxy_calls
WHERE namespace_id = :ns AND server_name = :server
  AND called_at > now() - :interval
GROUP BY tool_name
ORDER BY calls DESC
```

## R3: Suggestion Engine Architecture

**Decision**: Pure Python rule evaluation. No separate service, no LLM calls. The suggestion function reads aggregated stats and applies threshold-based rules.

**Rationale**: Suggestions are deterministic — "if avg response > 100KB, suggest redact_fields." No need for AI to generate suggestions. The AI consumes the suggestions and decides whether to act.

**Rules**:
1. `avg_response_bytes > 102400` → suggest redact_fields (with probe data if available)
2. `timeout_rate > 0.10` → suggest increase timeout_seconds
3. `error_rate > 0.20` → suggest checking credentials/health
4. `calls == 0 over 7d` → suggest removing unused tool wrappers
5. `avg_calls_per_execution > 0.8 * max_calls_per_execution` → suggest raising cap
6. `truncation_rate > 0.05` → suggest increasing response_limit_bytes or adding redact_fields

## R4: Live Probe Implementation

**Decision**: Use the existing `McpServerPool` / connection pool to make a single tool call with empty or minimal arguments. Parse the JSON response to measure field sizes.

**Rationale** (from clarification): User-triggered via `probe` parameter. Only probe tools the user explicitly lists. The probe makes a real call — the user is responsible for choosing safe tools.

**Field analysis**:
```python
def analyze_response_fields(data: dict) -> list[dict]:
    """Return top-level field names with their sizes."""
    fields = []
    for key, value in data.items():
        size = len(json.dumps(value))
        fields.append({"field": key, "bytes": size, "percent": ...})
    return sorted(fields, key=lambda f: f["bytes"], reverse=True)
```

## R5: Prometheus Metrics Integration

**Decision**: Use the existing `prometheus_fastapi_instrumentator` for new metrics, plus manual Counter/Histogram from `prometheus_client`.

**Rationale**: The `/metrics` endpoint already exists. Adding new metric objects is trivial. Labels provide per-server/tool breakdown without custom exporters.

**Metrics**:
```python
from prometheus_client import Counter, Histogram

mcp_proxy_calls = Counter(
    "mcpworks_mcp_proxy_calls_total",
    "Total MCP proxy calls",
    ["namespace", "server", "tool", "status"]
)
mcp_proxy_latency = Histogram(
    "mcpworks_mcp_proxy_latency_seconds",
    "MCP proxy call latency",
    ["namespace", "server", "tool"]
)
mcp_proxy_response = Histogram(
    "mcpworks_mcp_proxy_response_bytes",
    "MCP proxy response size",
    ["namespace", "server", "tool"]
)
```

## R6: Cleanup Job Registration

**Decision**: Register the cleanup task in the APScheduler instance during app startup, same as agent heartbeat and schedule tasks.

**Schedule**: Daily at 03:00 UTC.

**Query**: `DELETE FROM mcp_proxy_calls WHERE called_at < now() - interval '30 days'`
**Query**: `DELETE FROM mcp_execution_stats WHERE executed_at < now() - interval '30 days'`

Batch delete with `LIMIT 10000` per iteration to avoid long-running transactions on large datasets.

## R7: Execution Stats Capture

**Decision**: Track MCP proxy calls per execution via the execution token registry. When the proxy is called, increment a counter associated with the execution ID. On sandbox cleanup, flush the counter to the `mcp_execution_stats` table.

**Rationale**: The execution token registry (from 008) already maps bridge keys to execution context. Adding a call counter and byte accumulator is a minor extension.

**Extension to ExecutionContext**:
```python
@dataclass
class ExecutionContext:
    execution_id: str
    namespace_id: UUID
    namespace_name: str
    created_at: datetime
    mcp_calls_count: int = 0
    mcp_bytes_total: int = 0
```

Proxy increments `ctx.mcp_calls_count` and `ctx.mcp_bytes_total` on each call. Run handler writes the final values to `mcp_execution_stats` after sandbox exit.

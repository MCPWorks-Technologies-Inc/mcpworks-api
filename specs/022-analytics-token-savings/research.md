# Research: MCP Proxy Analytics — Token Savings

**Date**: 2026-04-08

## R1: Token Savings Calculation Method

**Decision**: `tokens_saved = max(0, (max(mcp_bytes, input_bytes) - result_bytes)) // 4`

**Rationale**: The "processed" data is whichever is larger — the MCP proxy bytes fetched inside the sandbox or the input arguments passed to the function. The result is what actually returns to the AI context. The 4 bytes/token approximation is industry standard for English text with GPT/Claude tokenizers.

**Alternatives considered**:
- Using only `mcp_bytes - result_bytes`: Misses the savings from pure sandbox functions (no MCP proxy).
- Using `input_bytes + mcp_bytes - result_bytes`: Double-counts when the function processes its own input AND uses MCP proxy. The `max()` approach avoids this.
- Exact tokenization: Too expensive for a fire-and-forget recording path; 4 bytes/token is within 10% for typical content.

## R2: Analytics Recording Pattern

**Decision**: Continue using `asyncio.create_task()` fire-and-forget pattern with independent DB context.

**Rationale**: Existing pattern in `services/analytics.py` is proven — `record_proxy_call` already uses this. Recording must never block or fail the execution. Independent DB context (`get_db_context()`) avoids transaction coupling with the execution path.

**Alternatives considered**:
- Buffered batch writes: Better DB efficiency at scale, but adds complexity and delay. Not needed at current scale.
- Redis queue → async worker: Better durability, but adds infrastructure dependency. Overkill for analytics.
- Synchronous write in execution transaction: Risks execution failure on analytics DB error. Rejected.

## R3: REST API Authentication Pattern

**Decision**: Use existing `require_active_status` dependency for namespace-scoped endpoints; `AdminUserId` for platform-wide aggregate.

**Rationale**: Follows established patterns in `api/v1/executions.py` and `api/v1/admin.py`. No new auth mechanism needed.

**Alternatives considered**:
- API key with analytics-specific scope: Unnecessary complexity for initial release.
- Public endpoints with namespace token: Would bypass existing auth middleware.

## R4: Input Bytes Measurement

**Decision**: For tools mode, measure `len(json.dumps(arguments))`. For code mode, measure `len(code.encode('utf-8'))`.

**Rationale**: Tools mode arguments are the actual data the AI would have had to process; code mode's "input" is the code the AI wrote (which contains embedded data/logic the sandbox processes locally).

**Alternatives considered**:
- Measuring only the `input_data` dict size: Misses code-mode executions entirely.
- Measuring the full extra_files package: Inflated by generated function wrappers, not user data.

## R5: Admin Aggregate Query Performance

**Decision**: Direct aggregate query on `mcp_execution_stats` with time filter. No materialized views or pre-computation.

**Rationale**: At current scale (<100K records total), a single `SELECT SUM(...) GROUP BY namespace_id` with a time-range index completes in <100ms. The existing `ix_mcp_execution_stats_ns_time` index covers this query.

**Alternatives considered**:
- Materialized view refreshed on schedule: Better at scale but adds operational complexity.
- Pre-computed daily rollups: Good pattern for >1M records; deferred to future optimization.

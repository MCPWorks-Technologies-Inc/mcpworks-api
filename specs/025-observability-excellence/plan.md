# Implementation Plan: Observability Excellence

**Branch**: `feature/observability-excellence` | **Date**: 2026-04-12 | **Spec**: [spec.md](spec.md)
**Input**: Observability audit + PROBLEMS.md logging items + user requirement for Grafana-ready metrics

## Summary

Close the observability gaps that prevent production debugging and Grafana dashboarding. Three categories of work: (1) persist ephemeral agent data, (2) expose subsystem metrics to Prometheus, (3) fix silent failures in error/security logging.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), prometheus_client, structlog
**Storage**: PostgreSQL 15+ (new table + column), Redis 7+ (existing)
**Testing**: pytest with async fixtures; no DB needed for unit tests
**Performance Goals**: Zero overhead on hot path (fire-and-forget patterns); <1ms per Prometheus counter increment
**Constraints**: Must not break existing `/metrics`, `/health`, or telemetry webhook contracts

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PARTIAL | Phase 1 implemented before spec (retroactive). Process gap acknowledged. |
| II. Token Efficiency & Streaming | PASS | No impact on MCP response tokens; metrics are backend-only |
| III. Transaction Safety & Security | PASS | PII scrubbing on tool call inputs; fire-and-forget patterns avoid transaction blocking |
| IV. Provider Abstraction & Observability | PASS | This IS the observability improvement |
| V. API Contracts & Test Coverage | PASS | No API contract changes; unit tests pass (649/649) |

## Implementation Reflection (Retroactive Review)

### What we got right

1. **Centralized metrics module** (`middleware/observability.py`) — Single file with all Prometheus definitions and `record_*()` helpers. Clean separation from business logic. Easy for community contributors to find and extend.

2. **Fire-and-forget pattern consistency** — Prometheus increments are synchronous (sub-microsecond), so they don't need the `asyncio.create_task()` wrapper that DB analytics use. This is correct: Prometheus counters are thread-safe and in-process.

3. **PII scrubbing on tool call inputs** — Reuses existing `_scrub_error_message()` from execution.py. No new scrubbing logic to maintain.

4. **`db=None` fix pattern** — Follows the same `get_db_context()` pattern used by `record_proxy_call()` and `record_execution_stats()` in analytics.py. Consistent with codebase conventions.

### What needs scrutiny

1. **`tool_call_records` accumulated in orchestrator memory** — The tool call list grows unboundedly during long agent runs (up to 25 iterations x multiple tools). For enterprise-tier agents with 25 iterations and 3 tools each, that's ~75 dicts in memory. Each dict contains truncated input (2KB max) + result preview (500 chars), so worst case ~187KB. This is fine, but worth noting.

2. **`namespace_name` missing from MCP proxy Prometheus labels** — The `record_proxy_call()` in analytics.py now accepts `namespace_name`, but the callers in `mcp_proxy.py` don't pass it yet. The metric will record `namespace="unknown"` until those call sites are updated. **This is a gap that needs a follow-up task.**

3. **Auth instrumentation is login-only** — We instrumented `login()` in auth.py but not `register()`, `token()` (API key exchange), or OAuth flows. These are lower-priority but should be covered for completeness. **Follow-up task.**

4. **`agents_running` gauge correctness** — The gauge increments on entry to the try block and decrements in the finally block. If the orchestrator crashes between gauge increment and the try block entry (extremely unlikely but possible in theory), the gauge would drift. In practice, process restart resets all Prometheus gauges, so this is self-healing.

5. **`agent_run_id` threading to Execution records** — We added `agent_run_id` to the Execution model and threaded it through the orchestrator to `_execute_namespace_function`, but the function stores it in `context["agent_run_id"]` rather than directly on an Execution ORM object. The reason: `_execute_namespace_function` calls `backend.execute()` which doesn't create Execution records — those are created in the MCP run handler. For agent-triggered executions, the Execution record creation path is different (it doesn't go through the run handler). **The FK column exists but is not yet populated.** This needs a follow-up to wire the `agent_run_id` from the backend context into Execution record creation.

## Phase Structure

### Phase 1 (A0) — Implemented

| Task | Status | Files |
|------|--------|-------|
| Fix `fire_security_event(db=None)` | Done | `services/security_event.py` |
| Log HTTPException/ValidationError | Done | `middleware/error_handler.py` |
| AgentToolCall model + migration | Done | `models/agent_tool_call.py`, `alembic/versions/20260412_000001_*` |
| AgentRun.tool_calls relationship | Done | `models/agent.py` |
| Orchestrator tool call accumulation | Done | `tasks/orchestrator.py` |
| Execution.agent_run_id column | Done | `models/execution.py`, migration |
| Prometheus metrics module | Done | `middleware/observability.py` |
| Instrument orchestrator | Done | `tasks/orchestrator.py` |
| Instrument analytics (MCP proxy) | Done | `services/analytics.py` |
| Instrument security events | Done | `services/security_event.py` |
| Instrument telemetry webhooks | Done | `services/telemetry.py` |
| Instrument auth (login) | Done | `api/v1/auth.py` |
| Instrument billing | Done | `middleware/billing.py` |

### Phase 1.5 (A0) — Follow-up Gaps

| Task | Priority | Notes |
|------|----------|-------|
| Pass `namespace_name` to `record_proxy_call()` from `mcp_proxy.py` | P1 | Currently records "unknown" |
| Wire `agent_run_id` into Execution record creation | P1 | FK exists but not populated |
| Instrument `register()`, `token()`, OAuth in auth.py | P2 | Only login covered |
| Remove redundant `_stats` dict in execution_metrics.py | P2 | Blocked on verifying no consumers |
| Add `function_calls_total` recording to sandbox backend | P1 | Counter defined but not incremented |

### Phase 2 (A0 Stretch)

| Task | Priority | Notes |
|------|----------|-------|
| Expanded health checks | P2 | Scheduler heartbeat, migration status |
| Webhook delivery tracking + retry | P3 | New table, retry worker |
| Grafana dashboard JSON definitions | P2 | After metrics stabilize |

### Phase 3 (A1)

| Task | Priority | Notes |
|------|----------|-------|
| OpenTelemetry distributed tracing | P2 | New dependency |
| HITL decision logging | P3 | Depends on AgentToolCall table |
| Tool call sequence baselines | P3 | Depends on historical data |
| Error context enrichment | P2 | Depends on error handler logging |

## Verification

1. **Unit tests**: `pytest tests/unit/ -q` — 649 passed, 2 skipped
2. **Lint**: `ruff check` — all files pass
3. **Migration**: `alembic upgrade head` — creates `agent_tool_calls` table and `executions.agent_run_id` column
4. **Prometheus**: `curl localhost:8000/metrics | grep mcpworks_` — verify all 18 metric families appear
5. **Agent run audit**: Execute an agent run, then `SELECT * FROM agent_tool_calls WHERE agent_run_id = X ORDER BY sequence_number`
6. **Security events**: Verify `fire_security_event(db=None)` now persists (test with canary token leak)
7. **Error logging**: Send malformed request, verify structured log line appears

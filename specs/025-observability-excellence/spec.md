# Feature Specification: Observability Excellence

**Feature Branch**: `feature/observability-excellence`
**Created**: 2026-04-12
**Status**: In Progress (Phase 1 implemented, retroactive spec)
**GitHub Issue**: #66

## Problem Statement

mcpworks has solid observability foundations (structlog JSON logging, Prometheus HTTP metrics, security events, execution tracking, MCP analytics, telemetry webhooks). However, critical gaps prevent three key use cases:

1. **Production debugging of agent runs** — When an agent run fails or behaves unexpectedly, operators can only see a comma-separated list of function names and a 1000-char result summary. Individual tool call arguments, results, timing, and errors are ephemeral (in-memory pub/sub, lost on restart). Post-mortem analysis is impossible.

2. **Grafana dashboarding** — Most subsystem metrics only exist in PostgreSQL analytics tables or structlog output, not as Prometheus counters/histograms. An operator connecting Grafana to `/metrics` sees HTTP request rates and sandbox execution counts, but cannot see agent run rates, MCP proxy latency, per-function error rates, auth failure spikes, billing blocks, security events, or webhook delivery health.

3. **Cross-table traceability** — Execution records and AgentRun records are separate tables with no join path. When an agent triggers a function execution, there is no FK linking the two. Incident investigation requires manual timestamp correlation.

Additionally, a security bug silently drops critical events: `fire_security_event(db=None)` in the orchestrator fails because `SecurityEventService(None)` cannot write to the database. Canary token leaks and restricted tool attempts go unrecorded.

## User Scenarios & Testing

### US1 - Operator Debugs Failed Agent Run (Priority: P0)

An agent run fails or produces unexpected output. The operator queries the `agent_tool_calls` table to see exactly what happened: which tools were called, in what order, with what arguments, what each returned, and how long each took. They identify the failing step without reproducing the issue.

**Acceptance Scenarios**:

1. **Given** a completed agent run, **When** the operator queries `agent_tool_calls WHERE agent_run_id = X ORDER BY sequence_number`, **Then** they see every tool call with name, truncated input (max 2KB, PII-scrubbed), result preview (500 chars), duration_ms, source (namespace/mcp/platform), and status (success/error).
2. **Given** an agent run that fails mid-execution, **When** the operator queries, **Then** they see all tool calls up to and including the failing one, with error_message populated on the failure.
3. **Given** tool call input containing an email address or API key, **When** persisted, **Then** PII is scrubbed using the existing `_scrub_error_message()` pattern.

### US2 - Operator Builds Grafana Dashboards (Priority: P0)

An operator connects Prometheus to `api.mcpworks.io/metrics` and imports Grafana dashboard definitions. They see operational visibility across all subsystems without writing custom queries.

**Acceptance Scenarios**:

1. **Given** Prometheus scraping `/metrics`, **When** agent orchestration runs occur, **Then** `mcpworks_agent_runs_total`, `mcpworks_agent_run_duration_seconds`, `mcpworks_agents_running`, and `mcpworks_agent_tool_calls_total` metrics update with correct labels.
2. **Given** MCP proxy calls occurring, **When** scraped, **Then** `mcpworks_mcp_proxy_calls_total`, `mcpworks_mcp_proxy_latency_seconds`, and injection/truncation counters reflect reality.
3. **Given** function executions, **When** scraped, **Then** `mcpworks_function_calls_total` and `mcpworks_function_duration_seconds` show per-function (namespace/service/function) breakdowns.
4. **Given** auth attempts, billing checks, security events, and webhook deliveries, **When** scraped, **Then** corresponding `mcpworks_*` metrics increment.

### US3 - Operator Traces Agent Run to Function Executions (Priority: P1)

An operator investigating a slow agent run wants to see which specific function executions it triggered and how long each took in the sandbox.

**Acceptance Scenarios**:

1. **Given** an agent run that executed namespace functions, **When** the operator queries `executions WHERE agent_run_id = X`, **Then** they see all Execution records triggered by that run, with full execution metadata (input, output, timing, backend).
2. **Given** an execution record, **When** the operator inspects `agent_run_id`, **Then** it links back to the AgentRun that triggered it (or is NULL for non-agent executions).

### US4 - Security Events from Orchestrator are Persisted (Priority: P0)

When the orchestrator detects a canary token leak or restricted tool attempt, the security event is persisted to the `security_events` table even though the orchestrator has no active database session.

**Acceptance Scenarios**:

1. **Given** the orchestrator detects a canary token in tool call arguments, **When** `fire_security_event(db=None)` is called, **Then** the event is persisted with `event_type="canary_token_leaked"`, severity "critical".
2. **Given** an agent attempts a restricted tool, **When** `fire_security_event(db=None)` is called, **Then** the event is persisted with `event_type="restricted_tool_attempt"`, severity "high".
3. **Given** `fire_security_event(db=None)` fails (e.g., database connection error), **Then** the failure is logged but does not crash the orchestrator.

### US5 - Operator Sees All Error Types in Logs (Priority: P1)

HTTPException (4xx/5xx) and ValidationError (422) responses produce structured log entries, enabling alerting and debugging without reproducing the request.

**Acceptance Scenarios**:

1. **Given** a 403 HTTPException, **When** returned, **Then** a `warning` level log with `event=http_exception`, status, path, and method is emitted.
2. **Given** a 500 HTTPException, **When** returned, **Then** an `error` level log is emitted.
3. **Given** a Pydantic ValidationError, **When** returned as 422, **Then** a `warning` level log with field names (not values) and error count is emitted.

## Design Decisions & Reflections

### Why a separate `agent_tool_calls` table instead of JSONB on AgentRun?

JSONB would be simpler (no new table, no migration FK). But a separate table enables:
- SQL queries across runs ("which tool has the highest error rate across all agents?")
- Index on `created_at` for retention cleanup
- JOIN with executions via `agent_run_id`
- Future: sequence baselines, anomaly detection queries

**Trade-off accepted**: Extra table adds one more migration, one more model. Worth it for queryability.

### Why Prometheus counters instead of just DB analytics?

The DB analytics tables (`mcp_proxy_calls`, `mcp_execution_stats`) already track much of this data. But:
- Prometheus is pull-based, real-time, and designed for alerting
- DB analytics are great for historical analysis but lag behind (async write, commit latency)
- Grafana dashboards need Prometheus, not SQL queries
- The two are complementary, not redundant — Prometheus for ops, DB for business analytics

**Trade-off accepted**: Some data is now recorded in both Prometheus and PostgreSQL. This is intentional — different consumers, different latency requirements.

### Cardinality concerns on per-function metrics

`mcpworks_function_calls_total` has labels `[namespace, service, function, status]`. If there are 1000 functions across 100 namespaces, that's potentially 4000 time series (with 4 status values). This is well within Prometheus's comfort zone (millions of series), but worth monitoring. If cardinality becomes a problem, we can drop the `function` label and keep only `namespace + service`.

### Why PII scrubbing on tool call inputs?

Tool call arguments may contain user data (emails, API keys passed as env vars). Storing raw arguments in `agent_tool_calls.tool_input` would create a PII retention liability. We truncate to 2KB and scrub using the existing `_scrub_error_message()` pattern. This preserves debuggability while avoiding a compliance problem.

**Known limitation**: The truncation is blunt — it may cut mid-JSON. A future improvement could truncate individual values within the JSON structure instead of the serialized string.

### What about the redundant `_stats` dict in execution_metrics.py?

`execution_metrics.py` maintains a thread-locked `_stats` dict that duplicates Prometheus counters. The `get_stats_snapshot()` function is the only consumer. This should be removed (task 1.6), but we need to verify no admin endpoint or health check depends on it first.

## Non-Requirements (Explicitly Out of Scope)

- **OpenTelemetry distributed tracing** — Phase 3 (A1). Requires new dependency, multi-file instrumentation.
- **HITL decision logging** — Phase 3 (A1). Requires orchestration pause/resume logic.
- **Tool call sequence baselines** — Phase 3 (A1). Requires statistical computation over historical data.
- **Webhook retry with dead-letter queue** — Phase 2. Requires new table + retry worker.
- **Grafana dashboard JSON files** — Phase 2. Metrics must stabilize first.
- **Database connection pool metrics** — Not adding custom SQLAlchemy pool metrics; rely on OTel instrumentation in Phase 3.
- **Redis operation metrics** — Same; defer to OTel auto-instrumentation.

## Data Model Changes

### New Table: `agent_tool_calls`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| agent_run_id | UUID FK (agent_runs.id, CASCADE) | |
| sequence_number | int | 0-indexed order within the run |
| tool_name | varchar(255) | |
| tool_input | JSONB | Truncated to 2KB, PII-scrubbed |
| result_preview | text | First 500 chars of result |
| duration_ms | int | |
| source | varchar(20) | namespace, mcp, platform |
| status | varchar(20) | success, error |
| error_message | text | PII-scrubbed, only on error |
| created_at | timestamptz | server_default=now() |

Indexes: `(agent_run_id, sequence_number)`, `(created_at)`

### Modified Table: `executions`

| Column | Type | Notes |
|--------|------|-------|
| agent_run_id | UUID FK (agent_runs.id, SET NULL) | Nullable, new column |

Index: `(agent_run_id)`

### New Prometheus Metrics

| Metric | Type | Labels | Subsystem |
|--------|------|--------|-----------|
| mcpworks_agent_runs_total | Counter | namespace, trigger_type, status | Agent orchestration |
| mcpworks_agent_run_duration_seconds | Histogram | namespace, trigger_type | Agent orchestration |
| mcpworks_agent_run_iterations_total | Counter | namespace | Agent orchestration |
| mcpworks_agent_tool_calls_total | Counter | namespace, tool_name, source, status | Agent orchestration |
| mcpworks_agent_tool_call_duration_seconds | Histogram | namespace, source | Agent orchestration |
| mcpworks_agents_running | Gauge | namespace | Agent orchestration |
| mcpworks_mcp_proxy_calls_total | Counter | namespace, server_name, tool_name, status | MCP proxy |
| mcpworks_mcp_proxy_latency_seconds | Histogram | namespace, server_name | MCP proxy |
| mcpworks_mcp_proxy_response_bytes | Histogram | namespace, server_name | MCP proxy |
| mcpworks_mcp_proxy_injections_total | Counter | namespace, server_name | MCP proxy |
| mcpworks_mcp_proxy_truncations_total | Counter | namespace, server_name | MCP proxy |
| mcpworks_function_calls_total | Counter | namespace, service, function, status | Per-function |
| mcpworks_function_duration_seconds | Histogram | namespace, service, function | Per-function |
| mcpworks_auth_attempts_total | Counter | method, status | Auth |
| mcpworks_billing_quota_checks_total | Counter | namespace, result | Billing |
| mcpworks_security_events_total | Counter | event_type, severity | Security |
| mcpworks_webhook_deliveries_total | Counter | namespace, status | Webhooks |
| mcpworks_webhook_delivery_latency_seconds | Histogram | namespace | Webhooks |

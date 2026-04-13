# Tasks: Observability Excellence

**Input**: Design documents from `/specs/025-observability-excellence/`
**Prerequisites**: spec.md, plan.md

**Organization**: Tasks grouped by phase. Phase 1 is implemented. Phase 1.5 addresses gaps found during retroactive spec review.

## Format: `[ID] [Status] Description`

---

## Phase 1: Core Observability (Implemented)

**Purpose**: Agent audit trail, Prometheus metrics, error logging, security event fix

- [x] T001 [US4] Fix `fire_security_event(db=None)` — create fresh session via `get_db_context()` when db is None in `services/security_event.py`
- [x] T002 [US5] Add structured logging to `http_exception_handler` (warning for 4xx, error for 5xx) and `validation_exception_handler` (warning with field names) in `middleware/error_handler.py`
- [x] T003 [US1] Create `AgentToolCall` model with table `agent_tool_calls` in `models/agent_tool_call.py` — UUID PK, agent_run_id FK, sequence_number, tool_name, tool_input (JSONB), result_preview, duration_ms, source, status, error_message, created_at
- [x] T004 [US1] Add `tool_calls` relationship on `AgentRun` in `models/agent.py` — cascade delete, ordered by sequence_number
- [x] T005 [US3] Add `agent_run_id` nullable UUID FK column to `Execution` model in `models/execution.py`
- [x] T006 Create Alembic migration `20260412_000001_add_observability.py` — creates `agent_tool_calls` table + adds `executions.agent_run_id` column with FK and index
- [x] T007 Register `AgentToolCall` in `models/__init__.py`
- [x] T008 [US2] Create `middleware/observability.py` — centralized Prometheus metrics module with 18 metric definitions across 7 subsystems (agent, MCP proxy, per-function, auth, billing, security, webhooks) and `record_*()` helper functions
- [x] T009 [US1] Accumulate tool call records in orchestrator loop — capture tool_name, truncated input (2KB, PII-scrubbed), result_preview (500 chars), duration_ms, source, status, error_message per tool call in `tasks/orchestrator.py`
- [x] T010 [US1] Bulk-insert tool call records in `_record_run()` — flush AgentRun to get ID, then add AgentToolCall rows in `tasks/orchestrator.py`
- [x] T011 [US2] Instrument orchestrator with Prometheus metrics — `agents_running` gauge (inc/dec in try/finally), `record_agent_run()` in `_record_run()`, `record_agent_tool_call()` per tool call in `tasks/orchestrator.py`
- [x] T012 [US3] Thread `agent_run_id` through `_dispatch_tool` and `_execute_namespace_function` — stored in backend execution context in `tasks/orchestrator.py`
- [x] T013 [US2] Instrument `record_proxy_call()` with Prometheus metrics via `record_mcp_proxy_call()` in `services/analytics.py`
- [x] T014 [US2] Instrument `fire_security_event()` with `record_security_event()` counter in `services/security_event.py`
- [x] T015 [US2] Instrument `_deliver_webhook()` with `record_webhook_delivery()` counter and latency histogram in `services/telemetry.py`
- [x] T016 [US2] Instrument `login()` endpoint with `record_auth_attempt()` in `api/v1/auth.py`
- [x] T017 [US2] Instrument `BillingMiddleware.dispatch()` with `record_billing_check()` (allowed/blocked) in `middleware/billing.py`

**Checkpoint**: 649 unit tests pass, lint clean, all Phase 1 code committed.

---

## Phase 1.5: Gaps Found During Spec Review (Not Started)

**Purpose**: Address gaps identified during retroactive spec writing

- [x] T018 [US2] Pass `namespace_name` to `record_proxy_call()` from all 4 call sites in `core/mcp_proxy.py` — ctx.namespace_name already available on ExecutionContext.
- [x] T019 [US3] Create Execution records in `_execute_namespace_function` with `agent_run_id` FK populated — mirrors the run handler pattern but for agent-triggered executions.
- [x] T020 [US2] Instrument `register()`, `token()` (API key exchange), and OAuth callback with `record_auth_attempt()` in `api/v1/auth.py` and `api/v1/oauth.py`
- [x] T021 [US2] Wire `record_function_call()` into `_execute_namespace_function` alongside Execution record creation in `tasks/orchestrator.py`
- [x] T022 Remove redundant `_stats` dict from `middleware/execution_metrics.py` — rewrote `get_stats_snapshot()` to read from Prometheus collectors directly. Admin endpoints preserved with same API shape.

---

## Phase 2: A0 Stretch (Not Started)

**Purpose**: Operational reliability and dashboarding

- [ ] T023 [US2] Add scheduler heartbeat to readiness probe — write timestamp to Redis key from scheduler loop, check freshness (<2min) in `api/v1/health.py`
- [ ] T024 [US2] Add migration status to readiness probe — `SELECT version_num FROM alembic_version`, compare to expected head
- [ ] T025 [US2] Add MCP server pool health to readiness probe — check at least one configured server is reachable
- [ ] T026 Webhook delivery tracking — new `webhook_deliveries` table with status, attempts, next_retry_at, last_error. Record every delivery attempt.
- [ ] T027 Webhook retry worker — background task that polls failed deliveries and retries with exponential backoff (10s, 60s, 300s). Dead-letter after 3 attempts.
- [ ] T028 [US2] Create Grafana dashboard JSON definitions in `deploy/grafana/` — Platform Overview, Agent Operations, MCP Proxy Health, Security, Function Performance dashboards

---

## Phase 3: A1 Best-in-Class (Not Started)

**Purpose**: Distributed tracing, behavioral analysis, decision audit

- [ ] T029 OpenTelemetry SDK integration — TracerProvider, OTLP exporter, FastAPI/SQLAlchemy/httpx auto-instrumentation, W3C Trace Context propagation
- [ ] T030 Bind trace_id/span_id to structlog contextvars — every log line correlates with traces
- [ ] T031 Per-tool-call spans in orchestrator — waterfall visibility into agent execution
- [ ] T032 HITL decision logging — `agent_hitl_decisions` table, orchestration pause/resume for approval gates
- [ ] T033 Tool call sequence baselines — compute per-agent behavioral baselines from `agent_tool_calls` history
- [ ] T034 Anomaly detection — flag runs that deviate >2 sigma from baseline, emit security events
- [ ] T035 Error context enrichment — add namespace/endpoint_type/account_id to all exception handler logs

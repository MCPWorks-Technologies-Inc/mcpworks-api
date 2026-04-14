# Tasks: Orchestration Pipeline Observability

**Input**: Design documents from `/specs/027-orchestration-observability/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/rest-api.md, quickstart.md

**Organization**: Tasks grouped by user story. No test tasks generated (not requested in spec).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Exact file paths included in descriptions

---

## Phase 1: Setup

**Purpose**: Database migration covering all schema changes for this feature

- [x] T001 Create Alembic migration adding columns to `agent_runs` (outcome, orchestration_mode, limits_consumed JSONB, limits_configured JSONB, schedule_id FK, functions_called_count), columns to `agent_tool_calls` (decision_type with server_default 'call', reason_category), and new `schedule_fires` table with indexes — in `alembic/versions/YYYYMMDD_add_orchestration_observability.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Models and schemas that all user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T002 Extend `RUN_STATUSES` tuple to include `"no_action"`, `"limit_hit"`, `"cancelled"` and add new columns (outcome, orchestration_mode, limits_consumed, limits_configured, schedule_id FK, functions_called_count) to AgentRun model with relationship to schedule_fires — in `src/mcpworks_api/models/agent.py`
- [x] T003 [P] Add `decision_type` (String(20), default 'call') and `reason_category` (String(50), nullable) columns to AgentToolCall model. Define `DECISION_TYPES = ("call", "skip", "no_action", "limit_check")` and `REASON_CATEGORIES` tuple with validators — in `src/mcpworks_api/models/agent_tool_call.py`
- [x] T004 [P] Create ScheduleFire model with schedule_id FK, agent_id FK, fired_at, status, agent_run_id FK, error_detail. Add indexes per data-model.md. Register in `src/mcpworks_api/models/__init__.py` — in `src/mcpworks_api/models/schedule_fire.py`
- [x] T005 Create Pydantic response schemas: OrchestrationRunSummary (for list), OrchestrationRunDetail (with steps and limits), ScheduleFireSummary, OrchestrationStepDetail. Follow existing schema patterns — in `src/mcpworks_api/schemas/observability.py`

**Checkpoint**: Models and schemas ready — user story implementation can begin

---

## Phase 3: User Story 1 — Diagnose Why a Scheduled Agent Didn't Act (Priority: P1) MVP

**Goal**: Namespace owners can query orchestration run history to see every run's trigger, steps, outcome, and limits consumed — answering "why didn't my agent act?" without operator intervention.

**Independent Test**: Run a scheduled agent through several cron fires, then query `list_orchestration_runs` and `describe_orchestration_run` via MCP tools. Verify runs show trigger source, structured decision steps, outcome classification, and limit consumption.

### Implementation for User Story 1

- [x] T006 [US1] Modify `_record_run()` in orchestrator to persist outcome classification (map OrchestrationResult to no_action/limit_hit/completed/failed/timeout), orchestration_mode, limits_consumed and limits_configured JSONB, functions_called_count, and schedule_id when triggered by cron — in `src/mcpworks_api/tasks/orchestrator.py`
- [x] T007 [US1] Modify orchestrator loop to emit structured decision steps: for each iteration, create AgentToolCall with decision_type ('call' when invoking function, 'skip' when AI decides against, 'no_action' at end of run with no calls) and reason_category. Update existing tool_call_records construction to include the new fields — in `src/mcpworks_api/tasks/orchestrator.py`
- [x] T008 [US1] Create ObservabilityService with methods: `list_runs(agent_id, trigger_type, outcome, since, until, limit, offset)` and `get_run(run_id)` returning run with eagerly-loaded tool_calls (steps). Use existing get_db_context pattern — in `src/mcpworks_api/services/observability_service.py`
- [x] T009 [US1] Register `list_orchestration_runs` and `describe_orchestration_run` tool definitions in tool registry per contracts/rest-api.md schemas — in `src/mcpworks_api/mcp/tool_registry.py`
- [x] T010 [US1] Implement `_list_orchestration_runs` and `_describe_orchestration_run` handler methods in create_handler, wiring to ObservabilityService. Register in tool dispatch dict — in `src/mcpworks_api/mcp/create_handler.py`
- [x] T011 [US1] Create REST endpoints `GET /v1/agents/{agent_id}/runs` (list with filters/pagination) and `GET /v1/agents/{agent_id}/runs/{run_id}` (detail with steps). Wire to ObservabilityService — in `src/mcpworks_api/routers/observability.py`
- [x] T012 [US1] Register observability router in FastAPI app — in `src/mcpworks_api/main.py`

**Checkpoint**: US1 complete — owners can query run history via MCP tools and REST to diagnose agent behavior

---

## Phase 4: User Story 2 — Trace Execution to Trigger (Priority: P2)

**Goal**: Namespace owners can navigate from any function execution to the orchestration run that caused it, and from any run to all its constituent executions.

**Independent Test**: Trigger an orchestration run that calls multiple functions. Use `describe_execution` to verify it includes the parent run reference. Use `describe_orchestration_run` to verify it lists all child executions.

### Implementation for User Story 2

- [x] T013 [US2] Ensure orchestrator sets `agent_run_id` on Execution records when executing functions within an orchestration run. The FK exists (added in 025); verify it's being populated in the sandbox execution path — in `src/mcpworks_api/tasks/orchestrator.py`
- [x] T014 [US2] Extend `_describe_execution` MCP handler to include `agent_run_id` and basic run summary (trigger_type, outcome) in the response when the execution has a parent run — in `src/mcpworks_api/mcp/create_handler.py`
- [x] T015 [US2] Extend `get_run()` in ObservabilityService to include associated Execution records (query executions WHERE agent_run_id = run.id, ordered by created_at) — in `src/mcpworks_api/services/observability_service.py`
- [x] T016 [US2] Update OrchestrationRunDetail schema to include `executions` list with execution_id, function_name, status, duration_ms — in `src/mcpworks_api/schemas/observability.py`

**Checkpoint**: US1 + US2 complete — bidirectional navigation between runs and executions

---

## Phase 5: User Story 3 — Cron Fire History (Priority: P2)

**Goal**: Namespace owners can see when each cron schedule fired, whether each fire produced a run, and why it failed if it didn't.

**Independent Test**: Enable a cron schedule, wait for fires, then query `list_schedule_fires` via MCP. Verify fire timestamps, run IDs, and error details for failed fires.

### Implementation for User Story 3

- [x] T017 [US3] Modify `_execute_scheduled_function` in scheduler to create a ScheduleFire record at the start of each fire (status='started') and update it with agent_run_id on success or error_detail on failure — in `src/mcpworks_api/tasks/scheduler.py`
- [x] T018 [US3] Add `list_fires(schedule_id, agent_id, status, since, limit, offset)` method to ObservabilityService — in `src/mcpworks_api/services/observability_service.py`
- [x] T019 [US3] Register `list_schedule_fires` tool definition in tool registry per contracts/rest-api.md schema — in `src/mcpworks_api/mcp/tool_registry.py`
- [x] T020 [US3] Implement `_list_schedule_fires` handler method in create_handler, wiring to ObservabilityService. Register in tool dispatch dict — in `src/mcpworks_api/mcp/create_handler.py`
- [x] T021 [US3] Create REST endpoint `GET /v1/schedules/{schedule_id}/fires` (list with filters/pagination). Wire to ObservabilityService — in `src/mcpworks_api/routers/observability.py`

**Checkpoint**: US1 + US2 + US3 complete — full pipeline visibility from cron fire through run to execution

---

## Phase 6: User Story 4 — Orchestration Run Webhook (Priority: P3)

**Goal**: External tooling receives a webhook payload when an orchestration run completes, enabling push-based monitoring without polling.

**Independent Test**: Configure telemetry webhook with `orchestration_run` event type enabled. Trigger a run. Verify webhook fires with run summary payload. Verify existing tool_call webhooks are unaffected.

### Implementation for User Story 4

- [x] T022 [US4] Add `emit_orchestration_run_event()` function to telemetry service. Check `telemetry_config.events` for `"orchestration_run"` before firing. Build payload per contracts/rest-api.md webhook event schema. Use existing `_deliver_webhook` for delivery — in `src/mcpworks_api/services/telemetry.py`
- [x] T023 [US4] Call `emit_orchestration_run_event()` from orchestrator after `_record_run()` completes, passing run summary data. Fire-and-forget via `asyncio.create_task` — in `src/mcpworks_api/tasks/orchestrator.py`
- [x] T024 [US4] Update `configure_telemetry_webhook` MCP tool to accept `"orchestration_run"` as a valid event type in the events list. Document in tool description — in `src/mcpworks_api/mcp/create_handler.py` and `src/mcpworks_api/mcp/tool_registry.py`

**Checkpoint**: All 4 user stories complete — full observability pipeline with push notifications

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Retention, cleanup, and validation

- [x] T025 [P] Create background retention task: prune `agent_runs` older than 30 days (cascades to tool_calls) and `schedule_fires` older than 90 days. Schedule daily via existing APScheduler or lifespan task — in `src/mcpworks_api/tasks/retention.py`
- [x] T026 [P] Register retention task in app lifespan — in `src/mcpworks_api/main.py`
- [x] T027 Add Prometheus counter `mcpworks_schedule_fires_total` with labels (agent, schedule_id, status) and record in scheduler on each fire — in `src/mcpworks_api/middleware/observability.py` and `src/mcpworks_api/tasks/scheduler.py`
- [x] T028 Run `ruff format` and `ruff check --fix` across all modified files. Run `pytest tests/unit/ -q` to verify no regressions

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — migration first
- **Phase 2 (Foundational)**: Depends on Phase 1 — models need migration columns to exist
- **Phase 3 (US1)**: Depends on Phase 2 — needs models and schemas
- **Phase 4 (US2)**: Depends on Phase 3 — needs orchestration runs to exist before tracing to them
- **Phase 5 (US3)**: Depends on Phase 2 only — can run in parallel with US1
- **Phase 6 (US4)**: Depends on Phase 3 — needs run recording to emit webhook events
- **Phase 7 (Polish)**: Depends on all user stories

### User Story Dependencies

- **US1 (P1)**: Foundational only — no story dependencies
- **US2 (P2)**: Depends on US1 (runs must be recorded before executions can link to them)
- **US3 (P2)**: Foundational only — independent of US1/US2 (can parallelize with US1)
- **US4 (P3)**: Depends on US1 (runs must be recorded before webhook can fire)

### Within Each User Story

- Orchestrator/scheduler changes before service layer
- Service layer before MCP tools and REST endpoints
- MCP tools and REST endpoints can be parallel (different files)

### Parallel Opportunities

- T003 and T004 can run in parallel (different model files)
- T009 and T011 can run in parallel within US1 (tool_registry vs router)
- US1 and US3 can run in parallel after Phase 2 (independent stories)
- T025 and T026 can run in parallel in Polish phase
- T019/T020 and T021 can run in parallel within US3 (MCP vs REST)

---

## Parallel Example: User Story 1

```
# After T007 completes (orchestrator emits steps), launch in parallel:
T009: Register MCP tool definitions in tool_registry.py
T011: Create REST endpoints in routers/observability.py

# Then sequentially:
T010: Implement MCP handlers (needs T009 definitions)
T012: Register router in main.py (needs T011 router)
```

## Parallel Example: Phase 2

```
# After T001 migration, launch in parallel:
T003: AgentToolCall model extensions in agent_tool_call.py
T004: ScheduleFire model in schedule_fire.py

# T002 (AgentRun) and T005 (schemas) run sequentially after T003/T004
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Migration
2. Complete Phase 2: Models + Schemas
3. Complete Phase 3: US1 (orchestrator → service → MCP tools → REST)
4. **STOP and VALIDATE**: Query mcpworkssocial agent runs via `list_orchestration_runs`
5. Deploy if ready — this alone solves the core PROBLEM-029 diagnostic gap

### Incremental Delivery

1. Setup + Foundational → Schema ready
2. US1 → Run history queryable → Deploy (MVP)
3. US3 → Fire history queryable → Deploy (can parallel with US1)
4. US2 → Execution↔Run tracing → Deploy
5. US4 → Webhook push notifications → Deploy
6. Polish → Retention + metrics → Deploy

---

## Notes

- All new columns are nullable with defaults — zero-downtime migration
- `decision_type` defaults to `'call'` — existing AgentToolCall rows need no backfill
- ScheduleFire is write-heavy (one per cron fire) but read-light (queried on demand)
- Structured decision logs use enums only — no free-text, no PII risk
- 28 total tasks across 7 phases

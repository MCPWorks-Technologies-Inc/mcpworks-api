# Tasks: Execution Debugging

**Input**: Design documents from `/specs/020-execution-debugging/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Unit tests for execution service query logic.

**Organization**: Tasks grouped by user story.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

**Purpose**: Database migration and model extension

- [ ] T001 Add `namespace_id` (UUID FK), `service_name` (String), `function_name` (String), `execution_time_ms` (Integer) columns to executions table via Alembic migration. Add indexes: ix_executions_namespace_id, ix_executions_ns_function, ix_executions_ns_status, ix_executions_ns_created in alembic/versions/

---

## Phase 2: Foundational

**Purpose**: Model changes and service layer that all stories depend on

- [ ] T002 Add `namespace_id`, `service_name`, `function_name`, `execution_time_ms` mapped columns to Execution model in src/mcpworks_api/models/execution.py
- [ ] T003 Create ExecutionService class in src/mcpworks_api/services/execution.py with `list_executions(namespace_id, service, function, status, since, until, limit, offset)` and `get_execution(namespace_id, execution_id)` query methods
- [ ] T004 Create Pydantic response schemas `ExecutionSummary`, `ExecutionDetail`, `ExecutionListResponse` in src/mcpworks_api/schemas/execution.py

**Checkpoint**: Model and service ready — endpoint implementation can begin

---

## Phase 3: User Story 1+2 - Execution Record Persistence and Query (Priority: P1) MVP

**Goal**: Every function execution creates a queryable record. REST API exposes history and detail.

**Independent Test**: Execute a function, query GET /v1/executions, verify the record appears with correct data.

### Implementation

- [ ] T005 [US1] Wire execution record creation into `RunMCPHandler.dispatch_tool()` in src/mcpworks_api/mcp/run_handler.py — create Execution record before backend.execute(), update with result/error after, persist stdout/stderr (truncated 4KB) in backend_metadata
- [ ] T006 [US1] Create REST endpoint `GET /v1/executions` with query params (namespace, service, function, status, since, until, limit, offset) in src/mcpworks_api/api/v1/executions.py
- [ ] T007 [US2] Create REST endpoint `GET /v1/executions/{execution_id}` returning full detail (input, output, error, stdout, stderr) in src/mcpworks_api/api/v1/executions.py
- [ ] T008 [US1] Register the executions router in src/mcpworks_api/main.py
- [ ] T009 [US1] Write unit tests for ExecutionService query methods (filter by status, function, time range, pagination) in tests/unit/test_execution_service.py

**Checkpoint**: Function executions are persisted and queryable via REST API

---

## Phase 4: User Story 3 - Procedure Error Chain (Priority: P2)

**Goal**: Procedure execution detail with step-by-step error chain accessible via REST API.

**Independent Test**: Run a procedure that fails, query the execution detail, verify all step attempts and errors are visible.

### Implementation

- [ ] T010 [US3] Create REST endpoint `GET /v1/procedures/{procedure_id}/executions/{execution_id}` returning full step detail with all attempt errors in src/mcpworks_api/api/v1/procedures.py (extend existing router)

**Checkpoint**: Procedure failures are fully debuggable via REST API

---

## Phase 5: User Story 4 - MCP Tools (Priority: P2)

**Goal**: Execution history and detail available via MCP tools on create endpoint.

**Independent Test**: Call list_executions and describe_execution via MCP client, verify results.

### Implementation

- [ ] T011 [P] [US4] Register `list_executions` tool definition in src/mcpworks_api/mcp/tool_registry.py
- [ ] T012 [P] [US4] Register `describe_execution` tool definition in src/mcpworks_api/mcp/tool_registry.py
- [ ] T013 [US4] Implement `_list_executions` and `_describe_execution` handlers in src/mcpworks_api/mcp/create_handler.py, wire into TOOL_SCOPES and dispatch map

**Checkpoint**: Debugging available without leaving MCP client

---

## Phase 6: Polish

- [ ] T014 Run full unit test suite `pytest tests/unit/ -q` and verify no regressions
- [ ] T015 Run `ruff format src/ tests/ && ruff check --fix src/ tests/`

---

## Dependencies & Execution Order

- **Phase 1**: Migration first
- **Phase 2**: Depends on Phase 1
- **Phase 3 (US1+2)**: Depends on Phase 2 — MVP
- **Phase 4 (US3)**: Independent of Phase 3 (uses existing ProcedureExecution model)
- **Phase 5 (US4)**: Depends on Phase 2 (uses ExecutionService)
- **Phase 6**: After all user stories

### Parallel Opportunities

- T011, T012 can run in parallel (different tool definitions)
- Phase 4 and Phase 5 can run in parallel after Phase 2

---

## Implementation Strategy

### MVP First (User Stories 1+2)

1. Phase 1: Migration
2. Phase 2: Model + service + schemas
3. Phase 3: Record persistence + REST API
4. **STOP and VALIDATE**: Execute function, query history, verify
5. Deploy — developers can now debug function failures

### Incremental

1. MVP → function execution debugging works
2. Add US3 → procedure error chains visible
3. Add US4 → debugging available in MCP clients
4. Polish → tests, lint

---

## Notes

- Total: 15 tasks
- US1+2: 5 tasks (MVP)
- US3: 1 task
- US4: 3 tasks
- Setup/Foundation: 4 tasks
- Polish: 2 tasks

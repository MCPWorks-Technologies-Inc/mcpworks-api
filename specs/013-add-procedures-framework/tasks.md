# Tasks: Procedures Framework

**Input**: Design documents from `/specs/013-add-procedures-framework/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Foundational (Data Model + Migration)

**Purpose**: Database schema and core models that all user stories depend on.

- [x] T001 Create Procedure, ProcedureVersion, ProcedureExecution SQLAlchemy models with JSONB steps/step_results columns, validation, and relationships in src/mcpworks_api/models/procedure.py
- [x] T002 [P] Create Pydantic schemas: CreateProcedureRequest (with step validation, 1-20 steps), ProcedureResponse, ProcedureStepSchema, ProcedureExecutionResponse, ProcedureStepResultSchema in src/mcpworks_api/schemas/procedure.py
- [x] T003 Create Alembic migration: add `procedures`, `procedure_versions`, `procedure_executions` tables; add `procedure_name` column to `agent_schedules` and `agent_webhooks`; add `"procedure"` to code-level ORCHESTRATION_MODES in alembic/versions/
- [x] T004 Add `"procedure"` to ORCHESTRATION_MODES tuple in src/mcpworks_api/models/agent.py
- [x] T005 Add `make_procedure`, `update_procedure`, `delete_procedure` to RESTRICTED_AGENT_TOOLS in src/mcpworks_api/core/ai_tools.py

**Checkpoint**: Foundation ready — tables exist, models compile, security restriction in place.

---

## Phase 2: User Story 1 — Create and Execute a Procedure (Priority: P1) MVP

**Goal**: Operators create procedures with ordered steps. The orchestrator enforces step-by-step execution — the LLM must call the specified function and the platform captures the actual result before advancing.

**Independent Test**: Create a procedure with 3 steps, execute it, verify each step has captured function output in the execution record.

- [x] T006 [US1] Implement ProcedureService with create_procedure() — validates function references exist in namespace, enforces 1-20 step limit, creates Procedure + ProcedureVersion rows in src/mcpworks_api/services/procedure_service.py
- [x] T007 [US1] Implement ProcedureService.get_procedure() and list_procedures() in src/mcpworks_api/services/procedure_service.py
- [x] T008 [US1] Implement run_procedure_orchestration() in src/mcpworks_api/tasks/orchestrator.py — step-by-step loop that: sets system prompt with step instructions + accumulated context, restricts tool calls to the step's required function, captures function result, persists ProcedureExecution step_results after each step, advances or retries
- [x] T009 [US1] Implement step enforcement logic: reject LLM responses without function call (count as retry), reject calls to wrong function (count as retry), only advance when correct function returns a result in src/mcpworks_api/tasks/orchestrator.py
- [x] T010 [US1] Implement step validation: after function returns, check result against step's validation rules (required_fields). Mark step failed if validation fails in src/mcpworks_api/tasks/orchestrator.py
- [x] T011 [US1] Implement data forwarding: build accumulated context dict from all prior step results and include in the system prompt for each step in src/mcpworks_api/tasks/orchestrator.py
- [x] T012 [US1] Add MCP tool definitions for make_procedure, list_procedures, describe_procedure, run_procedure in src/mcpworks_api/mcp/tool_registry.py
- [x] T013 [US1] Add MCP tool handlers: _make_procedure, _list_procedures, _describe_procedure, _run_procedure in src/mcpworks_api/mcp/create_handler.py
- [x] T014 [US1] Register procedure tools in the create_handler dispatch map and permission map in src/mcpworks_api/mcp/create_handler.py

**Checkpoint**: US1 complete — procedures can be created and executed with step-by-step enforcement and result capture.

---

## Phase 3: User Story 2 — Step Failure Handling and Retries (Priority: P1)

**Goal**: Steps support configurable failure policies (required/allowed/skip) and retry counts. Failed required steps halt the procedure. Failed allowed steps continue with a data gap marker.

**Independent Test**: Create a procedure with a step that fails, verify retry behavior matches failure_policy and max_retries.

- [x] T015 [US2] Implement failure policy enforcement in run_procedure_orchestration(): `required` halts procedure on step failure after retries, `allowed` continues with null result marker, `skip` skips immediately on first failure in src/mcpworks_api/tasks/orchestrator.py
- [x] T016 [US2] Implement per-step retry tracking: count attempts, record each attempt with timestamp/success/error in step_results JSONB in src/mcpworks_api/tasks/orchestrator.py
- [x] T017 [US2] Implement accumulated context markers for failed/skipped steps: step_N result shows `{"status": "failed", "result": null}` or `{"status": "skipped", "result": null}` so subsequent steps know data is unavailable in src/mcpworks_api/tasks/orchestrator.py

**Checkpoint**: US2 complete — failure policies and retries work correctly.

---

## Phase 4: User Story 3 — Audit and Inspect Procedure Executions (Priority: P1)

**Goal**: Complete execution records with per-step audit trail. Operators can list and inspect executions.

**Independent Test**: Execute a procedure, query the execution record, verify step-by-step results with function outputs, timestamps, and status.

- [x] T018 [US3] Implement ProcedureService.list_executions() with filters (procedure_name, status, limit) in src/mcpworks_api/services/procedure_service.py
- [x] T019 [US3] Implement ProcedureService.get_execution() returning full step-by-step audit trail in src/mcpworks_api/services/procedure_service.py
- [x] T020 [US3] Add MCP tool definitions for list_procedure_executions, describe_procedure_execution in src/mcpworks_api/mcp/tool_registry.py
- [x] T021 [US3] Add MCP tool handlers: _list_procedure_executions, _describe_procedure_execution in src/mcpworks_api/mcp/create_handler.py
- [x] T022 [US3] Record procedure executions as AgentRun records with trigger_type and procedure execution ID cross-reference in src/mcpworks_api/tasks/orchestrator.py

**Checkpoint**: US3 complete — full audit trail accessible via MCP tools.

---

## Phase 5: User Story 4 — Manage Procedures via MCP and REST (Priority: P2)

**Goal**: Full CRUD for procedures via both MCP tools and REST API. Immutable versioning on updates.

**Independent Test**: Create, update (verify new version), describe (verify version history), soft-delete a procedure.

- [x] T023 [US4] Implement ProcedureService.update_procedure() — creates new ProcedureVersion, updates active_version in src/mcpworks_api/services/procedure_service.py
- [x] T024 [US4] Implement ProcedureService.delete_procedure() — soft delete (is_deleted=true), preserves execution records in src/mcpworks_api/services/procedure_service.py
- [x] T025 [US4] Add MCP tool definitions for update_procedure, delete_procedure in src/mcpworks_api/mcp/tool_registry.py
- [x] T026 [US4] Add MCP tool handlers: _update_procedure, _delete_procedure in src/mcpworks_api/mcp/create_handler.py
- [x] T027 [P] [US4] Create REST endpoints: POST /v1/agents/{id}/procedures, GET /v1/agents/{id}/procedures, GET /v1/agents/{id}/procedures/{proc_id}, PUT /v1/agents/{id}/procedures/{proc_id}, DELETE /v1/agents/{id}/procedures/{proc_id} in src/mcpworks_api/api/v1/procedures.py
- [x] T028 [US4] Register procedures REST router in src/mcpworks_api/main.py

**Checkpoint**: US4 complete — full CRUD with versioning via MCP and REST.

---

## Phase 6: User Story 5 — Trigger Procedures from Schedules, Webhooks, and Channels (Priority: P2)

**Goal**: Existing trigger infrastructure supports `procedure` as an orchestration mode.

**Independent Test**: Create a schedule with `orchestration_mode: "procedure"` and `procedure_name`, trigger it, verify procedure executes with full audit.

- [x] T029 [US5] Update schedule execution path in src/mcpworks_api/tasks/scheduler.py to detect `orchestration_mode == "procedure"` and call `run_procedure_orchestration()` with the named procedure
- [x] T030 [US5] Update webhook execution path in src/mcpworks_api/api/v1/webhooks.py to detect `orchestration_mode == "procedure"` and call `run_procedure_orchestration()` with webhook payload as input_context
- [x] T031 [US5] Update add_schedule MCP tool to accept `procedure_name` parameter (required when mode is "procedure") in src/mcpworks_api/mcp/tool_registry.py and src/mcpworks_api/mcp/create_handler.py
- [x] T032 [US5] Update add_webhook MCP tool to accept `procedure_name` parameter in src/mcpworks_api/mcp/tool_registry.py and src/mcpworks_api/mcp/create_handler.py

**Checkpoint**: US5 complete — procedures triggered by schedules and webhooks.

---

## Phase 7: User Story 6 — Data Forwarding Between Steps (Priority: P2)

**Goal**: Each step receives accumulated results from all prior steps as context.

**Note**: Core data forwarding is implemented in T011 (US1). This phase covers edge cases and refinement.

- [x] T033 [US6] Verify that step context includes failed/skipped step markers from US2 (T017) and that the LLM receives clear indicators of missing data in src/mcpworks_api/tasks/orchestrator.py
- [x] T034 [US6] Verify that 5-step procedures accumulate full context correctly — step 5 sees results from steps 1-4 without truncation in src/mcpworks_api/tasks/orchestrator.py

**Checkpoint**: US6 complete — data forwarding works across all step states.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [x] T035 Run full existing test suite to verify no regressions
- [x] T036 [P] Update docs/guide.md with Procedures section covering creation, execution, failure policies, and audit
- [x] T037 [P] Update docs/llm-reference.md with procedure tools table and execution model
- [x] T038 Run quickstart.md smoke test validation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately
- **US1 (Phase 2)**: Depends on Phase 1 — core execution engine, MVP
- **US2 (Phase 3)**: Depends on US1 (extends the execution loop)
- **US3 (Phase 4)**: Depends on US1 (needs execution records to inspect)
- **US4 (Phase 5)**: Depends on Phase 1 (CRUD is independent of execution)
- **US5 (Phase 6)**: Depends on US1 (needs execution engine for triggers)
- **US6 (Phase 7)**: Depends on US1 + US2 (verifies forwarding with failures)
- **Polish (Phase 8)**: Depends on all user stories

### User Story Dependencies

- **US1 (Create & Execute)**: Independent after Phase 1 — MVP
- **US2 (Failure Handling)**: Extends US1's execution loop
- **US3 (Audit)**: Reads execution records from US1
- **US4 (CRUD Management)**: Independent after Phase 1 — can parallel with US1
- **US5 (Triggers)**: Depends on US1 execution engine
- **US6 (Data Forwarding)**: Verification of US1 + US2

### Parallel Opportunities

- T001 and T002 can run in parallel (models vs schemas)
- T012-T014 can run in parallel with T008-T011 (MCP tools vs orchestrator)
- US4 (CRUD) can run in parallel with US1 (execution)
- T036 and T037 can run in parallel (different doc files)

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Data model + migration
2. Complete Phase 2: US1 — Create and execute procedures
3. **STOP and VALIDATE**: Create a 3-step procedure, execute it, verify step results captured
4. This alone solves the hallucination problem

### Incremental Delivery

1. Phase 1 + Phase 2 (US1) → Deploy (MVP — procedures work)
2. Phase 3 (US2 failure handling) → Deploy (production-ready)
3. Phase 4 (US3 audit) → Deploy (inspection tools)
4. Phase 5 (US4 CRUD) → Deploy (full management)
5. Phase 6 (US5 triggers) → Deploy (schedule/webhook support)
6. Phase 7 (US6 verification) + Phase 8 (polish) → Deploy (complete)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Steps stored as JSONB arrays (not separate tables)
- Procedure management tools restricted from agents (014 consistency)
- Procedure execution creates AgentRun records for existing monitoring

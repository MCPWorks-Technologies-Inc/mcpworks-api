# Tasks: MCP Proxy Analytics — Token Savings Tracking and REST API

**Input**: Design documents from `/specs/022-analytics-token-savings/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Tests are included — spec FR-011 and SC-006 explicitly require comprehensive unit tests.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Database migration and model changes that all stories depend on

- [x] T001 Add `input_bytes` column to McpExecutionStat model in src/mcpworks_api/models/mcp_execution_stat.py
- [x] T002 Create Alembic migration for input_bytes column in alembic/versions/20260408_000001_add_input_bytes_to_execution_stats.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core analytics recording changes that MUST be complete before REST API or aggregation stories

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Update `record_execution_stats()` to accept `input_bytes` parameter and remove the `mcp_calls_count == 0` early-return guard in src/mcpworks_api/services/analytics.py
- [x] T004 Update token savings calculation in `record_execution_stats()` to use `max(mcp_bytes, input_bytes)` as the processed-data baseline in src/mcpworks_api/services/analytics.py
- [x] T005 Update `get_token_savings()` query to include `input_bytes` aggregation and new response fields (total_executions, input_bytes, tokens_saved_est) in src/mcpworks_api/services/analytics.py
- [x] T006 Update `TokenSavingsResponse` schema to include new fields (total_executions, input_bytes, input_tokens_est, tokens_saved_est) in src/mcpworks_api/schemas/analytics.py

**Checkpoint**: Foundation ready — analytics service correctly records and queries all execution types

---

## Phase 3: User Story 2 — All Executions Contribute to Analytics (Priority: P1)

**Goal**: Wire analytics recording into both execution paths so every function execution produces analytics data

**Independent Test**: Execute a pure sandbox function (no MCP proxy), then verify an analytics record exists with accurate input_bytes and result_bytes

### Implementation for User Story 2

- [x] T007 [US2] Wire `record_execution_stats()` into tools-mode execution path (dispatch_tool) in src/mcpworks_api/mcp/run_handler.py — measure input_bytes from `json.dumps(arguments)`, result_bytes from `json.dumps(result.output)`
- [x] T008 [US2] Update code-mode execution path (_execute_code_mode) to always record analytics (remove `mcp_calls_count > 0` guard) and measure input_bytes from code size in src/mcpworks_api/mcp/run_handler.py

**Checkpoint**: All executions now produce analytics records — verify by running a function and checking mcp_execution_stats table

---

## Phase 4: User Story 1 — Namespace Owner Views Token Savings (Priority: P1)

**Goal**: Token savings report accurately reflects all execution data including the new input_bytes dimension

**Independent Test**: Call `get_token_savings_report` MCP tool after running mixed executions (tools-mode and code-mode) and verify the report includes all of them

### Implementation for User Story 1

- [x] T009 [US1] Verify existing MCP tool `get_token_savings_report` returns updated response format with new fields (total_executions, input_bytes, tokens_saved_est) — no code changes needed if Foundational phase is correct; validate with manual test

**Checkpoint**: Token savings report shows accurate data for all execution types

---

## Phase 5: User Story 3 — REST API Endpoints (Priority: P2)

**Goal**: Analytics data accessible over HTTP for dashboards and external integrations

**Independent Test**: Authenticate and call each `/v1/analytics/*` endpoint, verify JSON responses match MCP tool output format

### Implementation for User Story 3

- [x] T010 [US3] Create analytics REST API router with token-savings, server-stats, function-stats, and suggestions endpoints in src/mcpworks_api/api/v1/analytics.py
- [x] T011 [US3] Register analytics router in src/mcpworks_api/api/v1/__init__.py

**Checkpoint**: All four REST analytics endpoints return correct data when called with valid auth

---

## Phase 6: User Story 4 — Platform Admin Aggregate (Priority: P2)

**Goal**: Admin endpoint showing platform-wide token savings across all namespaces

**Independent Test**: As admin, call `/v1/admin/analytics/token-savings` and verify cross-namespace totals and top-namespaces list

### Implementation for User Story 4

- [x] T012 [US4] Add `PlatformTokenSavingsResponse` schema in src/mcpworks_api/schemas/analytics.py
- [x] T013 [US4] Implement `get_platform_token_savings()` function in src/mcpworks_api/services/analytics.py — aggregate across all namespaces with top-10 breakdown
- [x] T014 [US4] Add admin analytics endpoint `GET /v1/admin/analytics/token-savings` in src/mcpworks_api/api/v1/admin.py

**Checkpoint**: Admin aggregate endpoint returns platform-wide savings data

---

## Phase 7: User Story 5 — Comprehensive Unit Tests (Priority: P3)

**Goal**: Full unit test coverage for all analytics functions

**Independent Test**: `pytest tests/unit/test_analytics.py -v` passes with meaningful assertions

### Implementation for User Story 5

- [x] T015 [P] [US5] Write unit tests for `record_proxy_call()` and `record_execution_stats()` in tests/unit/test_analytics.py — test with mock DB, verify input_bytes is stored, verify fire-and-forget error handling
- [x] T016 [P] [US5] Write unit tests for `get_token_savings()` in tests/unit/test_analytics.py — test period filtering, zero-data edge case, savings percentage calculation, new response fields
- [x] T017 [P] [US5] Write unit tests for `get_server_stats()` and `get_function_stats()` in tests/unit/test_analytics.py — test aggregation queries with mock data
- [x] T018 [P] [US5] Write unit tests for `suggest_optimizations()` in tests/unit/test_analytics.py — test threshold triggers (large response, high error rate, timeouts, truncations, unused tools)
- [x] T019 [P] [US5] Write unit tests for `get_platform_token_savings()` in tests/unit/test_analytics.py — test cross-namespace aggregation, top-namespaces ranking, empty-data edge case
- [x] T020 [US5] Run full test suite `pytest tests/unit/ -q` and verify no regressions

**Checkpoint**: All analytics tests pass, no regressions in existing test suite

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [x] T021 Run `ruff format` and `ruff check --fix` on all modified files
- [x] T022 Run full unit test suite `pytest tests/unit/ -q` — all tests pass
- [x] T023 Verify quickstart.md examples match actual API responses
- [ ] T024 Commit all changes and push branch

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US2 (Phase 3)**: Depends on Foundational — wiring execution paths
- **US1 (Phase 4)**: Depends on US2 — needs executions recording to verify report
- **US3 (Phase 5)**: Depends on Foundational — REST endpoints use same service layer
- **US4 (Phase 6)**: Depends on Foundational — aggregate uses same service layer
- **US5 (Phase 7)**: Depends on US2, US3, US4 — tests cover all implemented functions
- **Polish (Phase 8)**: Depends on all phases complete

### User Story Dependencies

- **US2 (All executions tracked)**: Foundational only — no other story dependencies
- **US1 (Token savings dashboard)**: Depends on US2 (needs data flowing to verify)
- **US3 (REST API)**: Foundational only — can start in parallel with US2
- **US4 (Admin aggregate)**: Foundational only — can start in parallel with US2/US3
- **US5 (Tests)**: Depends on all implementation stories being complete

### Parallel Opportunities

- T015, T016, T017, T018, T019 can all run in parallel (separate test functions, same file but non-conflicting)
- US3 and US4 can start in parallel after Foundational (different files)
- T001 and T002 can run in parallel (model vs migration)

---

## Implementation Strategy

### MVP First (US2 + US1)

1. Complete Phase 1: Setup (migration + model)
2. Complete Phase 2: Foundational (analytics service changes)
3. Complete Phase 3: US2 (wire all execution paths)
4. Complete Phase 4: US1 (verify token savings report)
5. **STOP and VALIDATE**: Token savings are now visible for all executions

### Incremental Delivery

1. Setup + Foundational → Analytics service ready
2. US2 → All executions tracked → Core value delivered
3. US3 → REST API endpoints → Dashboards can consume data
4. US4 → Admin aggregate → Marketing numbers available
5. US5 → Tests → Quality gate complete

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Most implementation already exists as stashed changes from prior work — apply and validate
- Commit after each phase completion
- The analytics recording is fire-and-forget — failures must never crash executions

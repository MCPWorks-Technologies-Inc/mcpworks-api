# Tasks: Per-Agent Function Visibility and State Access Control

**Input**: Design documents from `/specs/018-agent-access-control/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — unit tests for core rule evaluation logic.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: Database migration and core module scaffolding

- [x] T001 Add `access_rules` JSONB column to agents table via Alembic migration in alembic/versions/

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core rule evaluation engine that all user stories depend on

- [x] T002 Create rule evaluation module in src/mcpworks_api/core/agent_access.py with `check_function_access(rules, service_name, function_name)` and `check_state_access(rules, key)` functions using fnmatch glob matching. Deny-takes-precedence logic. Returns `(allowed: bool, rule_id: str | None)`.
- [x] T003 Create unit tests for rule evaluation in tests/unit/test_agent_access.py covering: no rules (allow all), allow_services, deny_services, allow_functions, deny_functions, allow_keys, deny_keys, deny-takes-precedence, glob patterns, mixed allow+deny.

**Checkpoint**: Rule evaluation engine tested and ready — user story implementation can begin

---

## Phase 3: User Story 1 - Restrict Agent to Specific Services (Priority: P1) MVP

**Goal**: Namespace owners can configure service-level allow/deny rules for agents, enforced on function calls.

**Independent Test**: Configure allow_services rule on an agent, verify allowed service function calls succeed and disallowed service function calls are denied.

### Implementation for User Story 1

- [x] T004 [US1] Add `access_rules` mapped column (JSONB, nullable) to Agent model in src/mcpworks_api/models/agent.py
- [x] T005 [US1] Add function access enforcement in src/mcpworks_api/mcp/run_handler.py — load agent access_rules in the function execution path (near `_load_agent_context`), call `check_function_access()` before `backend.execute()`, raise error with agent name, function name, and rule_id if denied
- [x] T006 [P] [US1] Register `configure_agent_access` tool definition in src/mcpworks_api/mcp/tool_registry.py with input schema from contracts/mcp-tools.md
- [x] T007 [P] [US1] Register `list_agent_access_rules` tool definition in src/mcpworks_api/mcp/tool_registry.py
- [x] T008 [P] [US1] Register `remove_agent_access_rule` tool definition in src/mcpworks_api/mcp/tool_registry.py
- [x] T009 [US1] Implement `_configure_agent_access` handler in src/mcpworks_api/mcp/create_handler.py — validate rule type/patterns, generate rule ID (`r-` + 8 hex), append to agent's access_rules JSONB, flush
- [x] T010 [US1] Implement `_list_agent_access_rules` handler in src/mcpworks_api/mcp/create_handler.py — load agent, return function_rules and state_rules from access_rules JSONB
- [x] T011 [US1] Implement `_remove_agent_access_rule` handler in src/mcpworks_api/mcp/create_handler.py — find rule by ID across function_rules and state_rules, remove it, flush
- [x] T012 [US1] Wire the three new tool names into the TOOL_SCOPES dict and dispatch map in src/mcpworks_api/mcp/create_handler.py

**Checkpoint**: Service-level function access control is fully functional and testable

---

## Phase 4: User Story 2 - Restrict Agent State Key Access (Priority: P2)

**Goal**: Namespace owners can configure state key allow/deny rules for agents, enforced on state operations.

**Independent Test**: Configure allow_keys rule on an agent, verify allowed state key operations succeed and disallowed state key operations are denied.

### Implementation for User Story 2

- [x] T013 [US2] Add state access enforcement to `_get_agent_state` in src/mcpworks_api/mcp/create_handler.py — load agent access_rules, call `check_state_access()` before service.get_state(), return error if denied
- [x] T014 [US2] Add state access enforcement to `_set_agent_state` in src/mcpworks_api/mcp/create_handler.py — call `check_state_access()` before service.set_state()
- [x] T015 [US2] Add state access enforcement to `_delete_agent_state` in src/mcpworks_api/mcp/create_handler.py — call `check_state_access()` before service.delete_state()
- [x] T016 [US2] Add state key filtering to `_list_agent_state_keys` in src/mcpworks_api/mcp/create_handler.py — filter returned keys through `check_state_access()`, exclude denied keys

**Checkpoint**: State access control is fully functional and testable

---

## Phase 5: User Story 3 - Function-Level Deny Rules with Glob Patterns (Priority: P2)

**Goal**: Fine-grained function-level deny rules with glob patterns, deny-takes-precedence over allow.

**Independent Test**: Configure deny_functions rule with glob pattern like `admin.delete_*`, verify matching functions are blocked while non-matching functions proceed.

### Implementation for User Story 3

- [x] T017 [US3] Add unit tests for combined allow+deny scenarios in tests/unit/test_agent_access.py — allow_services "admin" + deny_functions "admin.delete_*", verify deny wins

**Checkpoint**: Function-level deny with globs works — this is primarily a validation that the rule engine from Phase 2 handles the combined case correctly

---

## Phase 6: User Story 4 - View and Manage Access Rules (Priority: P3)

**Goal**: Namespace owners can add, list, and remove access rules with unique IDs.

**Independent Test**: Add multiple rules, list them to verify IDs/types/patterns, remove one by ID, verify removal.

### Implementation for User Story 4

- [x] T018 [US4] Add unit tests for rule management operations in tests/unit/test_agent_access.py — add_rule, list_rules, remove_rule by ID, verify remaining count

**Checkpoint**: Rule management is testable end-to-end via MCP tools (already implemented in US1)

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T019 Add structlog logging for access denied events in src/mcpworks_api/core/agent_access.py — log agent name, resource, rule_id, denial reason
- [x] T020 Run full unit test suite `pytest tests/unit/ -q` and verify no regressions
- [x] T021 Run `ruff format src/ tests/ && ruff check --fix src/ tests/` to ensure code quality

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — migration first
- **Foundational (Phase 2)**: Depends on Phase 1 (migration must exist for model column)
- **User Story 1 (Phase 3)**: Depends on Phase 2 (rule engine)
- **User Story 2 (Phase 4)**: Depends on Phase 2 (rule engine) — can run parallel to US1
- **User Story 3 (Phase 5)**: Depends on Phase 2 (rule engine) — validation tests only
- **User Story 4 (Phase 6)**: Depends on US1 (management tools implemented there) — validation tests only
- **Polish (Phase 7)**: Depends on all user stories

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Foundational only — implements management tools + function enforcement
- **User Story 2 (P2)**: Depends on Foundational only — uses same rule engine, different enforcement point
- **User Story 3 (P2)**: Depends on Foundational — tests combined allow+deny (rule engine already supports this)
- **User Story 4 (P3)**: Depends on US1 — management tools are built there, this phase validates them

### Within Each User Story

- Tool registration (T006-T008) can run in parallel
- Handler implementation (T009-T011) depends on tool registration
- Enforcement (T005) depends on core module (T002)

### Parallel Opportunities

- T006, T007, T008 can all run in parallel (different tool definitions, same file but independent entries)
- T013, T014, T015 can all run in parallel (different methods in same file)
- US1 and US2 can run in parallel after foundational phase

---

## Parallel Example: User Story 1

```bash
# Launch tool registrations in parallel:
Task: "Register configure_agent_access tool in tool_registry.py"
Task: "Register list_agent_access_rules tool in tool_registry.py"
Task: "Register remove_agent_access_rule tool in tool_registry.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Migration
2. Complete Phase 2: Rule evaluation engine + tests
3. Complete Phase 3: User Story 1 (function enforcement + management tools)
4. **STOP and VALIDATE**: Test service-level access control end-to-end
5. Deploy if ready — agents can now be restricted to specific services

### Incremental Delivery

1. Migration + Rule engine → Foundation ready
2. Add US1 → Function access control works → Deploy (MVP!)
3. Add US2 → State access control works → Deploy
4. Add US3+US4 → Validation tests → Deploy
5. Polish → Logging, cleanup → Deploy

---

## Notes

- Total tasks: 21
- US1: 9 tasks (core implementation)
- US2: 4 tasks (state enforcement)
- US3: 1 task (validation test)
- US4: 1 task (validation test)
- Setup/Foundation: 3 tasks
- Polish: 3 tasks
- Parallel opportunities: T006-T008, T013-T015, US1/US2 after foundation
- Suggested MVP: Phase 1 + Phase 2 + Phase 3 (User Story 1 only — 12 tasks)

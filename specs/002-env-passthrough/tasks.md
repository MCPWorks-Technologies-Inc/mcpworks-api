# Tasks: Environment Variable Passthrough

**Input**: Design documents from `/specs/002-env-passthrough/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included — spec Section 10 explicitly defines 17+ unit test cases and integration tests.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths included in all descriptions

## User Stories (from spec.md)

| ID | Title | Priority | Spec Section |
|----|-------|----------|-------------|
| US1 | Function Needs an API Key (core passthrough) | P1 - Must Have | 2.1, REQ-ENV-001/002/003/004/005/008 |
| US2 | Discovery via tools/list | P2 - Must Have | 2.1 step 3, REQ-ENV-006 |
| US3 | AI Assistant Diagnoses Missing Env Vars | P3 - Should Have | 2.2, REQ-ENV-007 |

---

## Phase 1: Foundational (Data Model + Core Module)

**Purpose**: Schema changes, migration, and core validation logic that ALL user stories depend on.

### Data Model

- [ ] T001 [P] Add `required_env` and `optional_env` columns to FunctionVersion model in `src/mcpworks_api/models/function_version.py` — both `ARRAY(String)`, nullable, matching existing `requirements` column pattern. Add `@validates` for env var name format.
- [ ] T002 [P] Add `required_env` and `optional_env` fields to `FunctionVersionCreate`, `FunctionVersionResponse`, `FunctionCreate`, and `FunctionUpdate` schemas in `src/mcpworks_api/schemas/function.py` — Pydantic `list[str] | None` with Field validators matching blocklist rules.
- [ ] T003 Create Alembic migration `alembic/versions/20260219_000001_add_env_declarations_to_function_versions.py` — `ALTER TABLE function_versions ADD COLUMN required_env VARCHAR[] DEFAULT NULL; ADD COLUMN optional_env VARCHAR[] DEFAULT NULL;`

### Core Validation Module

- [ ] T004 Create `src/mcpworks_api/mcp/env_passthrough.py` — implement `extract_env_vars(request: Request) -> dict[str, str]` with: base64 decode, JSON parse, size validation (32KB max), key count (64 max), key name regex (`^[A-Z][A-Z0-9_]{0,127}$`), exact blocklist (PATH, HOME, etc.), prefix blocklist (LD_, PYTHON, NSJAIL, SSL_, MCPWORKS_INTERNAL_), reserved prefix (MCPWORKS_), value size (8KB), null byte check. Raise `EnvPassthroughError` on validation failures. Return empty dict if header absent.
- [ ] T005 Implement `filter_env_for_function(env_vars: dict, required_env: list | None, optional_env: list | None) -> dict` in `src/mcpworks_api/mcp/env_passthrough.py` — returns intersection of provided vars and declared vars. Also implement `check_required_env(env_vars: dict, required_env: list | None) -> list[str]` that returns list of missing required var names (empty list = all present).

### Backend Interface

- [ ] T006 Add `sandbox_env: dict[str, str] | None = None` parameter to `Backend.execute()` abstract method in `src/mcpworks_api/backends/base.py` — update signature, docstring, and type hints. Backward compatible (default None).

### Observability

- [ ] T007 Add structlog processor `_strip_env_vars(logger, method_name, event_dict)` that removes fields named `sandbox_env`, `env_vars`, `env_dict` from log events. Wire into existing structlog configuration in `src/mcpworks_api/core/logging.py` (or wherever structlog is configured).

### Tests — Foundational

- [ ] T008 Create `tests/unit/test_env_passthrough.py` with all 17 unit test cases from spec Section 10.1: valid base64 JSON → correct dict; invalid base64 → error; valid base64/invalid JSON → error; payload too large → error; too many keys → error; blocked exact name (PATH) → error; blocked prefix (LD_PRELOAD) → error; reserved prefix (MCPWORKS_) → error; invalid key format → error; value too large → error; null byte → error; absent header → empty dict; non-string value → error; filter with required_env; filter with no declarations; undeclared vars dropped; missing required var detection.

**Checkpoint**: Data model, validation module, and backend interface ready. All unit tests passing.

---

## Phase 2: US1 — Core Passthrough (Priority: P1) MVP

**Goal**: Functions can read user-provided env vars via `os.environ` inside the sandbox. Zero persistence. Full pipeline: header → validate → filter → sandbox file → os.environ → cleanup.

**Independent Test**: Create a function with `required_env: ["TEST_KEY"]`, send header with `TEST_KEY=hello`, verify function returns `os.environ["TEST_KEY"]` = `"hello"`. Verify without header, function fails with `missing_env` error. Verify env vars not in logs or database.

### Server-Side Pipeline

- [ ] T009 [US1] Modify `call_tool()` in `src/mcpworks_api/mcp/transport.py` (line ~225) — after getting request from `_current_request` ContextVar, call `extract_env_vars(request)` from the new env_passthrough module. Catch `EnvPassthroughError` and raise `ValueError` with message. Pass the resulting `sandbox_env` dict to `handler.dispatch_tool(name, args, sandbox_env=sandbox_env)`.
- [ ] T010 [US1] Modify `dispatch_tool()` in `src/mcpworks_api/mcp/run_handler.py` (line ~152) — add `sandbox_env: dict[str, str] | None = None` parameter. After loading `function` and `version`, call `filter_env_for_function()` and `check_required_env()` from env_passthrough. If required vars missing, return `MCPToolResult(isError=True)` with `missing_env` error JSON (per contracts). Pass filtered dict to `backend.execute(..., sandbox_env=filtered_env)`.
- [ ] T011 [US1] Modify `_execute_code_mode()` in `src/mcpworks_api/mcp/run_handler.py` (line ~225) — add `sandbox_env` parameter, pass through to `backend.execute()`. Update `call_tool()` in transport.py to pass `sandbox_env` for code-mode calls too.

### Sandbox Backend — File Write

- [ ] T012 [US1] Modify `SandboxBackend.execute()` in `src/mcpworks_api/backends/sandbox.py` (line ~156) — accept `sandbox_env` param, pass to both `_execute_dev_mode()` and `_execute_nsjail()`.
- [ ] T013 [US1] Modify `_execute_nsjail()` in `src/mcpworks_api/backends/sandbox.py` (line ~311) — accept `sandbox_env` param. Before spawning nsjail, if `sandbox_env` is non-empty, write `json.dumps(sandbox_env)` to `exec_dir / ".sandbox_env.json"`. After writing the file, call `dict.clear()` on `sandbox_env` for defense-in-depth memory cleanup.
- [ ] T014 [US1] Modify `_execute_dev_mode()` in `src/mcpworks_api/backends/sandbox.py` (line ~212) — accept `sandbox_env` param. If non-empty, write `.sandbox_env.json` to `exec_dir` before spawning subprocess.

### Sandbox Shell — File Copy

- [ ] T015 [US1] Modify `deploy/nsjail/spawn-sandbox.sh` — after the existing exec_token copy block (lines 94-98), add: if `.sandbox_env.json` exists in `$EXEC_DIR`, copy it to `$WORKSPACE/.sandbox_env.json`, then `rm -f` the source. Chown is already handled by the blanket `chown -R 65534:65534` on line 101.

### Sandbox Python — Read, Inject, Delete

- [ ] T016 [US1] Modify `deploy/nsjail/execute.py` — after the exec_token block (lines 32-41), add env var injection: try to open `/sandbox/.sandbox_env.json`, `json.load()` it, `os.unlink()` immediately, then `os.environ.update()` with the parsed dict. Wrap in `try/except (FileNotFoundError, Exception): pass` — silently skip if file missing or malformed (defense-in-depth, matches exec_token pattern).

### Create Handler — Accept Env Declarations

- [ ] T017 [US1] Modify `make_function` and `update_function` tool handlers in `src/mcpworks_api/mcp/create_handler.py` — accept `required_env` and `optional_env` optional list parameters. Pass through to `FunctionService` which stores them on `FunctionVersion`. Validate names against the same blocklist rules from env_passthrough module before saving.

### Tests — US1

- [ ] T018 [US1] Add integration test in `tests/unit/test_env_passthrough.py` (or new `tests/integration/test_env_pipeline.py`) — test `filter_env_for_function()` + `check_required_env()` together: function with `required_env=["A"]` receiving `{"A": "1", "B": "2"}` gets only `{"A": "1"}`. Function with no declarations gets `{}`. Missing required var returns error list.

**Checkpoint**: Full pipeline works. Function can read `os.environ["KEY"]` inside sandbox. Missing vars fail fast. Env vars never persisted.

---

## Phase 3: US2 — Discovery via tools/list (Priority: P2)

**Goal**: AI assistants see env var requirements in tool descriptions when calling `tools/list`.

**Independent Test**: Create function with `required_env: ["OPENAI_API_KEY"]`, call `tools/list`, verify description contains `Required env: OPENAI_API_KEY`.

### Implementation

- [ ] T019 [US2] Modify `get_tools()` in `src/mcpworks_api/mcp/run_handler.py` (line ~106) — when building MCPTool for each function, check if the FunctionVersion has `required_env` or `optional_env`. If so, append `\n\nRequired env: X, Y` and/or `\nOptional env: Z` to the tool description string. Ensure FunctionVersion env fields are loaded in the `list_all_for_namespace()` query.
- [ ] T020 [US2] Modify `describe_function` tool response in `src/mcpworks_api/mcp/create_handler.py` — include `required_env` and `optional_env` in the version details returned by `describe_function`.

**Checkpoint**: `tools/list` shows env requirements. `describe_function` shows env declarations.

---

## Phase 4: US3 — Diagnostic Tool (Priority: P3)

**Goal**: AI assistants can call `_env_status` to check which env vars are configured vs missing across the namespace.

**Independent Test**: Create two functions — one with `required_env: ["A"]`, one with none. Call `_env_status` with header containing `A`. Verify response shows `configured: ["A"]`, both functions `status: "ready"`. Call without header, verify `missing_required: ["A"]`.

### Implementation

- [ ] T021 [US3] Add `_env_status` to `get_tools()` in `src/mcpworks_api/mcp/run_handler.py` — append an MCPTool with name `_env_status`, description per contracts (Section 4), and empty inputSchema. Only include in tools-mode (not code-mode).
- [ ] T022 [US3] Add `_env_status` dispatch case in `dispatch_tool()` in `src/mcpworks_api/mcp/run_handler.py` — when `name == "_env_status"`, load all functions for namespace, collect all `required_env`/`optional_env` declarations, compare against provided `sandbox_env` dict, return JSON per contracts Section 4 response format (configured, missing_required, missing_optional, per-function status).

**Checkpoint**: `_env_status` tool works. AI assistants can diagnose env configuration.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Security hardening, observability, backward compatibility verification

- [ ] T023 [P] Add Prometheus metrics in `src/mcpworks_api/mcp/transport.py` — `env_passthrough_requests_total` Counter (requests with header present), `env_passthrough_vars_count` Histogram (var count per request), `env_passthrough_errors_total` Counter labeled by type. Follow existing ORDER-017 pattern.
- [ ] T024 [P] Verify backward compatibility — run existing test suite (`pytest tests/unit/ --ignore=tests/unit/test_mcp_protocol.py --ignore=tests/unit/test_mcp_router.py -q`) and confirm zero regressions. Absent header must produce empty dict, functions without env declarations must work unchanged.
- [ ] T025 Security audit — manually trace all code paths where `sandbox_env` dict flows. Verify: (1) never assigned to model fields, (2) never passed to structlog bind, (3) never included in error messages to client beyond "missing_env" name list, (4) `dict.clear()` called after file write, (5) structlog processor strips env fields.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundational)**: No dependencies — start immediately
- **Phase 2 (US1 Core Passthrough)**: Depends on Phase 1 completion (T001-T008)
- **Phase 3 (US2 Discovery)**: Depends on Phase 1 (T001-T002 for env fields on model/schema). Can start in parallel with US1 if needed.
- **Phase 4 (US3 Diagnostic)**: Depends on Phase 2 (needs `sandbox_env` threading in dispatch_tool)
- **Phase 5 (Polish)**: Depends on Phases 2-4 completion

### User Story Dependencies

- **US1 (Core Passthrough)**: Requires foundational T001-T008. This IS the MVP.
- **US2 (Discovery)**: Requires T001-T002 (model/schema fields). Independent of US1 pipeline.
- **US3 (Diagnostic)**: Requires US1 T009-T010 (sandbox_env in dispatch_tool). Builds on US1.

### Within Each Phase

- Tasks marked [P] can run in parallel (different files)
- Sequential tasks depend on previous tasks in the phase

### Parallel Opportunities

**Phase 1 parallel group**: T001 + T002 (model + schema, different files). Then T003 (migration depends on T001). Then T004 + T005 (new module, no deps on model). T006 (backend interface). T007 (logging). T008 (tests, depends on T004-T005).

**Phase 2 parallel group**: T012 + T014 (both sandbox.py changes but different methods). T015 + T016 (shell script + python, different files). T009 + T017 (transport.py + create_handler.py, different files).

---

## Parallel Example: Phase 1

```bash
# Parallel group 1: Model + Schema (different files)
Task: T001 "Add env columns to FunctionVersion in models/function_version.py"
Task: T002 "Add env fields to Pydantic schemas in schemas/function.py"

# Then sequential: Migration (depends on model)
Task: T003 "Create Alembic migration"

# Parallel group 2: Core module + Backend interface + Logging (all different files)
Task: T004 "Create env_passthrough.py extraction/validation"
Task: T005 "Create env_passthrough.py filtering"
Task: T006 "Add sandbox_env to Backend.execute()"
Task: T007 "Add structlog redaction processor"

# Then: Tests (depends on T004-T005)
Task: T008 "Create test_env_passthrough.py"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Foundational (T001-T008) — ~4 hours
2. Complete Phase 2: US1 Core Passthrough (T009-T018) — ~6 hours
3. **STOP and VALIDATE**: Deploy to dev, test with real MCP client
4. Ship if US1 works end-to-end

### Incremental Delivery

1. Phase 1 + Phase 2 (US1) → MVP: Functions can use env vars
2. Add Phase 3 (US2) → tools/list shows requirements
3. Add Phase 4 (US3) → _env_status diagnostic tool
4. Phase 5 → Polish, metrics, security audit

### Summary

| Metric | Count |
|--------|-------|
| Total tasks | 25 |
| Phase 1 (Foundational) | 8 |
| Phase 2 (US1 MVP) | 10 |
| Phase 3 (US2 Discovery) | 2 |
| Phase 4 (US3 Diagnostic) | 2 |
| Phase 5 (Polish) | 3 |
| Parallel opportunities | 6 groups |
| MVP scope | Phase 1 + Phase 2 (18 tasks) |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Spec explicitly requests tests (Section 10) — included in T008 and T018
- Commit after each phase completion
- Security is paramount — every task touching env vars must ensure zero persistence

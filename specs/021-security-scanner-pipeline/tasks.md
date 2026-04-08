# Tasks: Pluggable Security Scanner Pipeline

**Input**: Design documents from `/specs/021-security-scanner-pipeline/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Unit tests for pipeline evaluation, each scanner type, and short-circuit behavior.

**Organization**: Tasks grouped by user story. US1 (built-in defense out of the box) is the MVP.

**Note**: No backward compatibility wrappers. Old modules (`sandbox/injection_scan.py`, `core/trust_boundary.py`) are deleted and call sites updated directly.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

**Purpose**: Migration, scanner interface, and module scaffolding

- [x] T001 Add `scanner_pipeline` JSONB column to namespaces table via Alembic migration in alembic/versions/
- [x] T002 Create scanner interface: `ScanVerdict` dataclass and `BaseScanner` abstract class with `async scan(content, context) -> ScanVerdict` in src/mcpworks_api/core/scanners/base.py. Include `ScanContext` dataclass (direction, namespace, service, function, execution_id, output_trust) and `PipelineResult` dataclass (final_action, final_score, verdicts list, total_ms, content_hash)

---

## Phase 2: Foundational

**Purpose**: Pipeline evaluator and built-in scanners — must complete before any user story

- [x] T003 Create pattern scanner (refactored from sandbox/injection_scan.py) implementing BaseScanner in src/mcpworks_api/core/scanners/pattern_scanner.py — move all patterns, normalize_text, scan logic. Returns ScanVerdict with action=flag/pass, score based on severity, matched pattern as reason
- [x] T004 [P] Create secret scanner (refactored from sandbox/credential_scan.py) implementing BaseScanner in src/mcpworks_api/core/scanners/secret_scanner.py — detects and redacts API keys, JWTs, connection strings. Returns flag verdict when secrets found, modifies content in-place via a `scan_and_redact(content) -> (cleaned_content, verdict)` method
- [x] T005 [P] Create trust boundary scanner implementing BaseScanner in src/mcpworks_api/core/scanners/trust_boundary_scanner.py — wraps output with trust markers based on output_trust from ScanContext. Always returns pass verdict (wrapping is the action, not blocking)
- [x] T006 Create scanner __init__.py with BUILTIN_SCANNERS registry mapping names to classes in src/mcpworks_api/core/scanners/__init__.py
- [x] T007 Create pipeline evaluator in src/mcpworks_api/core/scanner_pipeline.py — loads scanner config (from namespace JSONB or DEFAULT_PIPELINE), instantiates scanners, evaluates in order, short-circuits on block, returns PipelineResult. Includes `evaluate_pipeline(content, context, pipeline_config) -> PipelineResult` async function
- [x] T008 Write unit tests for pipeline evaluator in tests/unit/test_scanner_pipeline.py — test: all-pass, single-flag, single-block (short-circuit), mixed verdicts (highest severity wins), empty pipeline, fail-open default, scanner exception handling
- [x] T009 [P] Write unit tests for pattern scanner in tests/unit/test_pattern_scanner.py — test: known injection patterns detected, clean text passes, unicode normalization, base64 decode, severity scoring
- [x] T010 Delete sandbox/injection_scan.py and core/trust_boundary.py — update all import sites to use new scanner modules

**Checkpoint**: Scanner interface, pipeline evaluator, and built-in scanners tested and ready

---

## Phase 3: User Story 1 - Built-in Defense Out of the Box (Priority: P1) MVP

**Goal**: Default pipeline runs on every function execution. Outputs scanned, flagged, and trust-marked automatically. Scan results in execution records.

**Independent Test**: Execute a function returning injection text → verify trust markers applied and scan results in execution detail.

### Implementation

- [x] T011 [US1] Add `scanner_pipeline` mapped column (JSONB, nullable) to Namespace model in src/mcpworks_api/models/namespace.py
- [x] T012 [US1] Integrate pipeline into RunMCPHandler.dispatch_tool() in src/mcpworks_api/mcp/run_handler.py — after backend.execute(), call evaluate_pipeline() on the output. Apply trust boundary wrapping and secret redaction based on verdicts. Store scan results in execution record backend_metadata under "scan_results" key
- [x] T013 [US1] Update mcp_rules.py evaluate_response_rules() to use pattern scanner and trust boundary scanner from core/scanners/ instead of deleted modules in src/mcpworks_api/core/mcp_rules.py
- [x] T014 [US1] Update any remaining imports of sandbox.injection_scan or core.trust_boundary across the codebase — grep and fix all broken references
- [x] T015 [US1] Update existing injection scan tests to use new pattern scanner in tests/unit/test_output_sanitizer.py (or wherever existing injection tests live)

**Checkpoint**: Every function execution runs through the default scanner pipeline. Scan results visible in execution records.

---

## Phase 4: User Story 2 - Webhook Scanner (Priority: P1)

**Goal**: Users can register external HTTP scanners that participate in the pipeline.

**Independent Test**: Register a webhook scanner URL, execute a function, verify the webhook receives the scan request and its verdict is incorporated.

### Implementation

- [x] T016 [US2] Create webhook scanner implementing BaseScanner in src/mcpworks_api/core/scanners/webhook_scanner.py — POST content+context to configured URL via httpx, parse response into ScanVerdict, handle timeout (skip with warning), handle errors (skip with warning)
- [x] T017 [US2] Write unit tests for webhook scanner with httpx mock in tests/unit/test_webhook_scanner.py — test: successful scan, timeout handling, error handling, invalid response handling, custom headers

**Checkpoint**: Webhook scanners work end-to-end

---

## Phase 5: User Story 3 - Python Scanner (Priority: P2)

**Goal**: Self-hosters can register local Python callables (e.g., LLM Guard) as scanners.

**Independent Test**: Register a Python scanner with a module path, execute a function, verify the callable runs and its verdict is incorporated.

### Implementation

- [x] T018 [US3] Create python scanner implementing BaseScanner in src/mcpworks_api/core/scanners/python_scanner.py — import module dynamically, call configured function, handle import errors (mark unavailable), handle runtime errors (skip with warning)
- [x] T019 [US3] Write unit tests for python scanner in tests/unit/test_python_scanner.py — test: successful scan with mock module, import error handling, runtime error handling, init_kwargs passing

**Checkpoint**: Python scanners work end-to-end

---

## Phase 6: User Story 4+6 - Per-Namespace Config and MCP Tools (Priority: P2-P3)

**Goal**: Namespace owners manage their scanner pipeline via MCP tools. Each namespace can have a custom pipeline.

**Independent Test**: Add a webhook scanner via MCP tool, list pipeline, verify it appears. Remove it, verify gone. Execute function in namespace, verify custom pipeline is used.

### Implementation

- [x] T020 [P] [US4] Register `add_security_scanner` tool definition in src/mcpworks_api/mcp/tool_registry.py
- [x] T021 [P] [US4] Register `list_security_scanners` tool definition in src/mcpworks_api/mcp/tool_registry.py
- [x] T022 [P] [US4] Register `update_security_scanner` tool definition in src/mcpworks_api/mcp/tool_registry.py
- [x] T023 [P] [US4] Register `remove_security_scanner` tool definition in src/mcpworks_api/mcp/tool_registry.py
- [x] T024 [US6] Implement `_add_security_scanner`, `_list_security_scanners`, `_update_security_scanner`, `_remove_security_scanner` handlers in src/mcpworks_api/mcp/create_handler.py — validate scanner config, generate scanner ID, read/write namespace scanner_pipeline JSONB. Wire into TOOL_SCOPES and dispatch map

**Checkpoint**: Full scanner pipeline management via MCP tools

---

## Phase 7: User Story 5 - Scan Decision Observability (Priority: P2)

**Goal**: Every scan decision is logged and queryable via execution debugging API.

**Independent Test**: Execute a function that triggers a flag, query execution detail, verify per-scanner verdicts are present.

### Implementation

- [x] T025 [US5] Add structlog events for pipeline evaluation in src/mcpworks_api/core/scanner_pipeline.py — log: pipeline_started, scanner_completed (per scanner with timing), pipeline_completed (final verdict), scanner_error, scanner_timeout
- [x] T026 [US5] Verify scan_results are queryable via describe_execution MCP tool and GET /v1/executions/{id} — scan results should appear in the stdout/stderr/backend_metadata section of execution detail

**Checkpoint**: Full observability — every scan decision logged and queryable

---

## Phase 8: Polish

- [x] T027 Run full unit test suite `pytest tests/unit/ -q` and verify no regressions
- [x] T028 Run `ruff format src/ tests/ && ruff check --fix src/ tests/`
- [x] T029 Verify no remaining imports of `sandbox.injection_scan` or `core.trust_boundary` via `grep -r "injection_scan\|trust_boundary" src/ --include="*.py" | grep -v scanners/ | grep -v __pycache__`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: Migration first
- **Phase 2**: Depends on Phase 1 — scanner interface and pipeline evaluator
- **Phase 3 (US1)**: Depends on Phase 2 — integrates pipeline into dispatch path. **This is MVP.**
- **Phase 4 (US2)**: Depends on Phase 2 — adds webhook scanner type
- **Phase 5 (US3)**: Depends on Phase 2 — adds python scanner type
- **Phase 6 (US4+6)**: Depends on Phase 2 — MCP tools for pipeline management
- **Phase 7 (US5)**: Depends on Phase 3 — observability requires pipeline integration
- **Phase 8**: After all user stories

### Parallel Opportunities

- T004, T005 can run in parallel with T003 (different scanner files)
- T009 can run in parallel with T008 (different test files)
- Phase 4 (webhook) and Phase 5 (python) can run in parallel after Phase 2
- T020-T023 can all run in parallel (different tool definitions)
- Phase 6 can run in parallel with Phase 4+5

---

## Implementation Strategy

### MVP (User Story 1)

1. Phase 1: Migration
2. Phase 2: Scanner interface + pipeline + built-in scanners + tests
3. Phase 3: Wire into dispatch path + delete old modules
4. **STOP and VALIDATE**: Execute function with injection content, verify trust markers and scan results
5. Deploy — every namespace gets baseline defense automatically

### Incremental

1. MVP → built-in defense works out of the box
2. Add US2 → webhook scanners for external services
3. Add US3 → python scanners for local ML models
4. Add US4+6 → MCP tools for pipeline management
5. Add US5 → full scan decision observability
6. Polish → final cleanup

---

## Notes

- Total: 29 tasks
- Setup/Foundation: 10 tasks (scanner interface, pipeline, built-in scanners, tests)
- US1 (MVP): 5 tasks (integration + old module deletion)
- US2 (webhook): 2 tasks
- US3 (python): 2 tasks
- US4+6 (MCP tools): 5 tasks
- US5 (observability): 2 tasks
- Polish: 3 tasks
- **No backward compat wrappers** — old modules deleted, call sites updated directly

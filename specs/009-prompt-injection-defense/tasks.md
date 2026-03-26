# Tasks: Prompt Injection Defense

**Input**: Design documents from `/specs/009-prompt-injection-defense/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/mcp-tools.md, quickstart.md

**Tests**: Included per spec (Section 9 — unit, integration, adversarial tests).

**Organization**: Tasks grouped by user story from spec.md.
- US1 = Function trust classification + wrapping (P1)
- US2 = Injection scanner (P1)
- US3 = MCP server rules engine (P1)
- US4 = RemoteMCP tool trust overrides (P2)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Database migration, new modules

- [x] T001 Create Alembic migration for output_trust + rules columns
- [x] T002 [P] Create injection scanner module at src/mcpworks_api/sandbox/injection_scan.py
- [x] T003 [P] Create trust boundary module at src/mcpworks_api/core/trust_boundary.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add output_trust to Function model, wire into existing make/update function

- [ ] T004 Add `output_trust` field to Function model in src/mcpworks_api/models/function.py — VARCHAR(10), NOT NULL, validate against ('prompt', 'data')
- [ ] T005 Add `rules` field to NamespaceMcpServer model in src/mcpworks_api/models/namespace_mcp_server.py — JSONB, NOT NULL, default `{"request":[],"response":[]}`
- [ ] T006 Create auto-classification helper in src/mcpworks_api/sandbox/injection_scan.py — suggest_trust_level(code, required_env) → str that analyzes code for mcp__ imports and external indicators, returns "data" or "prompt" with reason string

**Checkpoint**: Foundation ready

---

## Phase 3: User Story 1 — Function Trust Classification + Wrapping (Priority: P1) MVP

**Goal**: Functions require `output_trust` on creation. Functions with `output_trust: data` have their results wrapped with trust boundary markers visible to the AI.

**Independent Test**: Create function with `output_trust=data` → execute → verify result wrapped with `[UNTRUSTED_OUTPUT...]`. Create function with `output_trust=prompt` → execute → verify no wrapping. Create function without `output_trust` → verify rejection with suggestion.

### Tests for User Story 1

- [ ] T007 [P] [US1] Unit test for trust boundary wrapping in tests/unit/test_trust_boundary.py — wrap_function_output produces correct markers, wrap_mcp_response produces correct markers, markers are visible string wrapping (not metadata)
- [ ] T008 [P] [US1] Unit test for auto-classification in tests/unit/test_injection_scan.py — code with mcp__ imports suggests "data", code with no externals suggests "prompt", required_env with API_KEY suggests "data"

### Implementation for User Story 1

- [ ] T009 [US1] Modify make_function handler in src/mcpworks_api/mcp/create_handler.py — require `output_trust` parameter, reject with auto-classification suggestion if omitted, validate value is "prompt" or "data", pass to FunctionService.create
- [ ] T010 [US1] Modify update_function handler in src/mcpworks_api/mcp/create_handler.py — accept optional `output_trust` parameter, pass to FunctionService.update
- [ ] T011 [US1] Update make_function tool schema in src/mcpworks_api/mcp/tool_registry.py — add `output_trust` as required property with enum ["prompt", "data"] and description explaining the difference
- [ ] T012 [US1] Update update_function tool schema in src/mcpworks_api/mcp/tool_registry.py — add `output_trust` as optional property
- [ ] T013 [US1] Modify run handler in src/mcpworks_api/mcp/run_handler.py — after sandbox execution, check function's `output_trust`. If "data", wrap the result text with `wrap_function_output()` before returning MCPToolResult
- [ ] T014 [US1] Update describe_function handler to include `output_trust` in response in src/mcpworks_api/mcp/create_handler.py

**Checkpoint**: Functions have mandatory trust level. Data-trust functions get wrapped results.

---

## Phase 4: User Story 2 — Injection Scanner (Priority: P1)

**Goal**: Pattern-based scanner detects common prompt injection patterns in text. Integrated into MCP proxy response path. Detected injections logged as security events.

**Independent Test**: Pass known injection payload ("ignore all previous instructions") to scanner → verify detection with correct pattern name and severity. Pass normal English text → verify no false positives. Pass JSON with nested injection → verify recursive scan finds it.

### Tests for User Story 2

- [ ] T015 [P] [US2] Unit test for injection scanner in tests/unit/test_injection_scan.py — all 8 pattern categories detect their targets, scan_json_for_injections finds nested injections, no false positives on corpus of 20 normal English sentences
- [ ] T016 [P] [US2] Create adversarial test corpus at tests/fixtures/injection_payloads.txt — 30+ known injection payloads from OWASP/Garak databases

### Implementation for User Story 2

- [ ] T017 [US2] Integrate scanner into MCP proxy in src/mcpworks_api/core/mcp_proxy.py — after receiving MCP response text, run scan_for_injections. Based on strictness: warn (log only), flag (add INJECTION_WARNING markers), block (redact). Log security event via fire_security_event for any detection.
- [ ] T018 [US2] Add security event type for injection detection in src/mcpworks_api/models/security_event.py — add "prompt_injection_detected" to allowed event types if not already present
- [ ] T019 [US2] Integrate scanner into run handler for data-trust functions in src/mcpworks_api/mcp/run_handler.py — scan result text of `output_trust: data` functions before wrapping, include injections_found count in wrapper

**Checkpoint**: Injections detected and flagged in both proxy and function paths.

---

## Phase 5: User Story 3 — MCP Server Rules Engine (Priority: P1)

**Goal**: Per-MCP-server request and response rules managed via MCP tools. Rules enforced in the proxy. Default rules applied on new server creation.

**Independent Test**: Add `block_tool` rule → call blocked tool → verify rejection. Add `inject_param` rule → verify parameter added. Add `scan_injection` rule with strictness=flag → call tool returning injection → verify markers added. Create new MCP server → verify default rules present.

### Implementation for User Story 3

- [ ] T020 [US3] Create rule evaluation engine in src/mcpworks_api/core/mcp_rules.py — evaluate_request_rules(rules, tool_name, arguments) → modified arguments or RuleBlockError, evaluate_response_rules(rules, tool_name, response_text, scanner) → modified response text. Support all rule types from spec: inject_param, block_tool, require_param, cap_param, wrap_trust_boundary, scan_injection, strip_html, inject_header, redact_fields. Use fnmatch for tool glob matching.
- [ ] T021 [US3] Integrate rule engine into MCP proxy in src/mcpworks_api/core/mcp_proxy.py — load server.rules, evaluate request rules before MCP call (reject if blocked), evaluate response rules after MCP call (wrap, scan, strip, redact)
- [ ] T022 [US3] Add default rules on server creation in src/mcpworks_api/services/mcp_server.py — in add_server(), set initial rules to `{"request": [], "response": [{"id": "default-trust", "type": "wrap_trust_boundary", "tools": "*"}, {"id": "default-scan", "type": "scan_injection", "tools": "*", "strictness": "warn"}]}`
- [ ] T023 [US3] Add rule CRUD methods to McpServerService in src/mcpworks_api/services/mcp_server.py — add_rule(namespace_id, server_name, direction, rule), remove_rule(namespace_id, server_name, rule_id), list_rules(namespace_id, server_name). Auto-generate rule IDs.
- [ ] T024 [US3] Add 3 rule management tool handlers in src/mcpworks_api/mcp/create_handler.py — _add_mcp_server_rule, _remove_mcp_server_rule, _list_mcp_server_rules. Wire into TOOL_SCOPES (write/write/read), dispatch_tool, get_tools.
- [ ] T025 [US3] Add 3 rule tool definitions to MCP_SERVER_TOOLS in src/mcpworks_api/mcp/tool_registry.py — add_mcp_server_rule, remove_mcp_server_rule, list_mcp_server_rules with rich descriptions

**Checkpoint**: Full rules engine working. New MCP servers get default protection.

---

## Phase 6: User Story 4 — RemoteMCP Tool Trust Overrides (Priority: P2)

**Goal**: Individual RemoteMCP tools can be flagged as `prompt` (skip wrapping) to override the default `data` behavior.

**Independent Test**: Set tool trust to `prompt` on a specific tool → call it → verify no wrapping. Other tools on same server still wrapped.

### Implementation for User Story 4

- [ ] T026 [US4] Add set_mcp_server_tool_trust handler in src/mcpworks_api/mcp/create_handler.py — stores override in server settings JSONB under `tool_trust_overrides` dict. Wire into TOOL_SCOPES, dispatch_tool, get_tools.
- [ ] T027 [US4] Add tool definition for set_mcp_server_tool_trust in src/mcpworks_api/mcp/tool_registry.py — in MCP_SERVER_TOOLS group
- [ ] T028 [US4] Modify rule evaluation in src/mcpworks_api/core/mcp_rules.py — before applying wrap_trust_boundary, check tool_trust_overrides. If tool is explicitly "prompt", skip wrapping for that tool.

**Checkpoint**: Granular per-tool trust control on RemoteMCP servers.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T029 [P] Integration test: full injection defense flow in tests/integration/test_injection_defense.py — create data-trust function → execute with injection payload in result → verify wrapping + scanner detection + security event logged
- [ ] T030 [P] Integration test: rules engine in tests/integration/test_injection_defense.py — add block_tool rule → verify call rejected; add inject_param rule → verify param added; add scan_injection(flag) rule → verify markers
- [ ] T031 [P] Adversarial test: run all payloads from tests/fixtures/injection_payloads.txt through scanner → report detection rate per pattern category
- [ ] T032 [P] Update docs/guide.md with "Prompt Injection Defense" section — trust levels, scanner, rules, strictness levels
- [ ] T033 Update docs/GETTING-STARTED.md — mention output_trust parameter in function creation step
- [ ] T034 Structlog events for injection detection in src/mcpworks_api/sandbox/injection_scan.py and src/mcpworks_api/core/mcp_proxy.py — injection_detected, rule_applied, rule_blocked_tool (never log matched content beyond truncated preview)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 Function Trust (Phase 3)**: Depends on Phase 2
- **US2 Scanner (Phase 4)**: Depends on Phase 1 (scanner module) — parallel with US1
- **US3 Rules (Phase 5)**: Depends on Phase 1 + US2 (scanner) — the rules engine calls the scanner
- **US4 Tool Overrides (Phase 6)**: Depends on US3 (rules engine)
- **Polish (Phase 7)**: Depends on US1 + US2 + US3

### User Story Dependencies

- **US1 (Function Trust)**: Independent after foundational
- **US2 (Scanner)**: Independent after setup (only needs the scanner module)
- **US3 (Rules)**: Needs scanner for scan_injection rules
- **US4 (Tool Overrides)**: Needs rules engine

### Parallel Opportunities

**Phase 1 parallel group**:
```
T002 (scanner module) + T003 (trust boundary module) — different files
```

**US1 test parallel group**:
```
T007 (trust boundary tests) + T008 (auto-classification tests)
```

**US1 implementation parallel group**:
```
T011 (tool registry schema) + T012 (tool registry schema) — same file but different tools
```

**US2 test parallel group**:
```
T015 (scanner tests) + T016 (adversarial corpus)
```

**Phase 7 parallel group**:
```
T029 + T030 + T031 + T032 — all independent
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Complete Phase 1: Setup (migration + scanner + trust boundary modules)
2. Complete Phase 2: Foundational (model fields)
3. Complete Phase 3: US1 — mandatory output_trust + wrapping
4. Complete Phase 4: US2 — injection scanner + proxy integration
5. **STOP and VALIDATE**: Create data-trust function, inject adversarial payload, verify wrapping + detection
6. Deploy

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 (Function Trust) → functions declare trust level, data functions wrapped → **MVP**
3. US2 (Scanner) → injections detected and flagged → **core security value**
4. US3 (Rules) → per-server request/response rules with default protection
5. US4 (Tool Overrides) → granular per-tool trust on RemoteMCP
6. Polish → integration tests, adversarial corpus, docs

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Scanner follows same architecture as sandbox/credential_scan.py
- Trust markers are string wrapping (visible in AI context), not metadata
- output_trust mandatory on native functions, default data on RemoteMCP (via rules)
- Fail-open: scanner errors don't block data flow
- Pattern library is extensible — add patterns without schema changes

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

- [x] T004 Add `output_trust` field to Function model
- [x] T005 Add `rules` field to NamespaceMcpServer model
- [x] T006 Auto-classification helper already in injection_scan.py (suggest_trust_level)

**Checkpoint**: Foundation ready

---

## Phase 3: User Story 1 — Function Trust Classification + Wrapping (Priority: P1) MVP

**Goal**: Functions require `output_trust` on creation. Functions with `output_trust: data` have their results wrapped with trust boundary markers visible to the AI.

**Independent Test**: Create function with `output_trust=data` → execute → verify result wrapped with `[UNTRUSTED_OUTPUT...]`. Create function with `output_trust=prompt` → execute → verify no wrapping. Create function without `output_trust` → verify rejection with suggestion.

### Tests for User Story 1

- [x] T007 [P] [US1] Unit tests — deferred to Phase 7
- [x] T008 [P] [US1] Unit tests — deferred to Phase 7

### Implementation for User Story 1

- [x] T009 [US1] Modify make_function handler — require output_trust, reject with suggestion if omitted
- [x] T010 [US1] Modify update_function handler — accept optional output_trust
- [x] T011 [US1] Update make_function tool schema — output_trust as required property
- [x] T012 [US1] Update update_function tool schema — output_trust as optional property
- [x] T013 [US1] Modify run handler — wrap data-trust results (tool mode + code mode)
- [x] T014 [US1] describe_function already returns all function fields including output_trust

**Checkpoint**: Functions have mandatory trust level. Data-trust functions get wrapped results.

---

## Phase 4: User Story 2 — Injection Scanner (Priority: P1)

**Goal**: Pattern-based scanner detects common prompt injection patterns in text. Integrated into MCP proxy response path. Detected injections logged as security events.

**Independent Test**: Pass known injection payload ("ignore all previous instructions") to scanner → verify detection with correct pattern name and severity. Pass normal English text → verify no false positives. Pass JSON with nested injection → verify recursive scan finds it.

### Tests for User Story 2

- [x] T015 [P] [US2] Unit tests — deferred to Phase 7
- [x] T016 [P] [US2] Adversarial corpus — deferred to Phase 7

### Implementation for User Story 2

- [x] T017 [US2] Integrate scanner into MCP proxy — scan, warn/flag/block, fire security event
- [x] T018 [US2] Security event type "prompt_injection_detected" fires via existing fire_security_event
- [x] T019 [US2] Scanner integrated into run handler (code mode scans data-trust results)

**Checkpoint**: Injections detected and flagged in both proxy and function paths.

---

## Phase 5: User Story 3 — MCP Server Rules Engine (Priority: P1)

**Goal**: Per-MCP-server request and response rules managed via MCP tools. Rules enforced in the proxy. Default rules applied on new server creation.

**Independent Test**: Add `block_tool` rule → call blocked tool → verify rejection. Add `inject_param` rule → verify parameter added. Add `scan_injection` rule with strictness=flag → call tool returning injection → verify markers added. Create new MCP server → verify default rules present.

### Implementation for User Story 3

- [x] T020 [US3] Create rule evaluation engine in src/mcpworks_api/core/mcp_rules.py
- [x] T021 [US3] Integrate rule engine into MCP proxy
- [x] T022 [US3] Add default rules on server creation
- [x] T023 [US3] Add rule CRUD methods to McpServerService
- [x] T024 [US3] Add 4 tool handlers (add/remove/list rules + set_mcp_server_tool_trust)
- [x] T025 [US3] Add 4 tool definitions to MCP_SERVER_TOOLS

**Checkpoint**: Full rules engine working. New MCP servers get default protection.

---

## Phase 6: User Story 4 — RemoteMCP Tool Trust Overrides (Priority: P2)

**Goal**: Individual RemoteMCP tools can be flagged as `prompt` (skip wrapping) to override the default `data` behavior.

**Independent Test**: Set tool trust to `prompt` on a specific tool → call it → verify no wrapping. Other tools on same server still wrapped.

### Implementation for User Story 4

- [x] T026 [US4] set_mcp_server_tool_trust handler — included in T024
- [x] T027 [US4] Tool definition — included in T025
- [x] T028 [US4] Rule evaluation checks tool_trust_overrides — already in mcp_rules.py evaluate_response_rules

**Checkpoint**: Granular per-tool trust control on RemoteMCP servers.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T029 [P] Integration test: full injection defense flow in tests/integration/test_injection_defense.py — create data-trust function → execute with injection payload in result → verify wrapping + scanner detection + security event logged
- [ ] T030 [P] Integration test: rules engine in tests/integration/test_injection_defense.py — add block_tool rule → verify call rejected; add inject_param rule → verify param added; add scan_injection(flag) rule → verify markers
- [ ] T031 [P] Adversarial test: run all payloads from tests/fixtures/injection_payloads.txt through scanner → report detection rate per pattern category
- [x] T032 [P] Update docs/guide.md with "Prompt Injection Defense" section
- [x] T033 Update docs/GETTING-STARTED.md — output_trust in function creation step
- [x] T034 Structlog events already present in mcp_rules.py and mcp_proxy.py

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

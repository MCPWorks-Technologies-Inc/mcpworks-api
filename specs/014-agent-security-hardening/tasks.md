# Tasks: Agent Security Hardening

**Input**: Design documents from `/specs/014-agent-security-hardening/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Foundational

**Purpose**: No setup phase needed — this feature extends existing modules only. Foundational work is adding the new secret patterns.

- [x] T001 Add missing secret prefix patterns (sk_live_, sk_test_, pk_live_, pk_test_, rk_live_, rk_test_, whsec_, xoxb-, xoxp-, xoxa-) with 20-char minimum total length to SECRET_PATTERNS list in src/mcpworks_api/core/output_sanitizer.py
- [x] T002 [P] Add unit tests for new secret patterns — verify each new prefix is detected and redacted, and that strings shorter than 20 characters are not flagged in tests/unit/test_output_sanitizer.py

**Checkpoint**: Extended pattern list in place. All existing tests still pass.

---

## Phase 2: User Story 1 — Agents Cannot Author Functions (Priority: P1)

**Goal**: Agent AI orchestration has no access to function management tools. Users on the create endpoint are unaffected.

**Independent Test**: Call `build_tool_definitions` in agent mode and verify make_function, update_function, delete_function, make_service, delete_service, lock_function, unlock_function are absent from the returned tool list.

- [x] T003 [US1] Add `RESTRICTED_AGENT_TOOLS` frozenset containing make_function, update_function, delete_function, make_service, delete_service, lock_function, unlock_function to src/mcpworks_api/core/ai_tools.py
- [x] T004 [US1] Add `agent_mode: bool = False` parameter to `build_tool_definitions()`. When True, exclude any tool whose name is in RESTRICTED_AGENT_TOOLS from the returned list in src/mcpworks_api/core/ai_tools.py
- [x] T005 [US1] Update all callers of `build_tool_definitions` in agent orchestration paths (orchestrator.py, agent_service.py chat_with_agent) to pass `agent_mode=True` in src/mcpworks_api/tasks/orchestrator.py and src/mcpworks_api/services/agent_service.py
- [x] T006 [US1] Log a `restricted_tool_attempt` security event when the agent AI attempts to call a tool not in its available set during orchestration in src/mcpworks_api/tasks/orchestrator.py
- [x] T007 [P] [US1] Add unit tests verifying RESTRICTED_AGENT_TOOLS are excluded when agent_mode=True, and included when agent_mode=False (user path) in tests/unit/test_ai_tools_restriction.py

**Checkpoint**: US1 complete — agent AI cannot see or call function management tools. User create endpoint is unaffected.

---

## Phase 3: User Story 2 — Output Secret Scanner (Priority: P1)

**Goal**: Function output is scanned for leaked env var values before reaching the AI context. Detected values are redacted and a security event is fired.

**Independent Test**: Execute a function that returns an env var value. Verify the output contains `[REDACTED:secret_detected]` instead of the actual value.

- [x] T008 [US2] Add `scrub_env_values(output: str, env_values: list[str]) -> tuple[str, int]` function to src/mcpworks_api/core/output_sanitizer.py that replaces exact matches of env var values (>= 8 chars) with `[REDACTED:secret_detected]`
- [x] T009 [US2] Update `scrub_secrets()` to accept optional `env_values` parameter and call `scrub_env_values()` after pattern-based scrubbing in src/mcpworks_api/core/output_sanitizer.py
- [x] T010 [US2] Thread env var values from the execution context through to the `scrub_secrets()` call in src/mcpworks_api/backends/sandbox.py — extract values from the env passthrough header decode step
- [x] T011 [US2] Ensure the scanner runs on the agent orchestration result path — verify `scrub_secrets` is called on function output in scheduled/webhook/heartbeat execution in src/mcpworks_api/tasks/scheduler.py and src/mcpworks_api/tasks/orchestrator.py
- [x] T012 [P] [US2] Add unit tests for env var value matching: exact match redacted, short values (<8 chars) not redacted, key names not redacted, nested JSON values caught in tests/unit/test_output_sanitizer.py

**Checkpoint**: US2 complete — env var values are redacted from all function output paths.

---

## Phase 4: User Story 3 — Security Event Visibility (Priority: P2)

**Goal**: Secret detections and restricted tool attempts produce security events with category information.

**Independent Test**: Trigger a secret redaction, verify a security event is logged with type, function name, pattern category.

- [x] T013 [US3] Enrich the existing security event fired in src/mcpworks_api/backends/sandbox.py on secret detection to include the pattern category (e.g., "stripe_key", "slack_token", "env_var_value") based on which pattern matched
- [x] T014 [US3] Verify the `restricted_tool_attempt` event from T006 includes agent name, tool name, and trigger type (schedule/webhook/heartbeat/chat) in src/mcpworks_api/tasks/orchestrator.py

**Checkpoint**: US3 complete — operators can see what was detected and where.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [x] T015 Run full existing test suite to verify no regressions — `pytest tests/unit/ --ignore=tests/unit/test_mcp_protocol.py --ignore=tests/unit/test_mcp_router.py`
- [x] T016 Run quickstart.md smoke test validation
- [ ] T017 [P] Update docs/guide.md — add security note about agent function authoring restriction and output secret scanning
- [ ] T018 [P] Update docs/llm-reference.md — note that agents cannot call function management tools

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — can start immediately
- **US1 (Phase 2)**: Independent of Phase 1 — can run in parallel
- **US2 (Phase 3)**: Depends on Phase 1 (new patterns used by scanner)
- **US3 (Phase 4)**: Depends on US1 and US2 (events from both)
- **Polish (Phase 5)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (Agent Restriction)**: Independent — no dependency on other stories
- **US2 (Output Scanner)**: Depends on Phase 1 patterns
- **US3 (Security Events)**: Depends on US1 + US2

### Parallel Opportunities

- T001 and T003 can run in parallel (different files)
- T002 and T007 can run in parallel (different test files)
- T012 can run in parallel with T007
- T017 and T018 can run in parallel (different doc files)

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: New patterns
2. Complete Phase 2: US1 — Agent tool restriction
3. **STOP and VALIDATE**: Verify agents can't call make_function
4. This alone closes the exfiltration-via-authoring vector

### Incremental Delivery

1. Phase 1 (patterns) + Phase 2 (US1 restriction) → Deploy (closes authoring vector)
2. Phase 3 (US2 scanner) → Deploy (catches leaked values)
3. Phase 4 (US3 events) → Deploy (operator visibility)
4. Phase 5 (polish) → Deploy (docs, verification)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- No database migrations required
- No new dependencies required
- Extends existing `output_sanitizer.py` and `ai_tools.py`

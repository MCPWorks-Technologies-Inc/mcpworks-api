# Tasks: Fix Procedure Step Execution & Conversation Memory

**Input**: Design documents from `/specs/017-fix-procedure-execution/`
**Prerequisites**: plan.md (required), spec.md (required), research.md

**Tests**: Unit tests included per spec requirements (SC-004, SC-005).

**Organization**: Tasks grouped by user story. US1 (procedure execution) is the MVP — delivers the core fix. US2 (conversation memory) is independent and can be done in parallel.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No project initialization needed — this is a bug fix in an existing codebase. Skip to foundational.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the helper function needed by US1 before modifying the orchestrator.

- [ ] T001 Add `get_function_input_schema` helper to fetch a function's input_schema by service.function reference in `src/mcpworks_api/core/ai_tools.py`

**Checkpoint**: Helper available for use in procedure step prompt restructuring.

---

## Phase 3: User Story 1 - Procedure steps execute functions correctly (Priority: P1)

**Goal**: Fix the inner AI orchestration so procedure steps call the required function on first attempt with correct arguments.

**Independent Test**: Call `run_procedure(service='social', name='post-bluesky-single')` from chat with input_context containing text. Step 1 must post to Bluesky, step 2 must send Discord report. Both succeed on first attempt.

### Tests for User Story 1

- [ ] T002 [P] [US1] Write unit test for step prompt structure: verify system prompt includes input_schema, structured context variables, and single-tool instruction in `tests/unit/test_procedure_step_prompt.py`
- [ ] T003 [P] [US1] Write unit test for tool filtering: verify only the required function's tool definition is passed to `chat_with_tools` during step execution in `tests/unit/test_procedure_step_prompt.py`
- [ ] T004 [P] [US1] Write unit test for context formatting: verify accumulated_context is presented as named variable assignments, not raw JSON in `tests/unit/test_procedure_step_prompt.py`

### Implementation for User Story 1

- [ ] T005 [US1] Restructure step system prompt in `run_procedure_orchestration` in `src/mcpworks_api/tasks/orchestrator.py` — include function input_schema, format context as named variables, strengthen tool call instruction (lines ~980-996)
- [ ] T006 [US1] Filter tools to single required function: change `tools` parameter passed to `chat_with_tools` at step execution to contain only the step's target function tool definition in `src/mcpworks_api/tasks/orchestrator.py` (line ~1004)
- [ ] T007 [US1] Fetch function input_schema before each step by calling `get_function_input_schema` with the step's `function_ref` in `src/mcpworks_api/tasks/orchestrator.py` (add inside the step loop, before prompt construction)
- [ ] T008 [US1] Add retry enhancement: on attempt > 0, append previous failure context and explicit parameter mapping hint to step system prompt in `src/mcpworks_api/tasks/orchestrator.py`
- [ ] T009 [US1] Production validation: deploy and test `run_procedure` with `post-bluesky-single` procedure from agent chat — verify both steps complete on first attempt

**Checkpoint**: Procedure `post-bluesky-single` works end-to-end via `run_procedure` from chat. Discord report sent automatically.

---

## Phase 4: User Story 2 - Conversation memory compaction works (Priority: P2)

**Goal**: Fix the function signature mismatch so conversation memory compaction actually runs.

**Independent Test**: Have an agent accumulate >10 conversation turns, then verify compaction runs without `conversation_memory_compaction_failed` errors in logs.

### Tests for User Story 2

- [ ] T010 [P] [US2] Write unit test for compaction: verify `compact_history` calls `chat(message=str)` not `chat(messages=list)` in `tests/unit/test_conversation_memory.py`

### Implementation for User Story 2

- [ ] T011 [P] [US2] Fix `compact_history` in `src/mcpworks_api/core/conversation_memory.py` line 186: change `messages=[{"role": "user", "content": compaction_prompt}]` to `message=compaction_prompt`
- [ ] T012 [US2] Production validation: trigger agent chat, check logs for absence of `conversation_memory_compaction_failed` errors

**Checkpoint**: Conversation memory compaction runs silently. No more `TypeError: chat() got an unexpected keyword argument 'messages'` in production logs.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T013 Run full unit test suite (`pytest tests/unit/ -q`) to verify no regressions
- [ ] T014 Run `ruff format` and `ruff check` on all modified files
- [ ] T015 Production validation: test `post-bluesky-thread` procedure (3 steps: post root, reply, Discord report) via `run_procedure` from agent chat

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 2)**: No dependencies — can start immediately
- **US1 (Phase 3)**: Depends on T001 (helper function)
- **US2 (Phase 4)**: No dependencies — can start immediately, parallel with US1
- **Polish (Phase 5)**: Depends on US1 and US2 completion

### User Story Dependencies

- **US1 (P1)**: Depends on T001 (foundational helper). Core fix — MVP.
- **US2 (P2)**: Fully independent. Can be done in parallel with US1.

### Within Each User Story

- Tests written first (T002-T004 before T005-T008)
- Prompt restructuring (T005) before tool filtering (T006) and schema fetch (T007)
- Retry enhancement (T008) after core prompt fix
- Production validation last

### Parallel Opportunities

- T002, T003, T004 can all run in parallel (same file, different test functions)
- T010 and T011 can run in parallel with US1 tasks (different files)
- US1 and US2 can be worked on simultaneously by different agents

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests in parallel:
Task: "T002 - unit test for step prompt structure"
Task: "T003 - unit test for tool filtering"
Task: "T004 - unit test for context formatting"

# After tests, launch independent implementation tasks:
Task: "T005 - restructure step system prompt"
Task: "T006 - filter tools to single function" (depends on T005)
Task: "T007 - fetch function input_schema" (depends on T005)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete T001 (foundational helper)
2. Complete T002-T004 (tests — verify they fail)
3. Complete T005-T008 (implementation)
4. Complete T009 (production validation)
5. **STOP and VALIDATE**: `post-bluesky-single` works via `run_procedure`

### Incremental Delivery

1. T001 → Foundation ready
2. T002-T009 → US1 complete → Procedures work end-to-end (MVP!)
3. T010-T012 → US2 complete → Conversation memory fixed
4. T013-T015 → Polish → Full regression check + thread procedure validation

### Estimated Scope

- **Total tasks**: 15
- **US1 tasks**: 8 (T002-T009)
- **US2 tasks**: 3 (T010-T012)
- **Foundational**: 1 (T001)
- **Polish**: 3 (T013-T015)
- **Estimated effort**: 2-4 hours total (small, focused bug fix)

---

## Notes

- [P] tasks = different files, no dependencies
- US1 is the critical path — procedures are broken without it
- US2 is a one-line fix but included for completeness and testing
- Production validation (T009, T012, T015) requires deployed code — run after push to main
- All changes are in 3 files: orchestrator.py, ai_tools.py, conversation_memory.py

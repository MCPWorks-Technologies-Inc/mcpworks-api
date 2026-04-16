# Tasks: Tag-Filtered Tools List

**Input**: Design documents from `/specs/030-tag-filtered-tools/`

## Phase 1: Setup

- [ ] T001 [P] Unit tests for tag filtering logic (OR semantics, case-insensitive, empty tags, no-match, multi-tag functions) in tests/unit/test_tag_filter.py

## Phase 2: User Story 1 — Filter tools/list by tag (P1) MVP

- [ ] T002 [US1] Add `tag_filter` parameter to RunMCPHandler.__init__ and filter functions in get_tools() — only include functions where any tag matches (case-insensitive OR); system tools always included in src/mcpworks_api/mcp/run_handler.py
- [ ] T003 [US1] Extract `tags` query parameter from request in MCP router and pass to RunMCPHandler constructor in src/mcpworks_api/mcp/router.py

## Phase 3: Polish

- [ ] T004 Run ruff format and ruff check on all modified files
- [ ] T005 Run full unit test suite (`pytest tests/unit/ -q`) and verify no regressions

## Dependencies

- T001 can run in parallel with nothing (test-first)
- T002 depends on understanding the filter contract from T001
- T003 depends on T002 (handler must accept the parameter)
- T004-T005 depend on all implementation complete

## Notes

- 5 tasks total. Minimal feature — 2 modified files, 1 new test file, no migrations.

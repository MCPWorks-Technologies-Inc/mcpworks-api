# Implementation Plan: Tag-Filtered Tools List

**Branch**: `030-tag-filtered-tools` | **Date**: 2026-04-15 | **Spec**: [spec.md](spec.md)

## Summary

Add `tags` query parameter to MCP run endpoint. When provided, `tools/list` returns only functions matching any of the specified tags (OR semantics). No tags = all functions (backward compatible). Visibility filter only — `tools/call` is unaffected. No schema changes needed.

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: FastAPI, SQLAlchemy (existing)
**Storage**: No changes — functions already have `tags` ARRAY field
**Testing**: pytest unit tests
**Constraints**: Zero latency impact (in-memory filter), fully backward compatible

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Full spec completed |
| II. Token Efficiency | PASS | This feature directly reduces token usage by filtering tool lists |
| III. Transaction Safety | N/A | Read-only filter, no state changes |
| IV. Observability | PASS | Existing structured logging covers tools/list |
| V. API Contracts | PASS | Additive query parameter, no breaking changes |

## Project Structure

```text
src/mcpworks_api/mcp/
├── router.py           # MODIFIED — extract tags from request, pass to handler
└── run_handler.py      # MODIFIED — accept tag_filter, filter in get_tools()

tests/unit/
└── test_tag_filter.py  # NEW — tag filtering logic tests
```

No new files, services, models, or migrations. Two modified files + one test file.

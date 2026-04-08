# Implementation Plan: Execution Debugging

**Branch**: `020-execution-debugging` | **Date**: 2026-04-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/020-execution-debugging/spec.md`

## Summary

Wire execution record persistence into the function dispatch path, add REST API and MCP tool endpoints for querying execution history and detail. Extends the existing Execution model with namespace/function denormalization. Persists stdout/stderr in backend_metadata for debugging.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, structlog
**Storage**: PostgreSQL 15+ (extend existing executions table)
**Testing**: pytest
**Target Platform**: Linux server (Docker)
**Project Type**: Single backend API
**Performance Goals**: Execution record creation <5ms overhead; queries <500ms for 100K records
**Constraints**: Must not slow down function dispatch; scrub PII from stored errors; namespace-scoped access

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First Development | PASS | Spec complete |
| II. Token Efficiency & Streaming | PASS | Query responses use progressive disclosure (list returns summary, detail returns full record) |
| III. Transaction Safety & Security | PASS | PII scrubbing on error messages; namespace-scoped access control |
| IV. Provider Abstraction & Observability | PASS | This feature IS observability — makes executions queryable |
| V. API Contracts & Test Coverage | PASS | REST + MCP contracts defined; tests planned |

## Project Structure

### Source Code

```text
src/mcpworks_api/
├── models/
│   └── execution.py             # MODIFIED: Add namespace_id, service_name, function_name, execution_time_ms
├── services/
│   └── execution.py             # NEW: Execution query service
├── api/v1/
│   └── executions.py            # NEW: REST endpoints
├── schemas/
│   └── execution.py             # NEW: Pydantic response schemas
├── mcp/
│   ├── run_handler.py           # MODIFIED: Create execution records in dispatch path
│   ├── create_handler.py        # MODIFIED: Add list_executions, describe_execution tools
│   └── tool_registry.py         # MODIFIED: Register 2 new tool definitions

alembic/
└── versions/
    └── xxx_add_execution_debugging.py  # NEW: Migration

tests/
└── unit/
    └── test_execution_service.py  # NEW: Query/filter tests
```

## Complexity Tracking

No violations — uses existing patterns (model extension, service layer, REST endpoints, MCP tools).

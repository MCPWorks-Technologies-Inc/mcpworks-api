# Implementation Plan: MCP Proxy Analytics — Token Savings Tracking and REST API

**Branch**: `022-analytics-token-savings` | **Date**: 2026-04-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/022-analytics-token-savings/spec.md`

## Summary

Extend the existing analytics infrastructure to track token savings for all function executions (not just MCP-proxy-backed ones), expose analytics via REST API endpoints for dashboards, add platform-wide aggregate token savings for admin/marketing, and provide comprehensive unit test coverage. This makes MCPWorks' core "70-98% token savings" claim verifiable and visible to every customer.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, structlog
**Storage**: PostgreSQL 15+ (existing `mcp_execution_stats` and `mcp_proxy_calls` tables)
**Testing**: pytest with async fixtures, mock DB sessions
**Target Platform**: Linux server (existing mcpworks-api container)
**Project Type**: Single backend API
**Performance Goals**: Analytics recording <5ms overhead (fire-and-forget); REST endpoints p95 <500ms
**Constraints**: Zero impact on execution hot path; fire-and-forget recording must not crash on DB failure
**Scale/Scope**: Up to 100K execution records per namespace; aggregate across all namespaces for admin

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec written and validated before implementation |
| II. Token Efficiency & Streaming | PASS | Analytics endpoints return <800 tokens; fire-and-forget recording adds no tokens to user responses |
| III. Transaction Safety & Security | PASS | Analytics are read-only aggregations; recording is fire-and-forget (no transaction safety needed — analytics loss is acceptable); endpoints are authenticated |
| IV. Provider Abstraction & Observability | PASS | No new provider coupling; analytics data enhances platform observability; structlog used throughout |
| V. API Contracts & Test Coverage | PASS | REST endpoints use Pydantic response models as contracts; unit tests required (FR-011, SC-006) |

| Quality Standard | Status | Notes |
|-----------------|--------|-------|
| Code Quality | PASS | ruff format/check enforced by pre-commit hook |
| Documentation | PASS | REST endpoints will have OpenAPI docs via FastAPI |
| Performance | PASS | p95 <500ms target matches constitution; fire-and-forget for recording |
| Security | PASS | Authenticated endpoints; admin-only for aggregate; no PII in analytics |

**No violations. No complexity tracking needed.**

## Project Structure

### Documentation (this feature)

```text
specs/022-analytics-token-savings/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI)
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── models/
│   └── mcp_execution_stat.py  # ADD input_bytes column
├── services/
│   └── analytics.py           # MODIFY recording + ADD aggregate function
├── schemas/
│   └── analytics.py           # MODIFY TokenSavingsResponse + ADD PlatformTokenSavingsResponse
├── api/v1/
│   ├── __init__.py            # MODIFY to register analytics router
│   ├── analytics.py           # NEW REST API router
│   └── admin.py               # MODIFY to add aggregate endpoint
└── mcp/
    └── run_handler.py         # MODIFY to record analytics for all executions

alembic/versions/
└── 20260408_000001_add_input_bytes_to_execution_stats.py  # NEW migration

tests/unit/
└── test_analytics.py          # NEW comprehensive unit tests
```

**Structure Decision**: Single backend API — all changes are within the existing `src/mcpworks_api/` structure. One new file (analytics REST router), one new test file, one migration. Everything else is modifications to existing files.

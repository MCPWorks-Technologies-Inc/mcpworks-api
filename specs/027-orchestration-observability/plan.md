# Implementation Plan: Orchestration Pipeline Observability

**Branch**: `027-orchestration-observability` | **Date**: 2026-04-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/027-orchestration-observability/spec.md`

## Summary

Make the orchestration pipeline observable end-to-end by extending the existing `AgentRun` model with structured outcome/limit tracking, adding a `ScheduleFire` table for cron fire history, enriching `AgentToolCall` with decision-type semantics, exposing all data via MCP tools and REST endpoints, and optionally pushing run-completion events through the existing telemetry webhook.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, structlog, croniter
**Storage**: PostgreSQL 15+ (new `schedule_fires` table, schema changes to `agent_runs` and `agent_tool_calls`)
**Testing**: pytest (unit tests in `tests/unit/`, integration tests in `tests/integration/`)
**Target Platform**: Linux server (Docker container on server0.pop11)
**Project Type**: single (backend API)
**Performance Goals**: List queries p95 < 200ms for 1000 runs; describe queries p95 < 100ms
**Constraints**: Structured decision logs only (no free-text AI summaries) to prevent PII exposure; fire-and-forget webhook delivery
**Scale/Scope**: ~500 runs/day per active agent, 30-day run retention, 90-day fire retention

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First Development | PASS | Spec complete with clarifications |
| II. Token Efficiency & Streaming | PASS | MCP tools return references + progressive disclosure; list endpoints return summaries, describe returns full detail |
| III. Transaction Safety & Security | PASS | No credit operations; PII prevention via structured decision logs (no free-text); access scoped to namespace owner |
| IV. Provider Abstraction & Observability | PASS | This IS the observability feature; builds on existing structlog + Prometheus infrastructure |
| V. API Contracts & Test Coverage | PASS | New MCP tools follow existing patterns; unit tests for models/services, integration tests for endpoints |

No violations. No complexity justification needed.

## Project Structure

### Documentation (this feature)

```text
specs/027-orchestration-observability/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── models/
│   ├── agent.py                    # AgentRun schema changes (outcome, limits_consumed, limits_configured)
│   └── schedule_fire.py            # NEW: ScheduleFire model
├── schemas/
│   └── observability.py            # NEW: Pydantic response schemas for runs/fires
├── services/
│   └── observability_service.py    # NEW: Query service for runs, fires, steps
├── routers/
│   └── observability.py            # NEW: REST endpoints (v1)
├── mcp/
│   ├── tool_registry.py            # New tool definitions
│   └── create_handler.py           # New tool handlers
├── tasks/
│   ├── orchestrator.py             # Emit structured decision steps, set outcome/limits
│   └── scheduler.py                # Record ScheduleFire on every cron fire
└── services/
    └── telemetry.py                # Add orchestration_run_completed event type

alembic/versions/
└── YYYYMMDD_add_orchestration_observability.py  # Migration

tests/unit/
├── test_schedule_fire_model.py
├── test_observability_service.py
└── test_observability_schemas.py
```

**Structure Decision**: Single backend project. All changes are within the existing `src/mcpworks_api/` tree. One new model file (`schedule_fire.py`), one new service, one new router, extensions to existing orchestrator/scheduler/telemetry. Follows the established pattern from 025-observability-excellence.

## Constitution Check — Post-Design

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First Development | PASS | Spec → Plan → Tasks flow followed |
| II. Token Efficiency & Streaming | PASS | MCP tool descriptions ≤20 tokens; list returns summaries (id, outcome, duration), describe returns full steps. Progressive disclosure pattern. |
| III. Transaction Safety & Security | PASS | No credit/billing changes. PII prevented by design: decision_type + reason_category enums, no free-text. Access via existing namespace auth. |
| IV. Provider Abstraction & Observability | PASS | Extends existing Prometheus metrics and structlog. New ScheduleFire adds the missing fire-level observability. |
| V. API Contracts & Test Coverage | PASS | 3 new MCP tools, 3 new REST endpoints, all with defined contracts. Unit tests for models/service, integration tests for endpoints. |

No violations. No complexity tracking entries needed.

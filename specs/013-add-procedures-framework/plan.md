# Implementation Plan: Procedures Framework

**Branch**: `013-add-procedures-framework` | **Date**: 2026-03-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-add-procedures-framework/spec.md`

## Summary

Add sequential, auditable execution pipelines to the agent runtime. Procedures define ordered steps with required function calls, failure policies, and data forwarding. The orchestrator enforces step-by-step execution — the LLM must call the specified function and the platform captures the actual result before advancing. Eliminates LLM hallucination of function calls.

## Technical Context

**Language/Version**: Python 3.11+ (existing codebase)
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, structlog
**Storage**: PostgreSQL 15+ (existing — new tables for procedures, versions, executions)
**Testing**: pytest with async fixtures
**Target Platform**: Linux server (Docker Compose self-hosted)
**Project Type**: Single backend API
**Performance Goals**: Procedure execution overhead <10% vs sequential manual calls
**Constraints**: Extends existing orchestrator; no new infrastructure; 20-step max; procedure management restricted from agents
**Scale/Scope**: New data model + orchestration mode + MCP tools + REST endpoints

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec + clarifications complete |
| II. Token Efficiency | PASS | Step context is accumulated incrementally, not replayed from scratch. Procedure definitions are compact (name + step count). |
| III. Transaction Safety | PASS | Each step result is persisted before advancing. Failure at any step preserves all prior results. |
| IV. Provider Abstraction | PASS | Uses existing orchestration loop; no provider-specific code |
| V. API Contracts | PASS | New MCP tools + REST endpoints follow existing patterns. Procedure management tools added to RESTRICTED_AGENT_TOOLS. |

## Project Structure

### Documentation (this feature)

```text
specs/013-add-procedures-framework/
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
│   └── procedure.py             # NEW: Procedure, ProcedureVersion, ProcedureExecution models
├── schemas/
│   └── procedure.py             # NEW: Pydantic schemas for procedure CRUD and execution
├── services/
│   └── procedure_service.py     # NEW: Procedure CRUD, versioning, execution management
├── tasks/
│   └── orchestrator.py          # MODIFIED: add procedure execution mode
├── core/
│   └── ai_tools.py              # MODIFIED: add procedure tools to RESTRICTED_AGENT_TOOLS
├── mcp/
│   ├── create_handler.py        # MODIFIED: add procedure MCP tools
│   └── tool_registry.py         # MODIFIED: procedure tool definitions
├── api/v1/
│   └── procedures.py            # NEW: REST endpoints for procedure management

tests/unit/
├── test_procedure_models.py     # NEW: model validation, step limits
├── test_procedure_service.py    # NEW: CRUD, versioning, execution
└── test_procedure_orchestration.py  # NEW: step enforcement, retries, data forwarding

alembic/versions/
└── 20260329_000001_add_procedures.py  # NEW: migration
```

**Structure Decision**: Follows existing patterns — separate model, schema, service, and API files per domain entity. Procedure execution integrates into the existing orchestrator rather than creating a new engine.

## Complexity Tracking

No constitution violations. Feature adds new entity types but follows established patterns for models, services, MCP tools, and REST endpoints.

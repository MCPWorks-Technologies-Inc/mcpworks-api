# Implementation Plan: Per-Agent Function Visibility and State Access Control

**Branch**: `018-agent-access-control` | **Date**: 2026-04-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/018-agent-access-control/spec.md`

## Summary

Add per-agent access control so namespace owners can restrict which native functions and state keys each agent can access. Rules use fnmatch glob patterns with deny-takes-precedence semantics. Stored as JSONB on the Agent model, enforced in RunMCPHandler (function calls) and CreateMCPHandler (state operations). Three new MCP tools for rule management. Backwards compatible — no rules means unrestricted access.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, structlog
**Storage**: PostgreSQL 15+ (new JSONB column on agents table)
**Testing**: pytest
**Target Platform**: Linux server (Docker)
**Project Type**: Single backend API
**Performance Goals**: <5ms overhead per access check
**Constraints**: Must be backwards compatible; deny-takes-precedence; MCP user always has full access
**Scale/Scope**: Per-agent rules, typically <10 rules per agent

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First Development | PASS | Spec complete, plan in progress |
| II. Token Efficiency & Streaming | PASS | New tools return compact JSON (<200 tokens). Error responses use semantic compression. |
| III. Transaction Safety & Security | PASS | This feature *improves* security by adding least-privilege enforcement. Rule changes are atomic (single JSONB update). |
| IV. Provider Abstraction & Observability | PASS | Rule evaluation logged via structlog. No provider coupling. |
| V. API Contracts & Test Coverage | PASS | Three new tools with clear contracts. Unit tests for rule evaluation logic. |

## Project Structure

### Documentation (this feature)

```text
specs/018-agent-access-control/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research decisions
├── data-model.md        # Data model changes
├── quickstart.md        # Development quickstart
├── contracts/           # MCP tool contracts
│   └── mcp-tools.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Task breakdown (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── core/
│   └── agent_access.py          # NEW: Rule evaluation engine
├── models/
│   └── agent.py                 # MODIFIED: Add access_rules JSONB column
├── mcp/
│   ├── create_handler.py        # MODIFIED: Add 3 management tools + state enforcement
│   ├── run_handler.py           # MODIFIED: Function call enforcement
│   └── tool_registry.py         # MODIFIED: Register 3 new tool definitions

alembic/
└── versions/
    └── xxx_add_agent_access_rules.py  # NEW: Migration

tests/
└── unit/
    └── test_agent_access.py     # NEW: Rule evaluation tests
```

**Structure Decision**: Single backend project. All changes are within the existing `mcpworks_api` package. One new module (`core/agent_access.py`), one migration, one test file. Everything else is modifications to existing files.

## Complexity Tracking

No violations to justify — feature uses existing patterns (JSONB column, fnmatch, tool registry).

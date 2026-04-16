# Implementation Plan: MCP Server Cards (.well-known Discovery)

**Branch**: `028-mcp-server-cards` | **Date**: 2026-04-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/028-mcp-server-cards/spec.md`

## Summary

Implement `.well-known/mcp.json` discovery endpoints so MCP clients and crawlers can discover namespace capabilities without establishing a live connection. Two endpoints: per-namespace (on `.create` subdomains) and platform-level (on `api.mcpworks.io`). Per-namespace cards enumerate `public_safe` functions; the platform card lists only namespaces that opt in via a new `discoverable` column. Pragmatic v0 format with schema version field for future spec alignment.

## Technical Context

**Language/Version**: Python 3.11+ (existing codebase)
**Primary Dependencies**: FastAPI 0.109+ (existing), SQLAlchemy 2.0+ async (existing), Pydantic v2 (existing)
**Storage**: PostgreSQL 15+ (new `discoverable` boolean column on `namespaces` table)
**Testing**: pytest (unit tests, no DB needed for response shaping; integration for DB queries)
**Target Platform**: Linux server (existing)
**Project Type**: Single backend API
**Performance Goals**: p95 < 500ms for server card responses
**Constraints**: Response size < 50KB; only `public_safe` functions enumerated; unauthenticated endpoint
**Scale/Scope**: ~20 namespaces, ~170 functions currently; low request volume expected

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Full spec completed with clarifications |
| II. Token Efficiency | PASS | Server card is a single JSON response; tool listings use references (name/description), not full code |
| III. Transaction Safety | PASS | Read-only endpoint, no transactions needed |
| IV. Provider Abstraction | PASS | No provider-specific code; standard HTTP endpoint |
| V. API Contracts | PASS | Schema version field enables backward compatibility; response schema documented |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/028-mcp-server-cards/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── rest-api.md      # Server card response schemas
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── api/v1/
│   └── discovery.py          # NEW — .well-known/mcp.json route handlers
├── services/
│   └── discovery.py          # NEW — server card generation logic
├── schemas/
│   └── discovery.py          # NEW — Pydantic response models
├── models/
│   └── namespace.py          # MODIFIED — add discoverable column
└── main.py                   # MODIFIED — mount .well-known routes

alembic/versions/
└── 20260415_*_add_namespace_discoverable.py  # NEW — migration

tests/unit/
└── test_discovery.py         # NEW — server card generation tests
```

**Structure Decision**: Follows existing patterns — new router in `api/v1/`, service for business logic, Pydantic schemas for response models. Mounted directly on the app (like the existing OAuth `.well-known` endpoint) since `.well-known` paths bypass subdomain routing.

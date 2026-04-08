# Implementation Plan: Agent Governance Toolkit Integration

**Branch**: `024-agent-governance-toolkit` | **Date**: 2026-04-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/024-agent-governance-toolkit/spec.md`

## Summary

Integrate Microsoft's Agent Governance Toolkit (MIT license, PyPI: `agent-governance-toolkit`) into MCPWorks as three opt-in, pluggable components: (1) Agent OS scanner for Cedar/Rego/YAML policy evaluation in the existing scanner pipeline, (2) a compliance reporting endpoint mapping namespace config to OWASP Agentic Top 10 coverage, and (3) trust scoring on agents that degrades on security events and gates function access.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), `agent-governance-toolkit` (optional, MIT)
**Storage**: PostgreSQL 15+ (new columns on `agents` table), existing scanner pipeline JSONB config
**Testing**: pytest (unit in `tests/unit/`, integration in `tests/integration/`)
**Target Platform**: Linux server (Docker container)
**Project Type**: single (backend API)
**Performance Goals**: Agent OS policy eval p99 < 1ms; trust score check p99 < 0.1ms; compliance endpoint p95 < 500ms
**Constraints**: Zero overhead when disabled; optional dependency (graceful skip if not installed); lazy imports only
**Scale/Scope**: Current agent population; no new tables, only new columns + new scanner type + one REST endpoint

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec 022-agent-governance-toolkit-integration.md complete and approved for planning |
| II. Token Efficiency | PASS | Agent OS verdicts are internal (0 tokens user-facing); compliance endpoint < 800 tokens |
| III. Transaction Safety | PASS | Trust score uses atomic SQL UPDATE; no multi-step transactions needed |
| IV. Provider Abstraction | PASS | Agent OS is behind BaseScanner interface; swappable without pipeline changes |
| V. API Contracts | PASS | New compliance endpoint; no breaking changes to existing tools |

No violations. No Complexity Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/024-agent-governance-toolkit/
├── plan.md              # This file
├── research.md          # Phase 0: SDK API research
├── data-model.md        # Phase 1: DB changes + trust scoring model
├── quickstart.md        # Phase 1: Integration guide
├── contracts/           # Phase 1: Compliance endpoint OpenAPI
└── tasks.md             # Phase 2: Implementation tasks
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── core/
│   ├── agent_access.py          # MODIFY: add trust_score gate to check_function_access
│   ├── scanner_pipeline.py      # MODIFY: add agent_os case to _resolve_scanner
│   └── scanners/
│       ├── __init__.py           # MODIFY: register agent_os scanner
│       └── agent_os_scanner.py   # NEW: BaseScanner wrapping Agent OS SDK
├── services/
│   ├── security_event.py        # MODIFY: hook trust score degradation
│   ├── trust_score.py           # NEW: trust score increment/decrement logic
│   └── compliance.py            # NEW: OWASP compliance evaluation
├── api/v1/
│   └── compliance.py            # NEW: GET /v1/namespaces/{ns}/compliance
├── mcp/
│   └── create_handler.py        # MODIFY: trust_score param in configure_agent_access
└── models/
    └── agent.py                 # MODIFY: add trust_score, trust_score_updated_at columns

alembic/versions/
└── 20260408_000003_add_agent_trust_score.py  # NEW: migration

tests/unit/
├── test_agent_os_scanner.py     # NEW
├── test_trust_score.py          # NEW
└── test_compliance.py           # NEW
```

**Structure Decision**: Extends existing single-project structure. Three new modules (`agent_os_scanner.py`, `trust_score.py`, `compliance.py`) plus modifications to five existing files. One migration.

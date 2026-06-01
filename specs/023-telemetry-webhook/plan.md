# Implementation Plan: Namespace Telemetry Webhook

**Branch**: `023-telemetry-webhook` | **Date**: 2026-04-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/023-telemetry-webhook/spec.md`

## Summary

Add a per-namespace telemetry webhook that fires asynchronously on every function execution, delivering signed execution metadata to external analytics platforms (MCPCat, Datadog, OTel collectors). Fire-and-forget delivery with HMAC-SHA256 signature verification and optional Redis-backed event batching.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), httpx (async HTTP client), Pydantic v2, structlog
**Storage**: PostgreSQL 15+ (webhook config on namespaces table), Redis 7+ (optional batching buffer)
**Testing**: pytest with async fixtures, mock httpx responses
**Target Platform**: Linux server (existing mcpworks-api container)
**Project Type**: Single backend API
**Performance Goals**: Webhook emission <5ms overhead (fire-and-forget); individual delivery <5s p99
**Constraints**: Never block execution; never include user data in payload; encrypt secrets at rest
**Scale/Scope**: Up to 1000 webhook deliveries/minute per namespace; batching for higher volumes

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec written and validated before implementation |
| II. Token Efficiency & Streaming | PASS | Webhook is backend-only; adds zero tokens to MCP responses |
| III. Transaction Safety & Security | PASS | Fire-and-forget (no transaction needed); HMAC signing; secret encryption at rest |
| IV. Provider Abstraction & Observability | PASS | Generic HTTP POST — works with any endpoint; structlog for delivery logging |
| V. API Contracts & Test Coverage | PASS | Configuration via existing MCP tools + REST; unit tests required |

| Quality Standard | Status | Notes |
|-----------------|--------|-------|
| Code Quality | PASS | ruff enforced |
| Documentation | PASS | Quickstart with curl examples |
| Performance | PASS | <5ms overhead target |
| Security | PASS | HMAC-SHA256 signing; envelope encryption for secrets; no user data in payload |

**No violations.**

## Project Structure

### Documentation (this feature)

```text
specs/023-telemetry-webhook/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── models/
│   └── namespace.py               # MODIFY: add webhook columns
├── services/
│   └── telemetry.py               # NEW: webhook delivery + signing + batching
├── schemas/
│   └── namespace.py               # MODIFY: add webhook config fields
├── mcp/
│   ├── run_handler.py             # MODIFY: emit telemetry after execution
│   └── create_handler.py          # MODIFY: add configure_telemetry_webhook tool
└── api/v1/
    └── namespaces.py              # MODIFY: add webhook config REST endpoints

alembic/versions/
└── 20260408_000002_add_telemetry_webhook_columns.py  # NEW

tests/unit/
└── test_telemetry.py              # NEW
```

**Structure Decision**: Single backend API — one new service file, one new test file, one migration. Everything else is modifications.

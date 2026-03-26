# Implementation Plan: MCP Proxy Analytics & AI Self-Optimization

**Branch**: `010-mcp-proxy-analytics` | **Date**: 2026-03-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/010-mcp-proxy-analytics/spec.md`

## Summary

Per-call and per-execution telemetry captured in PostgreSQL from the MCP proxy, queryable via 4 MCP tools in a new ANALYTICS_TOOLS group. Includes a rule-based suggestion engine with optional live probing for field-level redact recommendations. APScheduler handles 30-day retention cleanup. Prometheus metrics exported for external monitoring.

## Technical Context

**Language/Version**: Python 3.11+ (existing codebase)
**Primary Dependencies**: FastAPI (existing), SQLAlchemy (existing), APScheduler (existing), prometheus_fastapi_instrumentator (existing)
**Storage**: PostgreSQL (existing — two new tables: `mcp_proxy_calls`, `mcp_execution_stats`)
**Testing**: pytest (existing)
**Target Platform**: Linux server (Docker container)
**Project Type**: Single backend project (extends existing mcpworks-api)
**Performance Goals**: Telemetry capture < 1ms (async INSERT); stats query < 200ms for 24h aggregation
**Constraints**: No Redis for analytics (PostgreSQL only); suggestion engine is rule-based (no LLM calls); probes are user-triggered only
**Scale/Scope**: ~1000 calls/day per namespace, 30-day retention, ~6MB/month storage per namespace

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec complete with 4 clarifications |
| II. Token Efficiency | PASS | Analytics tools return structured summaries < 500 tokens. Suggestion responses are compact action items. |
| III. Transaction Safety | PASS | Async INSERT is fire-and-forget. Stats queries are read-only. No transaction concerns. |
| IV. Provider Abstraction | PASS | Generic MCP proxy telemetry — works with any MCP server. |
| V. API Contracts & Tests | PASS | 4 MCP tools with defined schemas. Unit + integration tests. |

**Gate: PASSED**

## Project Structure

### Documentation

```text
specs/010-mcp-proxy-analytics/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── mcp-tools.md     # Tool contracts
└── tasks.md             # Phase 2 output
```

### Source Code

```text
src/mcpworks_api/
├── models/
│   ├── mcp_proxy_call.py           # New: call telemetry model
│   └── mcp_execution_stat.py       # New: execution stats model
├── services/
│   └── analytics.py                # New: stats aggregation, suggestion engine
├── schemas/
│   └── analytics.py                # New: Pydantic response schemas
├── core/
│   └── mcp_proxy.py                # Modified: capture telemetry after each call
├── mcp/
│   ├── create_handler.py           # Modified: 4 new analytics tool handlers
│   ├── tool_registry.py            # Modified: ANALYTICS_TOOLS group
│   └── run_handler.py              # Modified: capture execution stats
├── tasks/
│   └── cleanup.py                  # New: APScheduler 30-day retention cleanup

alembic/versions/
└── YYYYMMDD_000001_add_analytics_tables.py

tests/
├── unit/
│   ├── test_analytics_service.py   # Aggregation, suggestion engine
│   └── test_telemetry_capture.py   # Call record formatting
└── integration/
    └── test_analytics_e2e.py       # Proxy call → stats query → suggestions
```

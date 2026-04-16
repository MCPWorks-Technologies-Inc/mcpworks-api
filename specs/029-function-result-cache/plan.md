# Implementation Plan: Function Result Caching (Redis)

**Branch**: `029-function-result-cache` | **Date**: 2026-04-15 | **Spec**: [spec.md](spec.md)

## Summary

Add opt-in result caching for function executions using Redis. Cache keys derived from function_id + version + hash(input). Check Redis before sandbox dispatch in run_handler, store on success, skip on error. Per-function cache_policy JSONB column. Prometheus metrics for hit/miss. Graceful degradation when Redis is unavailable.

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: FastAPI, SQLAlchemy 2.0+ async, redis.asyncio (existing)
**Storage**: PostgreSQL (new cache_policy JSONB on functions), Redis (cache entries)
**Testing**: pytest unit tests
**Performance Goals**: Cache hits < 50ms, graceful Redis failure
**Constraints**: No thundering herd protection v1, no cross-namespace sharing

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Full spec completed |
| II. Token Efficiency | PASS | Cached responses eliminate redundant sandbox execution |
| III. Transaction Safety | PASS | Cache is best-effort, never blocks execution |
| IV. Observability | PASS | Prometheus hit/miss counters, execution metadata |
| V. API Contracts | PASS | Cache bypass via existing input mechanism |

## Project Structure

```text
src/mcpworks_api/
├── services/
│   └── result_cache.py        # NEW — cache check/store/key generation
├── mcp/
│   ├── run_handler.py          # MODIFIED — inject cache layer before execute
│   ├── create_handler.py       # MODIFIED — configure_cache handler
│   └── tool_registry.py        # MODIFIED — configure_cache tool definition
├── models/
│   └── function.py             # MODIFIED — cache_policy JSONB column
└── middleware/
    └── execution_metrics.py    # MODIFIED — cache hit/miss counters

alembic/versions/
└── 20260415_000002_*.py        # NEW — add cache_policy to functions

tests/unit/
└── test_result_cache.py        # NEW — cache key generation, policy parsing
```

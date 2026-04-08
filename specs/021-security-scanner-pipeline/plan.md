# Implementation Plan: Pluggable Security Scanner Pipeline

**Branch**: `021-security-scanner-pipeline` | **Date**: 2026-04-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/021-security-scanner-pipeline/spec.md`

## Summary

Build a configurable, per-namespace security scanner pipeline for prompt injection defense. Three scanner types (builtin, webhook, python) evaluate content in sequence. Refactor existing injection_scan.py, trust_boundary.py, and credential_scan.py into built-in scanner implementations. Store pipeline config as JSONB on namespaces. Scan results feed into execution records (spec 020). MCP tools for pipeline management.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, httpx (webhook calls), structlog
**Storage**: PostgreSQL 15+ (JSONB on namespaces for pipeline config; scan results in executions.backend_metadata)
**Testing**: pytest
**Target Platform**: Linux server (Docker)
**Project Type**: Single backend API
**Performance Goals**: Built-in scanners <2ms total; webhook timeout configurable (default 5s); pipeline short-circuits on block
**Constraints**: Must not break existing injection scanning behavior; fail-open by default; backward compatible
**Scale/Scope**: Per-namespace config, typically 2-5 scanners per pipeline

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First Development | PASS | Spec complete with research |
| II. Token Efficiency & Streaming | PASS | Scan results are compact metadata, not returned to LLM. Trust boundary wrapping reduces effective token load by marking untrusted content |
| III. Transaction Safety & Security | PASS | This feature IS security. Fail-open default is deliberate — availability over false positives for self-hosters. Security-sensitive users can configure fail-closed |
| IV. Provider Abstraction & Observability | PASS | Scanner pipeline IS provider abstraction (builtin/webhook/python). Full scan decision logging via structlog |
| V. API Contracts & Test Coverage | PASS | Webhook protocol and Python scanner interface defined in spec. Tests planned for pipeline evaluation, each scanner type, short-circuit behavior |

## Project Structure

### Source Code

```text
src/mcpworks_api/
├── core/
│   ├── scanner_pipeline.py      # NEW: Pipeline evaluator (orchestrates scanner sequence)
│   ├── scanners/                # NEW: Scanner implementations
│   │   ├── __init__.py
│   │   ├── base.py              # Scanner interface + ScanVerdict dataclass
│   │   ├── pattern_scanner.py   # REFACTOR: from sandbox/injection_scan.py
│   │   ├── secret_scanner.py    # REFACTOR: from sandbox/credential_scan.py
│   │   ├── trust_boundary.py    # REFACTOR: from core/trust_boundary.py
│   │   ├── webhook_scanner.py   # NEW: HTTP POST to external service
│   │   └── python_scanner.py    # NEW: importable Python callable
│   └── trust_boundary.py        # KEPT: backward-compat wrapper (delegates to scanners/)
├── models/
│   └── namespace.py             # MODIFIED: Add scanner_pipeline JSONB column
├── mcp/
│   ├── run_handler.py           # MODIFIED: Call pipeline in dispatch path
│   ├── create_handler.py        # MODIFIED: Scanner management tools
│   └── tool_registry.py         # MODIFIED: Register scanner management tools
├── sandbox/
│   └── injection_scan.py        # KEPT: backward-compat, delegates to scanners/pattern_scanner

alembic/
└── versions/
    └── xxx_add_scanner_pipeline.py  # NEW: Migration

tests/
└── unit/
    ├── test_scanner_pipeline.py     # NEW: Pipeline evaluation tests
    ├── test_pattern_scanner.py      # NEW: Refactored pattern scanner tests
    ├── test_webhook_scanner.py      # NEW: Webhook scanner with mock HTTP
    └── test_python_scanner.py       # NEW: Python scanner loading tests
```

### Key Design Decisions

**Scanner interface** (`core/scanners/base.py`):
```python
@dataclass
class ScanVerdict:
    action: str          # "pass", "flag", "block"
    score: float         # 0.0 - 1.0
    reason: str          # human-readable
    scanner_name: str
    timing_ms: float

class BaseScanner:
    async def scan(self, content: str, context: ScanContext) -> ScanVerdict
```

**Pipeline evaluator** (`core/scanner_pipeline.py`):
- Loads scanner config from namespace JSONB (or global defaults)
- Instantiates scanners (builtin loaded at import, webhook/python loaded on first use)
- Evaluates in order, highest severity wins, short-circuits on block
- Returns `PipelineResult` with per-scanner verdicts and final decision
- All verdicts logged via structlog

**Backward compatibility**:
- `injection_scan.scan_for_injections()` still works (delegates to pattern scanner)
- `trust_boundary.wrap_function_output()` still works (delegates to trust boundary scanner)
- `mcp_rules.py` evaluate_response_rules still calls injection_scan for MCP server plugins
- No existing behavior changes unless namespace configures custom pipeline

## Complexity Tracking

No violations. Uses existing patterns (JSONB config, scanner refactor, httpx for webhooks).

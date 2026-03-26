# Implementation Plan: Prompt Injection Defense

**Branch**: `009-prompt-injection-defense` | **Date**: 2026-03-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/009-prompt-injection-defense/spec.md`

## Summary

Three-layer prompt injection defense: per-function mandatory `output_trust` flag with trust boundary wrapping, pattern-based injection scanner, and per-MCP-server request/response rules. Trust markers wrap the result string visible in the AI context. Scanner follows same architecture as existing `credential_scan.py`. Rules managed via existing MCP_SERVER_TOOLS group.

## Technical Context

**Language/Version**: Python 3.11+ (existing codebase)
**Primary Dependencies**: FastAPI (existing), re module (stdlib), structlog (existing)
**Storage**: PostgreSQL (existing — new `output_trust` column on functions, new `rules` JSONB on namespace_mcp_servers)
**Testing**: pytest (existing), adversarial test corpus
**Target Platform**: Linux server (Docker container)
**Project Type**: Single backend project (extends existing mcpworks-api)
**Performance Goals**: Scanner < 5ms for 100KB responses; rule evaluation < 1ms per rule
**Constraints**: Pattern-based only (no LLM calls in Phase 1); fail-open by default; markers are string wrapping (not metadata)
**Scale/Scope**: Runs on every RemoteMCP proxy response and every `output_trust: data` function result

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec complete with 6 clarifications |
| II. Token Efficiency | PASS | Markers add ~50 tokens per wrapped result. No impact on `output_trust: prompt` functions. |
| III. Transaction Safety | PASS | No transactions involved — markers applied post-execution, rules evaluated in proxy |
| IV. Provider Abstraction | PASS | Scanner and rules are generic — no MCP-server-specific code |
| V. API Contracts & Tests | PASS | 4 new MCP tools (3 rule mgmt + update_function param), unit + adversarial tests defined |

**Gate: PASSED**

## Project Structure

### Documentation

```text
specs/009-prompt-injection-defense/
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
├── sandbox/
│   └── injection_scan.py           # New: pattern-based injection scanner
├── core/
│   ├── mcp_proxy.py                # Modified: apply response rules + scan
│   └── trust_boundary.py           # New: trust marker wrapping functions
├── mcp/
│   ├── create_handler.py           # Modified: output_trust on make/update_function, rule mgmt tools
│   ├── run_handler.py              # Modified: wrap results for output_trust:data functions
│   └── tool_registry.py            # Modified: add rule tools to MCP_SERVER_TOOLS, update_function schema
├── models/
│   └── function.py                 # Modified: output_trust column
├── services/
│   └── mcp_server.py               # Modified: rule CRUD methods

alembic/versions/
└── YYYYMMDD_000001_add_output_trust_and_rules.py

tests/
├── unit/
│   ├── test_injection_scan.py      # Scanner pattern tests
│   ├── test_trust_boundary.py      # Marker wrapping tests
│   └── test_mcp_rules.py           # Rule engine tests
├── integration/
│   └── test_injection_defense.py   # End-to-end with proxy
└── fixtures/
    └── injection_payloads.txt      # Adversarial test corpus
```

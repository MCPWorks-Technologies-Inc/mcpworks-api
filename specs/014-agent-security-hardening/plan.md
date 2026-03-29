# Implementation Plan: Agent Security Hardening

**Branch**: `014-agent-security-hardening` | **Date**: 2026-03-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/014-agent-security-hardening/spec.md`

## Summary

Two security changes: (1) strip function management tools from agent AI orchestration so agents cannot author/modify functions, and (2) extend the existing output secret scanner with additional prefixes, env var value matching, and security event logging.

## Technical Context

**Language/Version**: Python 3.11+ (existing codebase)
**Primary Dependencies**: FastAPI 0.109+, structlog (existing)
**Storage**: PostgreSQL 15+ (existing, security events via fire_security_event)
**Testing**: pytest with async fixtures
**Target Platform**: Linux server (Docker Compose self-hosted)
**Project Type**: Single backend API
**Performance Goals**: Scanner adds <10ms to execution results
**Constraints**: No new dependencies; extends existing output_sanitizer.py and ai_tools.py
**Scale/Scope**: Minimal — two focused changes to existing modules

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec complete with clarification |
| II. Token Efficiency | PASS | Scanner operates on output strings, no token impact |
| III. Transaction Safety | PASS | Redaction is idempotent, no state changes |
| IV. Provider Abstraction | PASS | No provider-specific code |
| V. API Contracts | PASS | No tool signature changes — tools are removed from agent AI, not modified |

## Project Structure

### Documentation (this feature)

```text
specs/014-agent-security-hardening/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── core/
│   ├── ai_tools.py               # MODIFIED: add RESTRICTED_AGENT_TOOLS set, filter in build_tool_definitions
│   └── output_sanitizer.py       # MODIFIED: add missing prefixes, add scrub_env_values(), fire security events
├── tasks/
│   └── orchestrator.py           # MODIFIED: pass env_values to scrub step (if not already done)
├── backends/
│   └── sandbox.py                # MODIFIED: pass env_values to scrub_secrets call
├── mcp/
│   └── run_handler.py            # VERIFIED: ensure scanner runs on run endpoint results

tests/unit/
├── test_output_sanitizer.py      # MODIFIED: add tests for new prefixes, env var matching, edge cases
└── test_ai_tools_restriction.py  # NEW: verify restricted tools excluded from agent orchestration
```

**Structure Decision**: Extends existing modules only. No new files except one test file.

## Complexity Tracking

No constitution violations. Both changes are minimal extensions of existing patterns.

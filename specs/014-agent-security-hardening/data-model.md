# Data Model: Agent Security Hardening

**Branch**: `014-agent-security-hardening`

## No New Tables

This feature modifies behavior, not data structures. No database migrations required.

## Existing Entities Used

### Security Events (existing `security_events` table)

Used via `fire_security_event()` for:
- `secret_detected` — when output scanner redacts a secret (already partially implemented)
- `restricted_tool_attempt` — NEW event type when agent AI tries to call a blocked tool

### Secret Pattern (in-code only, not persisted)

A compile-time list of regex patterns in `output_sanitizer.py`. Each entry:
- Regex pattern (e.g., `sk_live_[a-zA-Z0-9]{12,}`)
- Replacement string (e.g., `[REDACTED_STRIPE_KEY]`)
- Implicit 20-character minimum from regex quantifiers

### Env Var Values (request-scoped, never persisted)

Passed from the `X-MCPWorks-Env` header decode step to the scanner. Values exist only in memory during the request lifecycle. The scanner checks for exact matches of values >= 8 characters.

## Affected Existing Files

| File | Changes |
|------|---------|
| `src/mcpworks_api/core/output_sanitizer.py` | Add 10 new secret patterns, add `scrub_env_values()` function |
| `src/mcpworks_api/core/ai_tools.py` | Add `RESTRICTED_AGENT_TOOLS` set, add `agent_mode` param to `build_tool_definitions` |
| `src/mcpworks_api/backends/sandbox.py` | Pass env values to scrub step |
| `src/mcpworks_api/tasks/orchestrator.py` | Log restricted_tool_attempt security events |

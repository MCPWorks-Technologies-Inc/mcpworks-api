# Quickstart: Agent Security Hardening

**Branch**: `014-agent-security-hardening`

## Implementation Order

1. Add new secret patterns to `output_sanitizer.py`
2. Add `scrub_env_values()` function to `output_sanitizer.py`
3. Wire env values through to scrub step in `sandbox.py`
4. Add `RESTRICTED_AGENT_TOOLS` blocklist to `ai_tools.py`
5. Filter blocked tools in `build_tool_definitions` for agent mode
6. Log `restricted_tool_attempt` security events in orchestrator
7. Tests for all of the above
8. Documentation updates

## Smoke Test

1. Run existing test suite — no regressions
2. Create a function that returns `"sk_live_" + "a" * 30` — verify redacted
3. Create a function that returns the value of an env var — verify redacted
4. Create a function that returns `{"total": 42}` — verify NOT redacted
5. Chat with an agent — verify make_function is not in the AI's tool list
6. Check security events after redaction — verify event logged

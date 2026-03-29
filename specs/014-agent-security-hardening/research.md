# Research: Agent Security Hardening

**Branch**: `014-agent-security-hardening`

## R1: Agent Tool Restriction

**Decision**: Add a `RESTRICTED_AGENT_TOOLS` set to `ai_tools.py` and filter these out in `build_tool_definitions` when called for agent orchestration.

**Rationale**: The agent AI's tool palette is built by `build_tool_definitions()` in `core/ai_tools.py`. This function returns namespace functions + platform tools. It does NOT currently include create-endpoint tools (make_function, etc.) — those live in the MCP create handler. However, the function needs an explicit blocklist to prevent future regressions if someone adds function management to platform tools.

**Key finding**: Agents currently cannot call make_function through orchestration — the tool simply isn't in the list. But this is implicit, not enforced. Adding an explicit blocklist makes the security boundary auditable and prevents accidental inclusion.

**Alternatives considered**:
- Allowlist approach (only permit specific tools): More restrictive but harder to maintain as new platform tools are added.
- Blocklist approach (explicitly exclude dangerous tools): Chosen — easier to audit, self-documenting, and the blocklist is short and stable.

## R2: Output Secret Scanner Extension

**Decision**: Extend `output_sanitizer.py` with additional patterns and env var value matching.

**Rationale**: The existing `scrub_secrets()` function already handles `sk-`, `AKIA`, `ghp_`, `gho_`, JWTs, and connection URIs. Missing: Stripe keys (`sk_live_`, `sk_test_`, `pk_live_`, `pk_test_`, `rk_live_`, `rk_test_`, `whsec_`), Slack tokens (`xoxb-`, `xoxp-`, `xoxa-`), and dynamic env var value matching.

**Key finding**: The scanner already runs in `backends/sandbox.py` line 281 after execution. It fires `fire_security_event` on line 283. The infrastructure for security events is already in place.

**New patterns to add** (with 20-char minimum total length):
- `sk_live_[a-zA-Z0-9]{12,}` — Stripe live secret key
- `sk_test_[a-zA-Z0-9]{12,}` — Stripe test secret key
- `pk_live_[a-zA-Z0-9]{12,}` — Stripe live publishable key
- `pk_test_[a-zA-Z0-9]{12,}` — Stripe test publishable key
- `rk_live_[a-zA-Z0-9]{12,}` — Stripe restricted key
- `rk_test_[a-zA-Z0-9]{12,}` — Stripe restricted test key
- `whsec_[a-zA-Z0-9]{12,}` — Stripe webhook secret
- `xoxb-[a-zA-Z0-9-]{20,}` — Slack bot token
- `xoxp-[a-zA-Z0-9-]{20,}` — Slack user token
- `xoxa-[a-zA-Z0-9-]{20,}` — Slack app token

**Env var value matching**: New function `scrub_env_values(output, env_values)` that takes the actual env var values and does exact string replacement for values >= 8 characters.

## R3: Security Event Logging

**Decision**: Use existing `fire_security_event()` pattern already called in `sandbox.py`.

**Rationale**: Line 283 of `backends/sandbox.py` already calls security event logging when secrets are detected. The event includes function name, namespace, and redaction count. This just needs to be extended with the pattern category and also wired up for the agent tool restriction.

**Key finding**: `fire_security_event()` is a fire-and-forget async call via `asyncio.create_task()`. It logs to the `security_events` table with structured fields. No new infrastructure needed.

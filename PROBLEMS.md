# MCPWorks API - Known Problems

This file tracks significant issues discovered during API testing that need resolution.

---

## Open Issues

No open issues.

---

## Resolved Issues

### ~~NOTE: Safe Logging Strategy — ORDER-020 through ORDER-023~~

**Filed:** 2026-02-20
**Status:** RESOLVED (2026-03-12)

All four logging orders implemented:
- **ORDER-020:** `input_data`/`result_data` never persisted (Execution model unused; admin endpoint hardcoded to NULL)
- **ORDER-021:** Structured JSON logging via structlog (`main.py:62-110`, `request_logging.py`)
- **ORDER-022:** Security events table with `hash_ip()`, `fire_security_event()`, wired to auth/billing/sandbox, `GET /v1/audit/logs` endpoint
- **ORDER-023:** PII scrub + 255-char truncation in `_scrub_error_message()` (`execution.py:26-32`)

Future consideration: decision logging for HITL approvals (A1 scope).

---

### ~~PROBLEM-015: `orchestration_mode` Locked to "direct" — No Way to Route Function Output to Agent AI~~

**Filed:** 2026-03-12
**Status:** RESOLVED (2026-03-12, commit `6dc5b59`)
**Reported by:** External user (simon.carr@gmail.com) via support@mcpworks.io — DogeDetective agent (Report #2)

`orchestration_mode` existed on schedules/webhooks but was not exposed as a settable parameter in the MCP tool schemas. Fixed by adding `orchestration_mode` as an enum parameter (`direct`, `reason_first`, `run_then_reason`) to both `add_schedule` and `add_webhook` MCP tools. Added full server-side orchestration pipeline: AI client (`chat_with_tools` for Anthropic/OpenAI/Google), orchestrator loop with per-tier safety limits, auto-channel posting, and webhook ingress handler. See spec `specs/004-agent-orchestration/`.

---

### ~~PROBLEM-013: Agent Orchestration Architecture Undocumented — Schedule/Channel/Function Integration Unclear~~

**Filed:** 2026-03-11
**Status:** RESOLVED (2026-03-12, commit `6dc5b59`)
**Reported by:** External user (simon.carr@gmail.com) via support@mcpworks.io — DogeDetective agent

All questions answered by the 004-agent-orchestration implementation:
- **Agent as tool-caller:** Yes — all namespace functions are presented as callable tools to the AI (format: `service__function`)
- **Channel output routing:** AI can call `send_to_channel` platform tool; `auto_channel` field on agents auto-posts final AI responses
- **Webhook external URL:** `https://{agent-name}.agent.mcpworks.io/webhook/{path}`
- **Three orchestration modes:** `direct` (no AI), `reason_first` (AI decides), `run_then_reason` (run function, AI analyzes output)
- Platform tools: `send_to_channel`, `get_state`, `set_state`

---

### ~~PROBLEM-014: Schedules Not Executing — Zero Observed Runs Despite Enabled Status~~

**Filed:** 2026-03-12
**Status:** RESOLVED (2026-03-12, commit `f2df73c`)
**Reported by:** External user (simon.carr@gmail.com) + internal testing
**Namespaces affected:** `dogedetective` (builder-agent), `mcpworkssocial` (pro-agent)

`add_schedule` stored metadata but nothing executed it. The `agent-runtime/` scheduler existed but was never deployed (no docker-compose reference). Fixed by adding an in-process scheduler to the API server that polls `AgentSchedule` rows every 30s, executes due functions via the sandbox backend, records `AgentRun` results, and applies failure policies (continue, auto_disable, backoff). Added `croniter` dependency for cron expression parsing.

---

### ~~PROBLEM-011: Network Blocked for pro-agent Tier — Misleading Tool Descriptions~~

**Filed:** 2026-03-11
**Status:** RESOLVED (2026-03-12, commit `3aa5704`)

Agent tiers (`pro-agent`, `builder-agent`, `enterprise-agent`) were not recognized by `ExecutionTier` enum, silently falling back to free tier resource limits. The `_tier_notice()` then reported "Network: BLOCKED" even though network actually worked (the shell script's `!= "free"` check gave MACVLAN access). Also: `api-connector` and `slack-notifier` templates were shown to all tiers without warning.

**Fixes:**
- Added `resolve_execution_tier()` to map agent tiers to base tiers
- Updated `spawn-sandbox.sh` case statement for agent tier variants
- Templates marked with `requires_network=True`; `list_templates` adds warnings for blocked tiers
- `make_function` warns when code imports network libraries on network-blocked tiers (commit `f2df73c`)

---

### ~~PROBLEM-012: create_service and create_function Return "Service not found"~~

**Filed:** 2026-03-11
**Status:** RESOLVED (2026-03-12, commit `3aa5704` — mitigated via documentation)
**Reported by:** External user (simon.carr@gmail.com) via support@mcpworks.io

Could not reproduce on internal namespace. Investigation showed the underlying code path is correct — `make_service` and `make_function` resolve services by name within the namespace set by the MCP server connection URL. The user's LLM (kimi-k2-thinking via OpenRouter) likely passed extra parameters like `namespace="alice"` that the tool doesn't accept, causing confusing errors.

**Fix:** Rewrote all MCP tool descriptions with comprehensive guidance for less capable models: workflow ordering, parameter explanations, examples, and explicit notes that namespace is set by the connection URL.

---

### ~~PROBLEM-010: MCP `make_function` Convention Not Documented — `handler()` Silently Fails~~

**Filed:** 2026-03-05
**Status:** RESOLVED (2026-03-05; nsjail regression fixed 2026-03-12 commit `2eb23ae`)

Sandbox wrapper now recognizes `handler(input, context)` as a valid entry point (called with empty dict context). The `make_function` tool description documents all four recognized patterns: `main(input)`, `handler(input, context)`, top-level `result`, top-level `output`.

**Regression found 2026-03-12:** The fix was only applied to dev-mode `_wrap_code` in `sandbox.py` but missed the production nsjail `execute.py`. Fixed in commit `2eb23ae`.

---

### ~~TODO-001: Update Tier Execution Limits (Pricing v5.2.0)~~

**Filed:** 2026-03-05
**Status:** RESOLVED (2026-03-06)

Updated all execution limits 10x across billing middleware, config, Stripe service, subscription model, console pricing UI, quickstart page, dashboard, ToS, and all tests. Concurrency limits updated in ToS. Rate limits per-minute not yet enforced in code (only documented).

---

### ~~PROBLEM-009: "whitelist" → "allowlist" terminology migration~~

**Status:** RESOLVED (2026-03-01)

Full rename completed across all source, templates, tests, and documentation. Only remaining "whitelist" references are in alembic migration history (correct — migrations are immutable).

---

### ~~PROBLEM-008: Misleading commit message in git history~~

**Status:** RESOLVED (2026-03-01, documented — cannot rewrite shared history)

Commit `7fc38ff` message says "switch seccomp to denylist" but the implementation actually added an allowlist. Corrected in commit `7c7b892`. No code issue.

---

### ~~PROBLEM-007: Legacy ServiceRouter and math/agent endpoints~~

**Status:** RESOLVED (2026-03-01)

Deleted all legacy gateway-era dead code.

---

### ~~PROBLEM-006: Code-Mode Execution Not Exposed via MCP Run Server~~

**Status:** RESOLVED (2026-02-20)

Flipped default from tools mode to code mode. `{ns}.run.mcpworks.io/mcp` now serves code-mode by default (single `execute` tool).

---

### ~~PROBLEM-005: MCP Run Server Tools Not Discoverable / Returning Null~~

**Status:** RESOLVED (2026-02-12)

Two root causes: `str(EndpointType.CREATE)` enum comparison bug, and sandbox wrapper not calling `main(input_data)`. Both fixed.

---

### ~~PROBLEM-001–004: Auth, Services, Usage, API Keys~~

**Status:** RESOLVED (2026-02-11)

All initial API endpoint issues resolved: usage tracking implemented, list services fixed, create service error handling fixed, API key prefix corrected to `mcpw_`.

---

## Notes

- API key prefix is now `mcpw_` (correct)
- New API key endpoint at `/v1/auth/api-keys` with improved response format
- Legacy endpoint `/v1/users/me/api-keys` still works for backward compatibility
- Subscription endpoint returns 404 "No subscription found" for free tier users (expected)

---

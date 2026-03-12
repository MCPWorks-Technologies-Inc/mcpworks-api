# MCPWorks API - Known Problems

This file tracks significant issues discovered during API testing that need resolution.

---

## Open Issues

### PROBLEM-013: Agent Orchestration Architecture Undocumented — Schedule/Channel/Function Integration Unclear

**Filed:** 2026-03-11
**Status:** OPEN
**Severity:** High (blocking agent usability)
**Reported by:** External user (simon.carr@gmail.com) via support@mcpworks.io — DogeDetective agent
**Namespace:** `dogedetective`

**Problem:** User built a full agent with functions, schedules, webhooks, and a Discord channel, but cannot determine how the pieces connect. The agent's AI model is configured but never invoked by the platform. All functions are self-contained because the orchestration model is undocumented.

**Specific questions requiring answers:**

1. **Schedule → AI flow:** When a scheduled function runs and returns output, does that output get passed to the agent's AI model for processing? Or does the schedule just silently execute the function?

2. **Agent as tool-caller:** When the AI agent is invoked, does it automatically see all functions in its namespace as callable tools? Can it decide to call `search-news` or `analyze-price` during reasoning?

3. **Channel output routing:** When a Discord channel is configured via `add_channel`, how does the AI agent post to it? Is there an implicit `send_message` / `post_to_channel` tool, or does the agent's text output automatically route to the channel?

4. **Webhook external URL:** `add_webhook` returns a webhook ID and path but no callable external URL. What is the full URL to POST to for triggering a webhook?

5. **Environment isolation:** Functions cannot access the agent's AI config (e.g., OpenRouter API key). The key is configured on the agent via `configure_agent_ai` but the sandbox only exposes `PYTHONPATH`, `HOME`, `LANG`, and SSL vars. Users are forced to duplicate API keys as function env vars.

6. **Complete lifecycle:** What is the intended trigger → AI → action flow?
   `Schedule fires → [?] → AI agent processes → [how does it call tools?] → [how does it output to channels?]`

**Impact:** Users build agents but end up with disconnected parts — functions that do everything themselves, an AI model that's never invoked, and channels that receive nothing. The agent abstraction isn't delivering its value.

**User's observation:** *"Right now? Nothing. The agent is running with an AI model and system prompt configured, but everything is handled by standalone functions that never involve it."*

---

### NOTE: Safe Logging Strategy — Implementation Tracked in ORDERS.md

**Filed:** 2026-02-20
**Status:** Spec complete, implementation pending (ORDER-020 through ORDER-023)

The question of how to safely log MCP server requests (given PII, credentials, and sensitive data in request/response bodies) has been fully spec'd:

- **Spec:** `../mcpworks-internals/docs/implementation/logging-specification.md` (v1.0.0)
- **Implementation orders:** ORDER-020 (stop logging PII in execution records), ORDER-021 (structured JSON logging), ORDER-022 (security events table), ORDER-023 (truncate/PII-scrub error messages)

**Core principles:** Log metadata never content. Hash IPs, reference API keys by prefix only. `input_data` and `result_data` fields must be NULL by default — only populated with opt-in debug logging (A1). Error messages truncated to 255 chars with PII scrub (email patterns, phone patterns, API key patterns).

**Iain Harper's "decision logging" gap** (from iain.so MCP tooling article, Feb 2026): Most observability tools log *what happened* but not *why it was allowed*. Consider adding policy-context logging for HITL approvals in A1. See `../mcpworks-internals/docs/research/competitive/2026-02-20_mcp-tooling-security-crisis-analysis.md`.

---

## Resolved Issues

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

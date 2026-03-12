# MCPWorks API — Support & Problems Report

**Date:** 2026-03-12
**Source:** `mcpworks-api/PROBLEMS.md` + support@mcpworks.io inbox
**Prepared by:** Claude Opus 4.6

---

## Executive Summary

4 open issues, 1 critical. The scheduler (PROBLEM-014) is non-functional — no scheduled functions execute on any tier. This blocks all automated agent functionality and is the single highest priority fix. Three external user reports were received and responded to within the same session.

---

## Summary Stats

| Metric | Count |
|--------|-------|
| Total problems filed | 14 |
| Open | 4 |
| Resolved | 10 |
| Critical (open) | 1 (PROBLEM-014) |
| High (open) | 2 (PROBLEM-012, PROBLEM-013) |
| Blocking (open) | 1 (PROBLEM-011 — partial fix deployed) |
| External user reports received | 3 |
| Support replies sent | 3 |

---

## Open Issues

### 🔴 PROBLEM-014: Schedules Not Executing (Critical)

**Filed:** 2026-03-12
**Namespaces affected:** `dogedetective` (builder-agent), `mcpworkssocial` (pro-agent)
**Reported by:** External user + internal testing

Schedules created via `add_schedule` show as `enabled` with `consecutive_failures: 0`, but functions are never invoked. Hard evidence:

- `check-price` call count matches exactly 5 manual REPL runs — zero from `*/5 * * * *` schedule
- `hourly-report` call count matches exactly 3 manual REPL runs — zero from hourly schedule
- Dedicated test function on `*/5 * * * *` waited 15+ minutes with 0 executions
- Agent restart did not help
- Also affects `mcpworkssocial` agent's `daily-intelligence-report` schedule

**Impact:** All automated agent functionality is broken. Agents are REPL-only.

**Missing observability:** No execution logs, no last/next run times, no "run now" trigger, ambiguous failure counter.

**Resolution needed:** Determine if scheduler process is running or if `add_schedule` only stores metadata.

---

### PROBLEM-013: Agent Orchestration Undocumented (High)

**Filed:** 2026-03-11
**Namespace:** `dogedetective`
**Reported by:** External user

Users cannot determine how the agent pipeline connects. The agent has AI configured, functions deployed, schedules set, channels added — but the AI is never invoked. Six specific questions remain unanswered:

1. Does scheduled function output get passed to the agent's AI?
2. Can the AI call its own functions as tools?
3. How does the AI post to configured channels?
4. What is the webhook external URL format?
5. Why can't functions access the agent's AI config?
6. What is the complete trigger → AI → action lifecycle?

**Impact:** Users build agents with disconnected parts. The agent abstraction delivers no value.

---

### PROBLEM-012: create_service/create_function Wrong Errors (High)

**Filed:** 2026-03-11
**Namespace:** `alice` (some)
**Reported by:** External user

`create_service` returns "Service not found" on CREATE operations. `create_function` can't find services that `list_services` confirms exist. Suspected namespace scoping bug where create endpoints resolve differently than list endpoints.

**Partial fix:** Tool descriptions rewritten in commit `3aa5704` to clarify correct parameter usage. Needs confirmation that the underlying lookup logic is also fixed.

**Impact:** Users cannot create services or functions despite valid auth.

---

### PROBLEM-011: Network Tier Mapping / Stale Tool Descriptions (Blocking → Partial Fix)

**Filed:** 2026-03-11

Agent tiers (`pro-agent`, `builder-agent`, `enterprise-agent`) were silently falling back to free tier resource limits. Network actually works — the tier mapping in `resolve_execution_tier()` and `spawn-sandbox.sh` was incorrect.

**Fix committed:** `3aa5704` — tier mapping corrected, tool descriptions rewritten.

**Remaining issue:** MCP run server tool description still shows "Network: BLOCKED" for pro-agent tier (confirmed via `mcp__mcpworks-mcpworkssocial-run__execute` tool schema). Likely a cached/stale description. Runtime networking confirmed working.

---

## Support Correspondence

| Date | Subject | From | Action Taken |
|------|---------|------|-------------|
| 2026-03-11 16:43 | OpenRouter/glm-5 create errors | simon.carr@gmail.com | Filed PROBLEM-012, replied |
| 2026-03-11 16:48 | DogeDetective problems report | simon.carr@gmail.com | Filed PROBLEM-013, replied |
| 2026-03-11 17:40 | Agent orchestration follow-up | simon.carr@gmail.com | Updated PROBLEM-013 |
| 2026-03-11 17:42 | Further information + test results | simon.carr@gmail.com | Filed PROBLEM-014, replied |
| 2026-03-12 18:35 | Agent Setup Report #2 (attachment) | simon.carr@gmail.com | Filed PROBLEM-014, replied |

All replies sent from support@mcpworks.io with acknowledgment and tracking numbers.

---

## Recently Resolved

| Problem | Description | Resolved |
|---------|-------------|----------|
| PROBLEM-011 | Network tier mapping (partial) | 2026-03-11 (commit 3aa5704) |
| TODO-001 | Tier execution limits 10x | 2026-03-06 |
| PROBLEM-010 | handler() entry point undocumented | 2026-03-05 |
| PROBLEM-009 | whitelist→allowlist migration | 2026-03-01 |
| PROBLEM-008 | Misleading commit message | 2026-03-01 (documented) |
| PROBLEM-007 | Legacy ServiceRouter cleanup | 2026-03-01 |
| PROBLEM-006 | Code-mode MCP exposure | 2026-02-20 |
| PROBLEM-005 | MCP run server tools null | 2026-02-12 |
| PROBLEM-001–004 | Auth, services, usage, API keys | 2026-02-11 |

---

## Resolution Priority

| Priority | Problem | Why |
|----------|---------|-----|
| 1 | PROBLEM-014 | Blocks ALL automated agent functionality across ALL namespaces |
| 2 | PROBLEM-013 | Users can't build useful agents without understanding the pipeline |
| 3 | PROBLEM-012 | Core CRUD operations broken for at least one namespace |
| 4 | PROBLEM-011 | Stale descriptions mislead users; runtime works |

---

## Pending Implementation (Not Problems)

| Item | Status | Reference |
|------|--------|-----------|
| Safe logging (ORDER-020–023) | Spec complete, implementation pending | `logging-specification.md` v1.0.0 |
| Rate limits per-minute | Documented only, not enforced in code | PRICING.md v5.2.0 |

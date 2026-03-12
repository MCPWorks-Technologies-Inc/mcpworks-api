# Support Report — 2026-03-11

**Source:** support@mcpworks.io inbox (2 reports from real user testing)
**Compiled:** 2026-03-11
**Priority:** HIGH — these are user-facing issues blocking real agent deployments

---

## SUPPORT-001: MCP Write Operations Fail While Read Operations Succeed

**Source:** Email — "Questions from a client using OpenRouter and glm-5"
**Namespace:** `some` (user `alice`)
**Model:** kimi-k2-thinking via OpenRouter
**Severity:** CRITICAL — users cannot create services or functions

### Symptoms

List operations work correctly:
- `list_namespaces` → namespace `alice` (created 2025-12-30)
- `list_services` → service `demoservice` (status: active)
- `list_packages` → Python, Python-Data, Python-AI
- `list_templates` → hello-world, echo, scheduled
- `list_functions` → empty array

Write operations fail with wrong errors:

| Operation | Expected | Actual | Bug |
|-----------|----------|--------|-----|
| `create_service(name="test-service", namespace="alice")` | Creates service | `"Service not found: test-service"` | Returns "not found" on a **create** operation |
| `create_function(service="demoservice", name="test-func", ...)` | Creates function | `"Service not found: demoservice"` | Contradicts `list_services` which shows `demoservice` as active |

### Analysis

1. **Service lookup by name vs ID mismatch:** The create endpoints may be looking up the service by the wrong identifier (name vs UUID vs slug). `list_services` returns the service, but `create_function` can't find it using the same name.

2. **`create_service` error is semantically wrong:** A create operation should never return "not found" for the resource being created. This suggests the handler is doing a lookup before creation (checking for the namespace? checking for duplicates?) and the error message is misleading.

3. **Possible namespace resolution issue:** The user passes `namespace="alice"` as a string name, but the backend may expect a namespace ID. The MCP tool schema may not make this clear.

### Suggested Investigation

- Check `src/mcpworks_api/` service creation handler — is it resolving namespace by name or ID?
- Check `create_function` — how does it resolve `service="demoservice"`? Name? ID? Slug?
- Check MCP tool schemas in the create server — do parameter descriptions clarify name vs ID?
- Verify the `some` namespace account is in good standing with valid subscription

---

## SUPPORT-002: Sandbox Network Isolation Contradicts Available Packages and Templates

**Source:** Email attachment — `AGENT_SETUP_REPORT.md` (DogeDetective agent)
**Namespace:** Unknown (builder-agent tier)
**Agent:** dogedetective (DOGE price alert bot)
**Severity:** HIGH — confusing UX, blocks legitimate use cases

### Problem

The `code_sandbox` backend runs inside nsjail with `clone_newnet:true`, creating a fully isolated network namespace. **All outbound connections are blocked** — HTTP, DNS, sockets all hang until the 10-second execution timeout.

However, the platform:
1. **Ships HTTP client packages:** `httpx`, `requests`, `aiohttp` are pre-installed and importable
2. **Provides an `api-connector` template** that uses `httpx` to call external APIs
3. **Does not warn at function creation time** — the error only surfaces at runtime (timeout after 10s)

### User Impact

The user attempted to build a DOGE price monitoring agent that:
- Fetches prices from CoinGecko every 5 minutes
- Analyzes for significant moves (threshold-based)
- Posts alerts to Discord

None of the HTTP-dependent functions work. The user was forced into these workarounds:
- **Webhook-driven architecture** — pushes complexity outside the platform
- **AI-as-price-fetcher** — schedules AI inference every 5 min (wasteful, ~$0.01-0.05/invocation)
- **Native Discord channel** — works, but only solves output, not input (fetching prices)

### Specific Contradictions

| What the platform says | What actually happens |
|------------------------|----------------------|
| `httpx`, `requests`, `aiohttp` are available packages | All fail at runtime — network blocked |
| `api-connector` template exists and uses `httpx` | Template code will always timeout |
| `make_function` docs: "Upgrade to Builder tier for network access" | User is on `builder-agent` tier — still blocked |

### Recommendations

**Immediate (docs/UX fix):**
1. Remove `api-connector` template OR gate it to network-enabled tiers only
2. Add clear warning in `make_function` response when creating functions that import network libraries on a network-blocked tier
3. Clarify tier naming: `builder-agent` vs `Builder` — does agent tier include network or not?

**Short-term (feature):**
4. Enable network access for Builder tier and above (the sandbox spec already contemplates this via `network_allowlist`)
5. Expose `network_allowlist` management through MCP tools so users can allowlist specific domains (e.g., `api.coingecko.com`)

**Medium-term (platform capability):**
6. Expose agent state read/write APIs inside the sandbox via env vars or a local socket
7. Allow functions to conditionally trigger the AI agent (function→agent invocation)

---

## SUPPORT-003: No Internal Platform APIs Available Inside Sandbox

**Source:** Email attachment — `AGENT_SETUP_REPORT.md` (DogeDetective agent)
**Severity:** MEDIUM — limits function↔agent interaction patterns

### Problem

The sandbox environment exposes only basic env vars: `PYTHONPATH`, `HOME`, `LANG`, `SSL_CERT_FILE`, and thread settings (OpenBLAS/OMP). No MCPWorks internal APIs are available.

### Impact

Functions cannot:
- **Read/write agent state** (e.g., store price history between executions)
- **Trigger the AI agent conditionally** (e.g., only invoke inference when thresholds are met)
- **Communicate between functions** (no shared state or message passing)

This forces the "dumb schedule → AI every time" pattern, which is wasteful. The ideal architecture (documented in the report) would have a pure-computation function check prices and only invoke the AI agent on significant moves — estimated to reduce AI costs from ~$14/day to ~$0/day during normal markets.

### Recommendations

1. Inject a scoped MCPWorks API token into the sandbox via env var or stdin (per ORDER-003 pattern)
2. Expose a minimal internal API surface:
   - `GET /internal/state/{key}` — read agent state
   - `PUT /internal/state/{key}` — write agent state
   - `POST /internal/agent/trigger` — conditionally invoke the agent
3. Route internal API calls through a local socket or loopback, not through the public internet

---

## SUPPORT-004: `describe_agent` Did Not Return `system_prompt` Field

**Source:** Email attachment — `AGENT_SETUP_REPORT.md` (DogeDetective agent)
**Severity:** LOW — resolved during the user's session (platform update deployed mid-session)

### Problem

Initially, `describe_agent` did not include the `system_prompt` field in its response, making it impossible to inspect or extract the agent's configured prompt.

### Status

Resolved — confirmed fixed during the session. Documenting for regression tracking.

---

## Cross-Cutting Observations

### User Profile
- Technical user comfortable with MCP protocol, agent architecture, and workaround design
- Using non-Anthropic model (kimi-k2-thinking via OpenRouter) — validates BYOAI strategy
- Willing to work around platform limitations but documented everything clearly
- The quality of this report suggests a power user who could become an advocate if issues are resolved

### Architecture Implications
- The "functions as building blocks, agents as product" strategy (Board 2026-03-10) makes SUPPORT-002 and SUPPORT-003 especially important — agents need functions that can interact with the outside world and with platform state
- The agent tier pricing needs clearer mapping to sandbox capabilities (network access, state access, schedule minimums)

### Related Orders
- **ORDER-003** (token injection via fd) — same pattern needed for internal API access in sandbox
- **ORDER-011** (function templates) — `api-connector` template is actively misleading users
- **ORDERS.md Standing Order #1** ("No new backends") — user suggests trying `activepieces` backend, but this is deferred to A1

---

## Action Items

| # | Action | Priority | Effort | Related |
|---|--------|----------|--------|---------|
| 1 | Debug service name/ID resolution in create_service and create_function | CRITICAL | 1-2 hrs | SUPPORT-001 |
| 2 | Remove or gate `api-connector` template behind network-enabled tiers | HIGH | 30 min | SUPPORT-002 |
| 3 | Add network library detection warning in `make_function` response | HIGH | 1-2 hrs | SUPPORT-002 |
| 4 | Clarify `builder-agent` vs `Builder` tier network capabilities in docs and MCP tool descriptions | HIGH | 1 hr | SUPPORT-002 |
| 5 | Design sandbox internal API surface (state read/write, agent trigger) | MEDIUM | Spec first | SUPPORT-003 |
| 6 | Add regression test for `describe_agent` system_prompt field | LOW | 30 min | SUPPORT-004 |
| 7 | Reply to support emails acknowledging issues and timeline | HIGH | 15 min | All |

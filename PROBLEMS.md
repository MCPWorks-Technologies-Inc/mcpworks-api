# MCPWorks API - Known Problems

This file tracks significant issues discovered during API testing that need resolution.

---

## Open Issues

### PROBLEM-016: Sandbox Network Connectivity Failure — Paid Tiers Cannot Reach External Services

**Filed:** 2026-03-12
**Status:** OPEN (investigating)
**Severity:** P1 — All paid-tier sandbox executions requiring network access are broken
**Reported by:** External user (simon.carr@gmail.com) via support@mcpworks.io — DogeDetective agent
**Affected tiers:** Builder, Pro, Enterprise (Free tier correctly has no network — working as designed)

#### Symptoms

Agent functions that make HTTP requests (e.g., CoinGecko API, Reddit API) fail with:
```
[Errno -3] Temporary failure in name resolution
```

User-initiated diagnostics from inside the sandbox revealed:
- `resolv.conf` correctly points to `8.8.8.8` and `8.8.4.4` (Google DNS)
- TCP `connect_ex` to `8.8.8.8:53` returns error 11 (`EAGAIN`) — not a timeout, actively rejected
- TCP `connect_ex` to `1.1.1.1:53` returns error 11 (`EAGAIN`) — same
- `/proc/net/route` access denied — can't inspect routing table
- Hostname: `unknown`, can't resolve itself
- No IPv6 available
- All domain resolution fails: `api.coingecko.com`, `google.com`, `reddit.com`

This is **not a DNS issue** — it's **zero network connectivity**. The sandbox has a network namespace with no working egress path.

#### Architecture Context

Network isolation uses `clone_newnet: true` (nsjail config) to give each sandbox its own network namespace:

- **Free tier:** Empty network namespace, no MACVLAN → zero connectivity (correct, per spec)
- **Paid tiers:** MACVLAN interface on container's `eth0` with unique IP from `172.18.128-254.X.Y`

The MACVLAN is configured in `spawn-sandbox.sh` lines 207-212:
```bash
if [ "${TIER}" != "free" ]; then
    NSJAIL_ARGS+=(--macvlan_iface eth0)
    NSJAIL_ARGS+=(--macvlan_vs_ip "${MACVLAN_IP}")
    NSJAIL_ARGS+=(--macvlan_vs_nm "255.255.0.0")
    NSJAIL_ARGS+=(--macvlan_vs_gw "172.18.0.1")
fi
```

#### Root Cause Analysis (In Progress)

**What we've confirmed works in the code:**

| Component | Status | Evidence |
|-----------|--------|---------|
| `clone_newnet: true` | Correct | `python.cfg` line 27 |
| MACVLAN creation for paid tiers | Correct | `spawn-sandbox.sh` lines 207-212 |
| IP assignment (172.18.128-254.X.Y) | Correct | Hash-based derivation, same /16 subnet as gateway |
| Gateway specification (172.18.0.1) | Correct | Docker bridge gateway |
| Seccomp allows networking | Correct | `socket`, `connect`, `bind`, `sendto`, `recvfrom`, `ioctl` all in ALLOW list |
| nsjail adds default route via `--macvlan_vs_gw` | Confirmed | nsjail source `net.cc`: `ioctl(SIOCADDRT)` with dst=0.0.0.0 via gateway |
| Host iptables rules (if applied) | Correct | `setup-sandbox-network.sh` allows DNS, blocks internal, NATs outbound |

**Probable failure points (need production host verification):**

1. **MACVLAN on Docker veth:** The container's `eth0` is a veth pair endpoint connected to the Docker bridge. MACVLAN on veth has known kernel limitations — some configurations don't support it, or the Docker bridge may not forward traffic from MACVLAN-originated MAC addresses. This is the most likely root cause.

2. **Host iptables not applied or lost:** `setup-sandbox-network.sh` must run on the HOST (not inside the container) because MACVLAN traffic bypasses the container's network namespace. If the host's FORWARD chain has a default DROP policy and these rules haven't been applied (or were lost on reboot), all sandbox traffic is silently dropped.

3. **Docker bridge MAC filtering:** Docker bridges may only forward traffic from known MAC addresses (the container's veth MAC). MACVLAN creates a new virtual MAC address that the bridge hasn't seen, and the bridge may drop it.

4. **ARP resolution failure:** The sandbox needs to ARP for the gateway (172.18.0.1) before sending any packets. If the Docker bridge doesn't respond to ARP from the MACVLAN interface's MAC, no traffic flows. Error 11 (EAGAIN) from `connect_ex` is consistent with ARP failing silently.

#### Verification Steps Needed (on production host)

```bash
# 1. Check if host iptables rules exist
iptables -L FORWARD -n -v | grep 172.18.128
iptables -t nat -L POSTROUTING -n -v | grep 172.18.128

# 2. Check Docker bridge settings
brctl show  # or: bridge link show
# Check if promiscuous mode is enabled on the bridge

# 3. Test MACVLAN on Docker veth from host
# Create a test MACVLAN interface on the container's veth and try to ping gateway
docker exec mcpworks-api ip link show eth0
ip link add test-mv link <container-veth-on-host> type macvlan mode bridge
ip addr add 172.18.200.1/16 dev test-mv
ip link set test-mv up
ping -c 1 172.18.0.1  # Does gateway respond?

# 4. Check kernel support
cat /proc/sys/net/ipv4/conf/all/forwarding  # Must be 1
dmesg | grep -i macvlan  # Any kernel errors?
```

#### Workaround Options (if MACVLAN is fundamentally broken on Docker veth)

**Option A — veth pair instead of MACVLAN (most robust):**
Replace MACVLAN with a veth pair: create one end on the host/container, move the other into the sandbox namespace, add IP/route. This is how Docker itself does networking and works reliably on all kernel versions.

**Option B — `--disable_clone_newnet` + iptables isolation (simpler, less isolated):**
Disable network namespacing and use UID-based iptables rules for network access control. Reduces isolation but avoids the MACVLAN-on-veth problem entirely. Was the previous architecture before commit `4a01d99`.

**Option C — Docker `--net=host` + MACVLAN on physical interface:**
Run the container with host networking so MACVLAN attaches to the physical NIC instead of a veth. Simpler but reduces container isolation.

#### Related

- **PROBLEM-011** (RESOLVED): Agent tiers falling back to free tier — fixed the tier mapping but didn't address underlying network connectivity
- **SECURITY_AUDIT.md FINDING-38:** Docker gateway reachable on 80/443 during audit — implies MACVLAN worked at some point, or was tested differently
- **Commit `4a01d99`** (Mar 9): Original clone_newnet + MACVLAN implementation
- **Commit `16490da`** (Mar 9): Subnet fix (10.200 → 172.18) — addressed "route unreachable" but not the deeper MACVLAN-on-veth question
- **Commit `0b4df92`** (Mar 8): Disabled clone_newnet in smoketest because it broke network for tiktoken — early signal that network in sandboxes wasn't working

#### Files

| File | Purpose |
|------|---------|
| `deploy/nsjail/python.cfg` | nsjail config — `clone_newnet: true` (line 27) |
| `deploy/nsjail/spawn-sandbox.sh` | MACVLAN setup for paid tiers (lines 207-212) |
| `src/mcpworks_api/backends/sandbox.py` | Tier config with network flags (lines 50-75) |
| `scripts/setup-sandbox-network.sh` | Host-level iptables rules (must be applied on HOST) |
| `deploy/nsjail/seccomp.policy` | Seccomp allowlist — networking syscalls allowed (lines 180-198) |

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

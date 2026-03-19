# MCPWorks API - Known Problems

This file tracks significant issues discovered during API testing that need resolution.

---

## Open Issues

### PROBLEM-022: DeepSeek V3.2 via OpenRouter Cannot Make Structured Tool Calls — Agent Orchestration Non-Functional (PARTIAL FIX)

**Filed:** 2026-03-19
**Status:** OPEN
**Severity:** P1 — Agent orchestration completely non-functional for DeepSeek V3.2 via OpenRouter
**Reported by:** Internal (agent-leadgenerator workspace)
**Namespace affected:** `leadgenerator` (pro-agent, OpenRouter engine, DeepSeek V3.2)

#### Symptoms

After PROBLEM-019/020/021 fixes were applied, two distinct failures remain:

**Failure 1 — `chat_with_agent` burns iterations without calling functions:**

The orchestration loop runs (confirmed by hitting `max_iterations`), but no functions are actually called. Evidence:

| Function | Call Count Before | Call Count After 2 Full Pipeline Attempts |
|----------|-------------------|------------------------------------------|
| `harvest-leads` | 7 | 7 (unchanged) |
| `investigate-lead` | 0 | 0 (unchanged) |
| `store-lead` | 0 | 0 (unchanged) |
| `notify-discord` | 0 | 0 (unchanged) |

With `max_iterations=100`, the loop exhausted all iterations and returned `"(Max chat iterations reached)"`. Despite the system prompt explicitly naming the functions and providing a step-by-step pipeline, DeepSeek V3.2 consumed 100 iterations without producing a single structured `tool_calls` response that the orchestrator could execute.

On the first attempt (before old functions were deleted), the AI called the old monolithic `run-pipeline` function and `score-leads` instead of the new individual functions — suggesting it may have been making some tool calls that worked, but fell back to the old pipeline. After those functions were deleted, zero functions were called across 100 iterations.

**Failure 2 — Webhook orchestration still returns 500:**

```
POST https://leadgenerator.agent.mcpworks.io/webhook/run-pipeline
→ 500 {"error":"INTERNAL_ERROR","message":"An unexpected error occurred","details":{}}
```

Tested after PROBLEM-021 was marked resolved. Same opaque 500. Either:
- The fix hasn't been deployed to production
- The fix addressed one failure mode but there's another (e.g., the OpenRouter API itself returns an error when DeepSeek V3.2 receives tools)

#### Root Cause Analysis

**Hypothesis A — DeepSeek V3.2 does not emit structured `tool_calls` via OpenRouter:**

DeepSeek V3.2's "agentic task synthesis pipeline" may work differently from OpenAI's structured tool-calling protocol. When tools are passed via the OpenAI-compatible API, DeepSeek may:
1. Acknowledge the tools in its reasoning but emit function calls as **text** (e.g., markdown code blocks or JSON in the content field) rather than structured `tool_calls` objects
2. Return `finish_reason: "stop"` with no `tool_calls` array — the PROBLEM-021 fix handles this for the case where `tool_calls` IS present but `finish_reason` is wrong, but not for the case where `tool_calls` is completely absent
3. Use a proprietary format that OpenRouter doesn't translate to the OpenAI-compatible schema

Evidence: The first run's AI response included text like:
```
"I'll call leads.harvest-leads now.\n\n```json\n{\"name\": \"leads.harvest_leads\"}\n```"
```
This is the AI **writing** a function call as text content, not producing a structured `tool_calls` response. The orchestrator only processes `message.tool_calls` — text-embedded calls are ignored.

**Hypothesis B — OpenRouter returns an error when passing tools to DeepSeek V3.2:**

The OpenRouter API may not support tool-calling for all models. If `POST /chat/completions` with `"tools": [...]` returns a 400/422 error for DeepSeek V3.2, the `_tools_openai()` function would raise `AIClientError`, which propagates as a 500 from the webhook handler.

**Hypothesis C — Iteration burn from extended reasoning:**

DeepSeek V3.2 may produce very long chain-of-thought responses that each count as an iteration. If each response is text-only (no `tool_calls`), the orchestrator would:
1. Check `stop_reason` → `"end_turn"` (no tool calls detected)
2. Count as one iteration
3. But with no tool calls to execute, there's nothing to feed back
4. The loop may re-prompt the AI, which generates another reasoning response

This would explain why 100 iterations are consumed with zero function calls — the AI is "thinking out loud" in a loop.

#### Verification Steps

These require access to production logs or a debuggable environment:

```python
# 1. Check what OpenRouter actually returns for DeepSeek + tools
import httpx, json

resp = httpx.post("https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": "Bearer sk-or-v1-..."},
    json={
        "model": "deepseek/deepseek-v3.2",
        "messages": [{"role": "user", "content": "Call the get_weather function for Toronto"}],
        "tools": [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather for a city",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}
            }
        }]
    })
print(resp.status_code, resp.text)
# Key questions:
# - Does it return tool_calls or text?
# - What is finish_reason?
# - Is there an error about unsupported features?

# 2. Test same payload with a known-working model
# Replace model with "anthropic/claude-sonnet-4.6" or "openai/gpt-4o"
# If those work, the issue is DeepSeek-specific

# 3. Add logging to orchestrator.py loop
# Log each iteration: response content type, stop_reason, tool_calls present/absent
```

#### Impact

- The `leadgenerator` agent cannot run autonomously — no scheduled runs, no webhook triggers, no chat-based orchestration
- All functions are proven working via direct `execute_python` calls, but the AI-driven orchestration layer cannot connect them
- This likely affects any agent using DeepSeek V3.2 (or potentially other non-OpenAI models) via OpenRouter with tool-calling
- The PROBLEM-020 "pseudo-function text extraction fallback" (deferred to A1) would solve Hypothesis A — the AI IS trying to call functions, just in text format that the orchestrator ignores

#### Proposed Fixes (in priority order)

**Fix 1 — Verify and deploy PROBLEM-021 fixes to production:**
The webhook 500 may simply be an undeployed fix. Verify the production codebase matches the resolved changes.

**Fix 2 — Add raw response logging to `_tools_openai()`:**
Before any parsing, log `resp.status_code` and `resp.text[:1000]` to understand what OpenRouter/DeepSeek actually returns. This is the single most important diagnostic.

**Fix 3 — Text-based tool call extraction (PROBLEM-020 item 2):**
If DeepSeek emits tool calls as text, add a fallback parser that extracts function calls from the response content. Pattern:
```python
# After checking message.tool_calls, also check message.content for text-embedded calls
if not tool_calls and message.get("content"):
    tool_calls = extract_tool_calls_from_text(message["content"])
```

**Fix 4 — Model-specific tool-call verification:**
Before using a model for orchestration, make a test tool-call request during `configure_agent_ai` to verify the model supports structured tool calling via its provider. Warn the user if it doesn't.

**Fix 5 — Orchestrator loop guard:**
If N consecutive iterations produce no tool calls and no new text (or identical text), break the loop early with a diagnostic message instead of burning through all iterations.

#### Workaround

Until fixed, the pipeline can be run manually via `execute_python`:
```python
from functions import harvest_leads, investigate_lead, store_lead, notify_discord
# Call each function sequentially — proven working
```

Or switch the agent to a model known to support structured tool calling (e.g., `anthropic/claude-sonnet-4.6` via OpenRouter, or native Anthropic engine).

#### Partial Resolution (2026-03-18)

Code analysis revealed the actual failure cascade was different from the hypotheses:

**Actual root cause:** DeepSeek V3.2 IS returning structured `tool_calls` (otherwise the loop would exit on iteration 1 — the orchestrator returns immediately when `stop_reason != "tool_use"`). However, DeepSeek calls functions by **wrong names** (e.g., `run-pipeline` instead of `leads__harvest-leads`). Three compounding bugs turned this into a 100-iteration burn:

1. **Failed dispatches counted as successful calls** (`orchestrator.py:252`): `functions_called.append()` ran regardless of whether the dispatch succeeded or returned an error. After 10 failed dispatches, `max_functions_called` triggered, giving the AI the misleading error "Function call limit exceeded" — even though zero functions actually executed.

2. **"Unknown tool" error didn't list available tools** (`orchestrator.py:342`, `agent_service.py:841`): When `parse_tool_name()` returned `None` (no `__` separator), the error was just `"Unknown tool: run-pipeline"` with no guidance on the correct format or available tool names. The AI had no way to self-correct.

3. **No consecutive failure guard**: Both the orchestrator loop and `chat_with_agent` loop would happily burn through all iterations even when every single tool call in every iteration was failing.

**Fixes applied:**

- **`ai_tools.py`**: Added `format_available_tools()` helper that formats tool names for error messages
- **`orchestrator.py`**:
  - `functions_called.append()` now only runs on successful dispatches (no `"error"` in result)
  - `_dispatch_tool()` accepts `available_tools` parameter; "Unknown tool" errors now include the correct name format and list of available tools
  - Added `consecutive_failures` counter — after 3 consecutive iterations where ALL tool calls fail, the loop breaks early with a diagnostic message
  - "Function call limit exceeded" error now includes the limit number and instructs the AI to summarize and finish
- **`agent_service.py`**: Same three fixes applied to `chat_with_agent` loop and `_dispatch_chat_tool()`

**Remaining (not fixed):**
- DeepSeek V3.2 may still call wrong tool names — but now it gets a helpful error with correct names and the loop stops after 3 failed attempts instead of burning 100 iterations
- Text-embedded tool call extraction (PROBLEM-020 item 2) still deferred to A1
- Webhook 500 still needs production deployment verification (PROBLEM-021 fix)

#### Related

- PROBLEM-019 (RESOLVED): `chat_with_agent` now uses orchestration loop — but loop is non-functional for DeepSeek
- PROBLEM-020 (PARTIAL): Tool-calling format adaptation — text extraction fallback was deferred, now shown to be necessary
- PROBLEM-021 (RESOLVED): Webhook 500 hardening — fix may not be deployed, or DeepSeek triggers a different failure path

---

### ~~PROBLEM-021: Webhook Orchestration Returns 500 — `reason_first` Mode Fails for OpenRouter/DeepSeek~~

**Filed:** 2026-03-19
**Status:** RESOLVED (2026-03-19)
**Severity:** P1 — All webhook-triggered AI orchestration broken for OpenRouter engine
**Reported by:** Internal (agent-leadgenerator workspace)
**Namespace affected:** `leadgenerator` (pro-agent, OpenRouter engine, DeepSeek V3.2)

#### Symptoms

POST to `https://leadgenerator.agent.mcpworks.io/webhook/run-pipeline` with `orchestration_mode=reason_first` returns:
```json
{"error": "INTERNAL_ERROR", "message": "An unexpected error occurred", "details": {}}
```

HTTP 500 with no actionable error details. Tried with both `{}` and `{"trigger": "manual_test"}` payloads — same result.

#### Architecture Context

Webhook handler at `webhooks.py:84-118` correctly routes `reason_first` mode to `run_orchestration()` in `orchestrator.py:91-303`, which calls `chat_with_tools()` → `_tools_openai()` in `ai_client.py:322-382`.

The `_tools_openai()` function:
1. Converts tools via `_convert_tools_to_openai()` (lines 267-278)
2. POSTs to `https://openrouter.ai/api/v1/chat/completions`
3. Parses response expecting `choice["message"]["tool_calls"]` (lines 357-369)

#### Probable Root Cause

Multiple fragile points in `_tools_openai()` that could produce unhandled exceptions:

1. **No validation of `choices` array:** Line 351 does `data["choices"][0]` without checking if `choices` exists or is empty. OpenRouter may return `{"error": {...}}` or `{"choices": []}` on failure.

2. **`finish_reason` mapping:** Line 371 maps `"tool_calls"` → `"tool_use"`, but DeepSeek V3.2 via OpenRouter may return `"function_call"` or `"stop"` even when tool calls are present. This would cause the orchestrator to exit the loop prematurely (it checks `stop_reason == "tool_use"` to continue iterating).

3. **Silent argument parsing:** Lines 357-361 catch `JSONDecodeError`/`KeyError` when parsing tool call arguments but silently substitute `{}`. If DeepSeek returns arguments in a different structure (e.g., already-parsed dict instead of JSON string), this masks the real issue.

4. **Generic error handler:** The 500 response has `"details": {}` — the webhook handler or orchestrator is catching the exception but stripping all context. Need to log the actual exception with traceback.

#### Verification Steps

```python
# 1. Add logging to _tools_openai() before response parsing
logger.info(f"OpenRouter response: {resp.status_code} {resp.text[:1000]}")

# 2. Check if OpenRouter returns an error for the model+tools combination
# DeepSeek V3.2 may not support all tool-calling features via OpenRouter

# 3. Test with a known-working model (e.g., anthropic/claude-sonnet-4.6 via OpenRouter)
# to isolate whether the issue is DeepSeek-specific or general OpenRouter
```

#### Resolution

Fixed `_tools_openai()` in `ai_client.py` with four hardening changes:
1. **Validate `choices` array** — `.get("choices")` with error logging and meaningful `AIClientError` if empty/missing (handles OpenRouter 200-with-error responses)
2. **Detect tool calls by presence** — `has_tool_use` flag (matching Google provider pattern) instead of relying on `finish_reason`. DeepSeek V3.2 returns `"stop"` even when tool calls are present; now `stop_reason` is `"tool_use"` whenever `message.tool_calls` exists
3. **Handle argument format variance** — `isinstance(raw_args, dict)` check before `json.loads()`, catches `TypeError` that was silently dropping arguments
4. **Fallback for missing fields** — `tc.get("id") or f"call_{i}"` and `func_data.get("name", f"unknown_{i}")` prevent `KeyError` on non-standard responses

Also enabled actual exception logging in `error_handler.py` (was commented out — all 500s were silently swallowed).

#### Related

- PROBLEM-019 (below) — `chat_with_agent` doesn't use orchestration at all
- PROBLEM-020 (below) — architectural gap in tool-calling format support

---

### ~~PROBLEM-019: `chat_with_agent` Does Not Use Orchestration Loop — No Tool Calling~~

**Filed:** 2026-03-19
**Status:** RESOLVED (2026-03-19)
**Severity:** P2 — Agent chat is text-only, cannot call functions
**Reported by:** Internal (agent-leadgenerator workspace)

#### Symptoms

`chat_with_agent` MCP tool sends a message to the agent's AI, but the AI cannot call any namespace functions. It responds with text describing what it *would* call (e.g., `"I'll call leads.harvest-leads now"` followed by a markdown code block) instead of actually executing function calls.

#### Root Cause

`agent_service.py:693-723` — `chat_with_agent()` calls the simple `chat()` function (`ai_client.py:43-65`), NOT `chat_with_tools()`. No tool definitions are built or passed to the AI.

```python
# agent_service.py line 708
response = await chat(        # <-- simple chat, no tools
    engine=agent.ai_engine,
    model=agent.ai_model or "",
    api_key=api_key,
    message=message,
    system_prompt=agent.system_prompt,
)
```

Compare with the orchestrator (`orchestrator.py:168`) which correctly uses:
```python
response = await chat_with_tools(  # <-- full orchestration with tools
    engine=agent.ai_engine,
    model=agent.ai_model or "",
    api_key=api_key,
    messages=messages,
    tools=tools,
    system_prompt=agent.system_prompt,
)
```

#### Expected Behavior

`chat_with_agent` should run the orchestration loop (or at minimum pass tool definitions via `chat_with_tools`), allowing the AI to call namespace functions, platform tools, and MCP server tools during a conversation.

#### Fix

Replace `chat()` with a mini orchestration loop in `chat_with_agent()`:
1. Build tool definitions via `build_tool_definitions()` from `ai_tools.py`
2. Call `chat_with_tools()` instead of `chat()`
3. Execute any tool calls the AI makes
4. Return the final text response

Alternatively, refactor to call `run_orchestration()` directly with `trigger_type="chat"`.

#### Impact

- Users cannot test agent orchestration via `chat_with_agent` — the only way to trigger tool-calling is via schedules or webhooks
- This makes agent development and debugging significantly harder
- The system prompt tells the AI about its tools, but it can never use them in chat mode

#### Resolution

Replaced `chat()` with a mini orchestration loop in `agent_service.py:chat_with_agent()`:
1. Builds tool definitions via `build_tool_definitions()` (namespace functions + platform tools)
2. Loads MCP server tools if configured
3. Calls `chat_with_tools()` in a loop (max 10 iterations)
4. Dispatches tool calls via `_dispatch_chat_tool()` — handles platform tools (get_state, set_state, send_to_channel), MCP tools, and namespace functions
5. Returns final text response after AI completes

Updated MCP tool description to reflect new capabilities. MCP handler now passes `account` object for tier-aware state operations.

---

### ~~PROBLEM-020: Agent AI Tool-Calling Format Assumes Provider Uniformity — Needs Dynamic Adaptation~~

**Filed:** 2026-03-19
**Status:** PARTIALLY RESOLVED (2026-03-19) — OpenAI-compatible path hardened; full adapter layer deferred
**Severity:** P2 — Architectural gap affecting multi-provider BYOAI
**Reported by:** Internal (agent-leadgenerator workspace)

#### Context

MCPWorks agents support BYOAI (Bring Your Own AI) — users configure any LLM via Anthropic, OpenAI, Google, or OpenRouter engines. The platform presents namespace functions as callable tools to the AI during orchestration. This works when the AI model reliably follows the tool-calling protocol of its provider, but breaks when models have idiosyncratic behavior.

#### Current Architecture

`ai_client.py` supports three tool-calling code paths:

| Engine | Function | Tool Format | Response Parsing |
|--------|----------|-------------|-----------------|
| `anthropic` | `_tools_anthropic()` | Native `tool_use` blocks | `content[].type == "tool_use"` |
| `openai` | `_tools_openai()` | OpenAI function format | `message.tool_calls[].function` |
| `google` | `_tools_google()` | `functionCall` format | `parts[].functionCall` |
| `openrouter` | `_tools_openai()` | OpenAI function format | Same as openai |

OpenRouter routes to `_tools_openai()` because it exposes an OpenAI-compatible API (`OPENAI_COMPATIBLE_BASE_URLS` mapping at `ai_client.py`).

#### Problem

This works for models that faithfully implement OpenAI's tool-calling spec, but many models accessed via OpenRouter have quirks:

1. **DeepSeek V3.2:** Uses OpenAI-compatible format but may return `finish_reason: "stop"` instead of `"tool_calls"` when making tool calls. The orchestrator checks `stop_reason == "tool_use"` to continue iterating — if DeepSeek returns `"stop"`, the loop exits and tool calls are never executed.

2. **Some models return tool calls as text:** Instead of structured `tool_calls` objects, they emit JSON or function-call syntax in the `content` field. The current parser only looks at `message.tool_calls` and ignores text-embedded calls.

3. **Argument format variance:** Some models return `arguments` as a parsed dict instead of a JSON string. The current code does `json.loads(tc["function"]["arguments"])` which would throw `TypeError` on a dict (caught by the generic except, but silently loses the arguments).

4. **Missing `id` field:** Some models don't return a `tool_call.id` — the code assumes it exists at `tc["id"]` (line 365).

#### Proposed Solution: Tool-Calling Adapter Layer

Instead of assuming all OpenRouter models behave identically, introduce a **tool-calling adapter** that can be overridden per-model or per-agent:

1. **Model-specific response parsers:** A registry of `(provider, model_prefix) → parser_function` that handles known quirks. For example, a DeepSeek parser that checks both `tool_calls` and text content for function calls.

2. **Agent-level override:** Allow `configure_agent_ai` to accept an optional `tool_call_format` parameter (e.g., `"openai_strict"`, `"openai_flexible"`, `"text_extraction"`) that tells the orchestrator how to parse responses from that agent's model.

3. **Pseudo-function fallback:** If structured tool calling fails, the orchestrator could fall back to a "pseudo-function" approach — instruct the model to output function calls in a known text format (e.g., `<tool_call>{"name": "...", "arguments": {...}}</tool_call>`) and parse those from the response text. This would work with any model regardless of its native tool-calling support.

4. **Better error surfacing:** When tool-call parsing fails, log the raw response and return a meaningful error instead of silently dropping to `{}` args or returning a generic 500.

#### Impact

- Agents using non-OpenAI models via OpenRouter may silently fail to call tools
- The BYOAI value proposition is weakened if only Anthropic/OpenAI models work reliably
- As MCPWorks onboards users with diverse model preferences, this will become a growing support burden

#### Partial Resolution

The immediate issues (items 1, 3, 4 from Proposed Solution) are addressed by PROBLEM-021 fixes:
- `has_tool_use` presence detection works for DeepSeek and other models that return `finish_reason: "stop"` with tool calls
- `isinstance(raw_args, dict)` handles already-parsed argument dicts
- Missing `id`/`name` fields handled with fallbacks
- Error logging enabled for all parsing failures

Remaining (deferred to A1):
- Item 2 (pseudo-function text extraction fallback for models with zero structured tool-call support)
- Per-model response parser registry
- Agent-level `tool_call_format` override

#### Related

- PROBLEM-019: `chat_with_agent` doesn't use orchestration
- PROBLEM-021: Webhook orchestration 500 (likely a manifestation of this format issue)

---

### ~~PROBLEM-017: `delete_function` MCP Tool Missing `confirmation_token` Parameter~~

**Filed:** 2026-03-18
**Status:** RESOLVED (2026-03-19)
**Severity:** P3 — Cosmetic / usability
**Reported by:** Internal (agent-leadgenerator workspace)

Replaced hard-delete + confirmation flow with soft-delete. `delete_function` now sets `deleted_at` timestamp instead of removing the row. Version history is preserved — if a function is re-created with the same name, it resurrects the existing record and continues the version sequence (e.g., v1 → deleted → re-created as v2). Removed `delete_function` from `CONFIRMATION_REQUIRED`. Also added PROBLEM-018 fix for scratchpad view `str(EndpointType)` bug.

---

### ~~PROBLEM-018: Scratchpad View Returns 404 — `str(EndpointType)` Enum Comparison Bug~~

**Filed:** 2026-03-19
**Status:** RESOLVED (2026-03-19)
**Severity:** P1 — All agent scratchpad views broken
**Reported by:** Internal (leadgenerator agent workspace)

`scratchpad_view.py` line 70 compared `str(endpoint_type) != "agent"` but `EndpointType` is `str, Enum` — in Python 3.11+ `str()` returns `"EndpointType.AGENT"` not `"agent"`. This made the guard always true, returning 404 for every agent view request. Fixed by comparing against `endpoint_type.value` instead.

Note: this is the same class of bug as PROBLEM-005 (`str(EndpointType.CREATE)` comparison).

---

## Resolved Issues

### ~~PROBLEM-016: Sandbox Network Connectivity Failure — Paid Tiers Cannot Reach External Services~~

**Filed:** 2026-03-12
**Status:** RESOLVED (2026-03-12, commits `6cff3ff`, `09965e5`, `f950343`)
**Severity:** P1 — All paid-tier sandbox executions requiring network access were broken
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

#### Resolution

**Root cause:** MACVLAN on Docker veth pairs is unreliable. Docker bridges filter unknown MAC addresses created by MACVLAN child interfaces, causing zero network connectivity. The container's `eth0` is a veth pair endpoint (not a physical NIC), and MACVLAN requires a physical parent or a bridge that accepts unknown MACs.

**Fix (Option A — veth pair):** Replaced MACVLAN with veth pair + NAT in `spawn-sandbox.sh`:
1. `ip netns add` creates a pre-configured network namespace per sandbox
2. Veth pair connects sandbox namespace to container namespace
3. Container acts as gateway with IP forwarding + MASQUERADE through default interface
4. iptables FORWARD chain blocks RFC1918, cloud metadata, non-DNS UDP
5. iptables INPUT chain blocks sandbox access to container services (API on :8000)
6. nsjail runs inside the namespace with `--disable_clone_newnet`

**Secondary fix:** Initial deploy hardcoded `eth0` for iptables rules, but the container has two Docker networks (`mcpworks-net` + `mcpworks-agents`), so the default route used a different interface. Fixed by auto-detecting via `ip route show default`.

**Security hardening:** veth pairs lack MACVLAN's inherent parent-child isolation, so added `iptables -I INPUT -i $VETH_HOST -j DROP` to prevent sandbox from reaching the container's gateway IP (and therefore the API, bypassing Caddy rate limiting).

**Accepted security deltas from MACVLAN approach:**
- `/proc/net` in paid-tier sandboxes shows veth topology (transient per-execution, low risk)
- Container is now an active NAT router (inherent veth tradeoff; container is already the trust boundary)
- Subnet collision possible at ~300 concurrent sandboxes (hash-based; sequential allocator is a future improvement)

**Commits:** `6cff3ff` (veth replacement), `09965e5` (interface detection), `f950343` (INPUT chain hardening)

#### Related

- **PROBLEM-011** (RESOLVED): Agent tiers falling back to free tier — fixed the tier mapping but didn't address underlying network connectivity
- **Commit `4a01d99`** (Mar 9): Original clone_newnet + MACVLAN implementation
- **Commit `0b4df92`** (Mar 8): Disabled clone_newnet in smoketest because it broke network for tiktoken — early signal

---

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

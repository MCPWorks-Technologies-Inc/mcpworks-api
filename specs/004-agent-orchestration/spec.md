# Feature Specification: Agent Orchestration — Trigger → AI → Action Pipeline

**Feature Branch**: `004-agent-orchestration`
**Created**: 2026-03-12
**Status**: Draft
**Depends on**: `003-containerized-agents` (implemented)
**Resolves**: PROBLEM-013

## Problem Statement

Users build agents with functions, schedules, webhooks, channels, and AI configuration — but the pieces are disconnected. Schedules fire functions directly without AI involvement. The AI model is never invoked by the platform (only via the admin `chat_with_agent` tool). Channels receive nothing. The agent abstraction delivers containers and cron, but not autonomous AI reasoning.

**User's observation:** *"The agent is running with an AI model and system prompt configured, but everything is handled by standalone functions that never involve it."*

## Design Goals

1. **Triggers invoke AI, not just functions.** Schedules and webhooks can optionally route through the agent's AI model before/after function execution.
2. **AI sees functions as tools.** When the AI is invoked, all functions in the agent's namespace are available as callable tools. The AI decides which functions to call during reasoning.
3. **AI can output to channels.** The AI has a built-in `send_to_channel` tool to post messages to configured Discord/Slack/etc. channels.
4. **AI can read/write state.** The AI has built-in `get_state` and `set_state` tools for persistent memory across invocations.
5. **Backward compatible.** Existing schedules that fire functions directly continue to work. AI orchestration is opt-in per schedule/webhook.

## Architecture

### Server-Side Orchestration

The orchestration loop runs **server-side in the API process**, not inside agent containers. This matches the existing pattern where `chat_with_agent` and the scheduler already run server-side.

Reasons:
- Agent containers run the agent-runtime (scheduler + webhook listener), but this code was never deployed and is not production-ready.
- Server-side orchestration avoids the complexity of injecting decrypted AI keys into containers.
- All function execution already goes through the sandbox backend — the orchestrator just calls the same path.
- Easier to observe, rate-limit, and bill centrally.

The agent-runtime container code remains available for future Phase 2 (container-side orchestration with local tool calling), but Phase 1 orchestration is entirely server-side.

### Orchestration Loop

```
Trigger (schedule/webhook/manual/channel message)
    │
    ├─ ai_orchestration = false ──→ Execute function directly (existing behavior)
    │
    └─ ai_orchestration = true ──→ Orchestration Loop:
        │
        1. Build context message from trigger:
        │   - Schedule: "Scheduled execution of {function}. Output: {result}" (if run-then-reason)
        │   - Schedule: "Scheduled trigger for {function}. Decide what to do." (if reason-first)
        │   - Webhook: "Webhook received on /{path}: {payload}"
        │   - Channel: "Message from {channel_type}: {content}"
        │
        2. Call AI with:
        │   - system_prompt (from agent config)
        │   - context message
        │   - tools: [namespace functions + send_to_channel + get_state + set_state]
        │   - conversation history (this invocation only)
        │
        3. Parse AI response:
        │   ├─ tool_use → Execute tool → Feed result back → Go to step 2
        │   └─ text response → Final answer
        │
        4. Record AgentRun with trigger_type="ai", result_summary=final text
        │
        5. If auto_channel configured → Route final text to channel
```

### Trigger Modes

Each schedule and webhook gains an `orchestration_mode` field:

| Mode | Behavior |
|------|----------|
| `direct` | Execute function directly, no AI involvement (default, backward-compatible) |
| `reason_first` | Invoke AI with trigger context, AI decides which functions to call |
| `run_then_reason` | Execute the target function first, then pass its output to AI for processing |

### Tool Definitions

When the AI is invoked, it receives these tools:

**Namespace functions** — Auto-generated from all functions in the agent's namespace:
```json
{
  "name": "service_name__function_name",
  "description": "...",  // from function description or code docstring
  "input_schema": { ... }  // from function's input_schema if defined
}
```

**Built-in platform tools:**

```json
{
  "name": "send_to_channel",
  "description": "Send a message to a configured communication channel",
  "input_schema": {
    "type": "object",
    "properties": {
      "channel_type": {"type": "string", "enum": ["discord", "slack", "email"]},
      "message": {"type": "string"}
    },
    "required": ["channel_type", "message"]
  }
}
```

```json
{
  "name": "get_state",
  "description": "Read a value from persistent agent state",
  "input_schema": {
    "type": "object",
    "properties": {
      "key": {"type": "string"}
    },
    "required": ["key"]
  }
}
```

```json
{
  "name": "set_state",
  "description": "Write a value to persistent agent state",
  "input_schema": {
    "type": "object",
    "properties": {
      "key": {"type": "string"},
      "value": {}
    },
    "required": ["key", "value"]
  }
}
```

### AI Client Changes

The current `ai_client.chat()` is message-in/text-out. It needs a new function:

```python
async def chat_with_tools(
    engine: str,
    model: str,
    api_key: str,
    messages: list[dict],
    tools: list[dict],
    system_prompt: str | None = None,
    max_tokens: int = 4096,
) -> dict:
    """Returns the full response object including tool_use blocks."""
```

This function must handle the tool-calling protocol for each provider:
- **Anthropic**: Native `tools` parameter, `tool_use`/`tool_result` content blocks
- **OpenAI-compatible**: `tools` parameter with `function` type, `tool_calls` in response
- **Google**: `tools` with `function_declarations`, `functionCall`/`functionResponse` parts

### Orchestrator Module

New module: `src/mcpworks_api/tasks/orchestrator.py`

```python
async def run_orchestration(
    agent: Agent,
    trigger_type: str,        # "cron", "webhook", "channel", "manual"
    trigger_context: str,     # Human-readable trigger description
    trigger_data: dict,       # Structured trigger payload
    max_iterations: int = 10, # Safety limit on tool-calling loops
) -> OrchestrationResult:
    """Execute the AI orchestration loop for an agent."""
```

**Safety limits (per orchestration invocation):**

| Limit | Builder | Pro | Enterprise |
|-------|---------|-----|------------|
| Max tool-call iterations | 5 | 10 | 25 |
| Max total tokens (input+output) | 50K | 200K | 1M |
| Max execution time | 60s | 120s | 300s |
| Max functions called | 3 | 10 | 25 |

### Channel Output

Two channel output modes:

1. **Explicit** — AI calls `send_to_channel` tool during reasoning.
2. **Auto-channel** — Agent has an `auto_channel` config field. If set, the AI's final text response is automatically posted to that channel type. Useful for "always post results to Discord" patterns.

### Webhook External URL

The full webhook URL pattern is:

```
https://{agent-name}.agent.mcpworks.io/webhook/{path}
```

Example: `https://dogedetective.agent.mcpworks.io/webhook/price-alert`

This is already routed by the subdomain middleware (`endpoint_type="agent"`) but the webhook ingress handler needs to be implemented in the API server (currently only exists in the undeployed agent-runtime).

### Channel Message Ingestion

When a Discord bot receives a message, it should trigger an orchestration run:
- `trigger_type = "channel"`
- `trigger_context = "Message from discord user {author}: {content}"`
- The AI processes and can reply via `send_to_channel`

This requires a server-side Discord bot listener (not per-container). Phase 1 scope: Discord only.

---

## User Scenarios & Testing

### User Story 1 — Schedule with AI Reasoning (Priority: P1)

A user creates a schedule with `orchestration_mode: "run_then_reason"`. The scheduled function executes, and its output is passed to the agent's AI model. The AI reasons about the result and sends a summary to Discord.

**Acceptance Scenarios:**

1. **Given** an agent with AI configured and a Discord channel, **When** a schedule fires with `run_then_reason` mode, **Then** the function executes first, its output is sent to the AI as context, and the AI's response is recorded as an AgentRun with trigger_type="ai".
2. **Given** the AI calls `send_to_channel(discord, "Price is up 15%!")`, **Then** the message appears in the configured Discord channel.
3. **Given** the AI calls a namespace function as a tool, **Then** the function executes via the sandbox backend and the result is fed back to the AI.

### User Story 2 — Webhook with AI Triage (Priority: P1)

A user creates a webhook with `orchestration_mode: "reason_first"`. When a webhook fires, the payload goes to the AI first. The AI decides which functions to call based on the payload content.

**Acceptance Scenarios:**

1. **Given** an agent with 3 functions (analyze-price, search-news, generate-report), **When** a webhook fires with `reason_first` mode, **Then** the AI receives the payload and can call any of the 3 functions as tools.
2. **Given** the AI calls `analyze-price` and gets a result, **When** the AI decides to also call `generate-report` with the analysis, **Then** both calls execute and results feed back to the AI.
3. **Given** the AI produces a final text response after tool calling, **When** `auto_channel` is set to "discord", **Then** the final response is posted to Discord automatically.

### User Story 3 — Discord Conversational Agent (Priority: P2)

A user configures a Discord channel on their agent. When someone messages the Discord bot, it triggers an orchestration run. The AI can call functions and reply to Discord.

**Acceptance Scenarios:**

1. **Given** a Discord channel configured on an agent, **When** a user sends "What's the DOGE price?", **Then** the AI receives the message, calls the `search-price` function, and replies to Discord with the result.
2. **Given** an ongoing Discord conversation, **When** the AI needs to remember context, **Then** it uses `get_state`/`set_state` to persist conversation history.

### User Story 4 — Direct Mode Backward Compatibility (Priority: P1)

Existing schedules and webhooks continue to work without AI involvement.

**Acceptance Scenarios:**

1. **Given** existing schedules with no `orchestration_mode` set, **When** they fire, **Then** they execute the function directly as before (defaults to `direct` mode).
2. **Given** a webhook with `orchestration_mode: "direct"`, **When** a request arrives, **Then** the handler function executes directly without AI involvement.

### Edge Cases

- When the AI enters a tool-calling loop that exceeds `max_iterations`, the orchestrator stops and records a failed run with error "Max iterations exceeded".
- When the AI requests a function that doesn't exist in the namespace, the orchestrator returns a tool error "Function not found" and the AI can try a different approach.
- When the AI's configured API key is invalid, the orchestration fails immediately and records a failed run.
- When `send_to_channel` is called for a channel type not configured on the agent, the tool returns an error "Channel not configured: {type}".
- When the agent has no AI configured but a schedule has `orchestration_mode != "direct"`, the schedule falls back to `direct` mode and logs a warning.

---

## Requirements

### Functional Requirements

- **FR-001**: System MUST support three orchestration modes per schedule/webhook: `direct`, `reason_first`, `run_then_reason`. Default is `direct` for backward compatibility.
- **FR-002**: System MUST present all functions in the agent's namespace as callable tools when invoking the AI.
- **FR-003**: System MUST provide `send_to_channel`, `get_state`, and `set_state` as built-in platform tools during AI orchestration.
- **FR-004**: System MUST support tool-calling protocols for Anthropic, OpenAI-compatible, and Google AI providers.
- **FR-005**: System MUST enforce per-tier safety limits on orchestration: max iterations, max tokens, max execution time, max function calls.
- **FR-006**: System MUST record orchestration runs as AgentRun with trigger_type="ai" and a result summary of the AI's final response.
- **FR-007**: System MUST support `auto_channel` configuration to automatically route AI final responses to a channel.
- **FR-008**: System MUST implement webhook ingress in the API server to handle `{name}.agent.mcpworks.io/webhook/{path}` requests.
- **FR-009**: System MUST fall back to `direct` mode when AI is not configured, even if orchestration_mode is set.
- **FR-010**: System MUST implement Discord bot listener for channel message ingestion (server-side, Phase 1 only Discord).

### Non-Functional Requirements

- **NFR-001**: Orchestration loop must complete within tier time limits (60s/120s/300s).
- **NFR-002**: Tool definitions must be generated dynamically from namespace functions (not cached).
- **NFR-003**: AI API keys must never be logged. Orchestration logs include trigger type, function names called, iteration count, and duration — never message content or API keys.

---

## Data Model Changes

### AgentSchedule — New Fields

```python
orchestration_mode: str = "direct"  # "direct", "reason_first", "run_then_reason"
```

### AgentWebhook — New Fields

```python
orchestration_mode: str = "direct"  # "direct", "reason_first", "run_then_reason"
```

### Agent — New Fields

```python
auto_channel: str | None = None     # channel_type to auto-post AI responses to
```

### AgentRun — Enhanced Fields

No schema changes needed. Existing fields cover the new use case:
- `trigger_type = "ai"` already supported
- `trigger_detail` stores "orchestration:{schedule_id}" or "orchestration:webhook:{webhook_id}"
- `result_summary` stores AI's final text response (truncated to 1000 chars)

---

## New Modules

| Module | Purpose |
|--------|---------|
| `tasks/orchestrator.py` | Orchestration loop: trigger → AI → tool calls → channel output |
| `core/ai_client.py` (extend) | Add `chat_with_tools()` for tool-calling AI invocations |
| `core/ai_tools.py` (new) | Build tool definitions from namespace functions + platform tools |
| `api/v1/webhooks.py` (new) | Webhook ingress handler for `*.agent.mcpworks.io/webhook/*` |
| `tasks/discord_listener.py` (new) | Server-side Discord bot for channel message ingestion |

---

## Migration Path

### Database Migration

```sql
ALTER TABLE agent_schedules ADD COLUMN orchestration_mode VARCHAR(20) NOT NULL DEFAULT 'direct';
ALTER TABLE agent_webhooks ADD COLUMN orchestration_mode VARCHAR(20) NOT NULL DEFAULT 'direct';
ALTER TABLE agents ADD COLUMN auto_channel VARCHAR(20);
```

All existing rows get `orchestration_mode = 'direct'` — zero behavioral change.

### MCP Tool Changes

- `add_schedule`: Add optional `orchestration_mode` parameter (default "direct")
- `add_webhook`: Add optional `orchestration_mode` parameter (default "direct")
- `configure_agent_ai`: Add optional `auto_channel` parameter
- `describe_agent`: Include `auto_channel` in response

---

## Scope Boundaries

**In scope:**
- Server-side orchestration loop (trigger → AI → tools → channels)
- Tool-calling AI client for Anthropic, OpenAI-compatible, Google
- Auto-generation of tool definitions from namespace functions
- Built-in platform tools (send_to_channel, get_state, set_state)
- Webhook ingress handler in API server
- Discord bot listener for channel message ingestion
- Per-tier safety limits on orchestration
- Auto-channel configuration for automatic channel output
- Database migration for orchestration_mode and auto_channel fields

**Out of scope:**
- Container-side orchestration (future Phase 2)
- Multi-turn conversation memory (beyond single invocation)
- Slack/WhatsApp/email channel listeners (Phase 2 — Discord only for Phase 1)
- Streaming AI responses to channels
- Inter-agent communication
- Custom tool definitions beyond namespace functions
- AI cost tracking/billing (future)

---

## Success Criteria

- **SC-001**: A schedule with `run_then_reason` mode executes the function, passes output to AI, and AI's response is recorded — end-to-end within 30 seconds for a simple function.
- **SC-002**: AI can call at least 3 namespace functions as tools in a single orchestration run.
- **SC-003**: `send_to_channel(discord, ...)` successfully delivers a message to the configured Discord channel.
- **SC-004**: Existing `direct` mode schedules continue working with zero changes.
- **SC-005**: Webhook ingress at `{name}.agent.mcpworks.io/webhook/{path}` triggers function execution within 2 seconds.
- **SC-006**: Discord bot receives a message and triggers an AI orchestration run that can call functions and reply.
- **SC-007**: Safety limits halt runaway orchestration loops and record a clear error.

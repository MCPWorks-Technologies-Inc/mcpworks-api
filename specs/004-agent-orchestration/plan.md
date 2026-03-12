# Implementation Plan: Agent Orchestration (004-agent-orchestration)

## Phase Ordering and Dependencies

```
Phase 1: Database Migration + Model Changes (no dependencies)
    ↓
Phase 2: AI Client Extension — chat_with_tools (no code dependencies)
    ↓
Phase 3: Tool Definition Builder + Orchestrator Module (depends on Phase 2)
    ↓
Phase 4: Scheduler Integration (depends on Phase 3)
    ↓
Phase 5: Webhook Ingress + MCP Tool Changes (depends on Phase 3)
    ↓
Phase 6: Discord Listener (depends on Phase 3, P2 priority)
```

---

## Phase 1: Database Migration + Model Changes

### Migration

File: `alembic/versions/XXXX_add_orchestration_fields.py`

```sql
ALTER TABLE agent_schedules ADD COLUMN orchestration_mode VARCHAR(20) NOT NULL DEFAULT 'direct';
ALTER TABLE agent_webhooks ADD COLUMN orchestration_mode VARCHAR(20) NOT NULL DEFAULT 'direct';
ALTER TABLE agents ADD COLUMN auto_channel VARCHAR(20);
```

Constraints:
- `orchestration_mode` CHECK IN (`direct`, `reason_first`, `run_then_reason`)
- `auto_channel` CHECK IN (`discord`, `slack`, `whatsapp`, `email`) OR NULL

### Model Changes — `models/agent.py`

Add to `Agent`:
```python
auto_channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
```

Add to `AgentSchedule`:
```python
orchestration_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="direct")
```

Add to `AgentWebhook`:
```python
orchestration_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="direct")
```

Add `@validates` decorators for the new fields. Module-level constant:
```python
ORCHESTRATION_MODES = ("direct", "reason_first", "run_then_reason")
```

---

## Phase 2: AI Client Extension

### File: `core/ai_client.py`

New function alongside existing `chat()`:

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
    """Returns normalized response:
    {
        "content": [
            {"type": "text", "text": "..."},
            {"type": "tool_use", "id": str, "name": str, "input": dict}
        ],
        "stop_reason": "tool_use" | "end_turn" | "max_tokens",
        "usage": {"input_tokens": int, "output_tokens": int}
    }
    """
```

### Provider Protocol Mapping

**Anthropic** — native support:
- `tools` parameter maps directly (`name`, `description`, `input_schema`)
- Response `content` contains `tool_use` blocks natively
- Tool results: `{"type": "tool_result", "tool_use_id": ..., "content": ...}`
- `stop_reason` is already `"tool_use"` or `"end_turn"`

**OpenAI-compatible** — normalize:
- Tools format: `[{"type": "function", "function": {"name", "description", "parameters"}}]`
- Response: `choices[0].message.tool_calls` → normalize to `tool_use` content blocks
- `finish_reason: "tool_calls"` → `stop_reason: "tool_use"`
- `arguments` is JSON string, must be parsed
- Tool results: role="tool" messages with `tool_call_id`

**Google** — normalize:
- Tools format: `[{"function_declarations": [{"name", "description", "parameters"}]}]`
- Response parts: `{"functionCall": {"name", "args"}}` → normalize to `tool_use` blocks
- Tool results: `{"functionResponse": {"name", "response"}}` parts with role="function"

All three normalize to the same output format — orchestrator is provider-agnostic.

---

## Phase 3: Tool Definition Builder + Orchestrator

### New File: `core/ai_tools.py`

```python
PLATFORM_TOOLS = [send_to_channel, get_state, set_state]  # defined in spec

async def build_tool_definitions(
    namespace_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """Query all functions in namespace via FunctionService.list_all_for_namespace().

    Tool name format: "{service_name}__{function_name}" (double underscore separator).
    Returns namespace function tools + PLATFORM_TOOLS.
    """
```

Uses `FunctionService.list_all_for_namespace()` (function.py line 456).

### New File: `tasks/orchestrator.py`

```python
@dataclass
class OrchestrationResult:
    success: bool
    final_text: str | None
    functions_called: list[str]
    iterations: int
    total_tokens: int
    duration_ms: int
    error: str | None = None

ORCHESTRATION_TIER_LIMITS = {
    "builder-agent":     {"max_iterations": 5,  "max_tokens": 50_000,    "max_seconds": 60,  "max_functions": 3},
    "pro-agent":         {"max_iterations": 10, "max_tokens": 200_000,   "max_seconds": 120, "max_functions": 10},
    "enterprise-agent":  {"max_iterations": 25, "max_tokens": 1_000_000, "max_seconds": 300, "max_functions": 25},
}

async def run_orchestration(
    agent: Agent,
    trigger_type: str,
    trigger_context: str,
    trigger_data: dict,
    tier: str,
) -> OrchestrationResult:
```

### Orchestration Loop Algorithm

1. **Setup**: Get tier limits. Build tool definitions. Decrypt AI API key. Start timer.
2. **Initial message**: `[{"role": "user", "content": trigger_context}]`
3. **Loop** (up to max_iterations):
   a. Call `chat_with_tools(engine, model, api_key, messages, tools, system_prompt)`
   b. If `stop_reason == "end_turn"`: extract final text, break
   c. If `stop_reason == "tool_use"`: for each tool call:
      - **Platform tool** (`send_to_channel`/`get_state`/`set_state`): delegate to AgentService
      - **Namespace function** (`{service}__{function}`): execute via sandbox backend
      - **Unknown**: return error "Function not found"
   d. Append assistant message + tool results to conversation
   e. Check safety limits (iterations, tokens, time, function count)
4. **Post-loop**: If `auto_channel` set, send final text. Record AgentRun. Return result.

### Safety Enforcement

Limits checked **before** each AI call (prevent runaway costs):
- iterations >= max → stop with "Max iterations exceeded"
- total_tokens >= max → stop with "Token limit exceeded"
- elapsed >= max_seconds → stop with "Execution time limit exceeded"
- functions_called >= max → stop with "Function call limit exceeded"

### Per-Agent Concurrency Lock

Redis-based lock (`agent:{id}:orchestration`) prevents two orchestration runs from colliding on the same agent's state.

---

## Phase 4: Scheduler Integration

### File: `tasks/scheduler.py`

Modify `_execute_scheduled_function` to branch on `schedule.orchestration_mode`:

```python
orch_mode = schedule.orchestration_mode or "direct"

# FR-009: Fall back to direct if AI not configured
if orch_mode != "direct" and not agent.ai_engine:
    logger.warning("schedule_ai_fallback_direct", ...)
    orch_mode = "direct"

if orch_mode == "direct":
    # Existing code path — unchanged
    ...
elif orch_mode == "run_then_reason":
    # 1. Execute function directly
    result = await _execute_function_direct(schedule, agent)
    # 2. Pass output to orchestrator
    trigger_context = f"Scheduled execution of {schedule.function_name}. Output: {result}"
    await run_orchestration(agent, "cron", trigger_context, {...}, tier)
elif orch_mode == "reason_first":
    trigger_context = f"Scheduled trigger for {schedule.function_name}. Decide what to do."
    await run_orchestration(agent, "cron", trigger_context, {...}, tier)
```

Refactor: extract existing execution logic into `_execute_function_direct()` helper.

---

## Phase 5: Webhook Ingress + MCP Tool Changes

### New Route: Webhook Ingress

Register at root level (not `/v1/`): `POST /webhook/{path:path}`

Only active when `request.state.endpoint_type == "agent"` (from SubdomainMiddleware).

Flow:
1. Extract agent_name from `request.state.namespace`
2. Resolve webhook via `AgentService.resolve_webhook(agent_name, path)`
3. Validate HMAC if `secret_hash` set
4. Branch on `webhook.orchestration_mode` (same pattern as scheduler)
5. Return 200 with result

### MCP Tool Changes — `create_handler.py`

| Tool | Change |
|------|--------|
| `add_schedule` | Add optional `orchestration_mode` param (default "direct") |
| `add_webhook` | Add optional `orchestration_mode` param (default "direct") |
| `configure_agent_ai` | Add optional `auto_channel` param |
| `describe_agent` | Include `auto_channel` in response |
| `list_schedules` | Include `orchestration_mode` per schedule |
| `list_webhooks` | Include `orchestration_mode` per webhook |
| `clone_agent` | Copy `auto_channel` and `orchestration_mode` values |

### AgentService Changes — `agent_service.py`

- `add_schedule()`: Add `orchestration_mode` param, set on model
- `add_webhook()`: Add `orchestration_mode` param, set on model
- `configure_ai()`: Add `auto_channel` param, set on agent
- `clone_agent()`: Copy new fields

---

## Phase 6: Discord Listener (P2)

### New File: `tasks/discord_listener.py`

Server-side Discord bot using `discord.py` (already in deps).

Architecture:
- Per-agent bot tokens (stored encrypted in channel config, not platform-wide)
- On startup: query all agents with `channel_type="discord"` and `enabled=True`
- Maintain mapping: `discord_channel_id → (agent_id, account_id)`
- On message: trigger `run_orchestration(agent, "channel", ...)`

### Lifespan Integration — `main.py`

```python
discord_task = asyncio.create_task(run_discord_listener())
```

Gated behind `DISCORD_BOT_ENABLED` setting (default False).

### Channel Output via `send_to_channel`

Phase 1: Discord via webhook URL (stored in channel config).
- POST `{"content": message[:2000]}` to Discord webhook URL
- Uses httpx

---

## Testing Strategy

### Unit Tests (no external deps)

| Test File | What |
|-----------|------|
| `test_ai_tools.py` | `build_tool_definitions` with mock FunctionService |
| `test_orchestrator.py` | Orchestration loop with mocked `chat_with_tools` — modes, limits, errors |
| `test_ai_client_tools.py` | Response normalization per provider (mock httpx) |
| `test_webhook_ingress.py` | Path resolution, HMAC validation, mode dispatch |
| `test_scheduler_orchestration.py` | Direct/run_then_reason/reason_first flows, AI fallback |

### Mocking Strategy

```python
@pytest.fixture
def mock_chat_with_tools(monkeypatch):
    responses = []  # Queue of canned responses
    async def fake(*args, **kwargs):
        return responses.pop(0)
    monkeypatch.setattr("mcpworks_api.core.ai_client.chat_with_tools", fake)
    return responses
```

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Runaway AI costs from infinite loops | High | Per-tier safety limits enforced before each AI call |
| AI API key exposure in logs | Critical | structlog strip processor + explicit scrubbing in orchestrator |
| Slow orchestration blocks scheduler | Medium | Own DB session, scheduler semaphore (MAX_CONCURRENT=5) |
| Concurrent orchestration on same agent | Medium | Redis-based per-agent lock |
| Migration breaks existing schedules | Low | All defaults are `'direct'`, zero behavioral change |
| Webhook ingress DDoS | Medium | Existing rate limiting + per-agent webhook rate limit |
| State explosion from AI set_state | Low | Existing tier-based size limits apply |

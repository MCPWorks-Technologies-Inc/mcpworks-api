# Tasks: Agent Orchestration (004-agent-orchestration)

## Phase 1: Database Migration + Model Changes

### Task 1.1: Add orchestration columns to models
**File:** `src/mcpworks_api/models/agent.py`
**Depends on:** nothing

- Add `ORCHESTRATION_MODES = ("direct", "reason_first", "run_then_reason")` constant
- Add `orchestration_mode` column to `AgentSchedule` (String(20), default="direct", NOT NULL)
- Add `orchestration_mode` column to `AgentWebhook` (String(20), default="direct", NOT NULL)
- Add `auto_channel` column to `Agent` (String(20), nullable)
- Add `@validates("orchestration_mode")` to both `AgentSchedule` and `AgentWebhook`
- Add `@validates("auto_channel")` to `Agent` (must be valid channel type or None)

### Task 1.2: Create Alembic migration
**Depends on:** Task 1.1

- Generate migration: `alembic revision --autogenerate -m "add orchestration mode and auto channel"`
- Verify: all existing rows get `orchestration_mode = 'direct'`, `auto_channel = NULL`
- Test: `alembic upgrade head` + `alembic downgrade -1` round-trip

---

## Phase 2: AI Client Extension

### Task 2.1: Implement `chat_with_tools` for Anthropic
**File:** `src/mcpworks_api/core/ai_client.py`
**Depends on:** nothing

- Add `async def chat_with_tools(engine, model, api_key, messages, tools, system_prompt, max_tokens) -> dict`
- Implement `_chat_with_tools_anthropic()`:
  - POST to `https://api.anthropic.com/v1/messages` with `tools` parameter
  - Return normalized response: `{content: [...], stop_reason: str, usage: {input_tokens, output_tokens}}`
  - Content blocks: `{"type": "text", "text": ...}` and `{"type": "tool_use", "id": ..., "name": ..., "input": ...}`

### Task 2.2: Implement `chat_with_tools` for OpenAI-compatible
**File:** `src/mcpworks_api/core/ai_client.py`
**Depends on:** Task 2.1 (shared normalize format)

- Implement `_chat_with_tools_openai(api_key, base_url, model, messages, tools, system_prompt, max_tokens)`:
  - Convert tools to OpenAI format: `[{"type": "function", "function": {"name", "description", "parameters"}}]`
  - Convert messages: tool_result → role="tool" with `tool_call_id`
  - Parse `choices[0].message.tool_calls` → normalize to `tool_use` content blocks
  - Parse `arguments` JSON string to dict
  - Map `finish_reason: "tool_calls"` → `stop_reason: "tool_use"`
  - Map usage: `prompt_tokens` → `input_tokens`, `completion_tokens` → `output_tokens`

### Task 2.3: Implement `chat_with_tools` for Google
**File:** `src/mcpworks_api/core/ai_client.py`
**Depends on:** Task 2.1 (shared normalize format)

- Implement `_chat_with_tools_google(api_key, model, messages, tools, system_prompt)`:
  - Convert tools to Google format: `[{"function_declarations": [...]}]`
  - Convert messages: tool_result → `{"functionResponse": {"name", "response"}}` parts
  - Parse `functionCall` parts → normalize to `tool_use` content blocks
  - Map usage from `usageMetadata`

### Task 2.4: Add routing in `chat_with_tools`
**File:** `src/mcpworks_api/core/ai_client.py`
**Depends on:** Tasks 2.1, 2.2, 2.3

- Route by engine to appropriate implementation (same pattern as existing `chat()`)
- Handle tool_result message format conversion per-provider before passing to implementations

---

## Phase 3: Tool Definition Builder + Orchestrator

### Task 3.1: Create tool definition builder
**File:** `src/mcpworks_api/core/ai_tools.py` (new)
**Depends on:** nothing

- Define `PLATFORM_TOOLS` list (send_to_channel, get_state, set_state) with input_schema
- Implement `async def build_tool_definitions(namespace_id, db) -> list[dict]`:
  - Query functions via `FunctionService(db).list_all_for_namespace(namespace_id)`
  - For each (function, version): generate `{"name": "{svc}__{fn}", "description": ..., "input_schema": ...}`
  - Double-underscore separator to avoid collision with hyphenated names
  - Append PLATFORM_TOOLS
  - Return combined list
- Implement `parse_tool_name(tool_name) -> tuple[str, str] | None`:
  - Split on `__`, return (service_name, function_name) or None if platform tool

### Task 3.2: Implement platform tool executor
**File:** `src/mcpworks_api/tasks/orchestrator.py` (new)
**Depends on:** Task 3.1

- Implement `async def _execute_platform_tool(tool_name, tool_input, agent, account_id, tier, db) -> str`:
  - `send_to_channel`: look up AgentChannel, decrypt config, POST to Discord webhook URL via httpx
  - `get_state`: call `AgentService(db).get_state()`, return JSON value
  - `set_state`: call `AgentService(db).set_state()`, return confirmation
  - Unknown tool: return error string

### Task 3.3: Implement namespace function executor
**File:** `src/mcpworks_api/tasks/orchestrator.py`
**Depends on:** Task 3.1

- Implement `async def _execute_namespace_function(service_name, function_name, input_data, namespace_id, account, db) -> str`:
  - Get function via `FunctionService(db).get_for_execution(namespace_id, service_name, function_name)`
  - Get backend via `get_backend(version.backend)`
  - Execute via `backend.execute(code, config, input_data, account, execution_id)`
  - Return `json.dumps(result.output)` or error string

### Task 3.4: Implement orchestration loop
**File:** `src/mcpworks_api/tasks/orchestrator.py`
**Depends on:** Tasks 2.4, 3.1, 3.2, 3.3

- Define `OrchestrationResult` dataclass
- Define `ORCHESTRATION_TIER_LIMITS` dict
- Implement `async def run_orchestration(agent, trigger_type, trigger_context, trigger_data, tier) -> OrchestrationResult`:
  - Setup: get limits, build tools, decrypt API key, start timer
  - Message construction: `[{"role": "user", "content": trigger_context}]`
  - Loop: call `chat_with_tools` → parse response → dispatch tools → append results
  - Safety checks before each AI call (iterations, tokens, time, function count)
  - Post-loop: auto_channel routing, AgentRun recording
  - Error handling: AIClientError → immediate fail, tool errors → feed back to AI
- Add Redis-based per-agent concurrency lock

### Task 3.5: Implement auto-channel routing
**File:** `src/mcpworks_api/tasks/orchestrator.py`
**Depends on:** Task 3.2

- After orchestration completes with a final text response:
  - If `agent.auto_channel` is set, call `_execute_platform_tool("send_to_channel", ...)`
  - Log success/failure but don't fail the orchestration if channel send fails

---

## Phase 4: Scheduler Integration

### Task 4.1: Refactor scheduler for orchestration modes
**File:** `src/mcpworks_api/tasks/scheduler.py`
**Depends on:** Task 3.4

- Extract existing function execution logic into `_execute_function_direct(schedule, agent) -> ExecutionResult`
- Modify `_execute_scheduled_function` to check `schedule.orchestration_mode`:
  - `direct`: call `_execute_function_direct` (existing behavior)
  - `run_then_reason`: call `_execute_function_direct`, then `run_orchestration` with output as context
  - `reason_first`: call `run_orchestration` with trigger description as context
- Add FR-009 fallback: if AI not configured, log warning and use `direct` mode
- Get account tier for orchestration limits (reuse existing account lookup)

---

## Phase 5: Webhook Ingress + MCP Tool Changes

### Task 5.1: Implement webhook ingress handler
**File:** `src/mcpworks_api/api/v1/webhooks.py` (new)
**Depends on:** Task 3.4

- Create `router = APIRouter()`
- Implement `POST /webhook/{path:path}`:
  - Extract agent_name from `request.state.namespace`
  - Resolve webhook via `AgentService.resolve_webhook(agent_name, path)`
  - Check agent status (must be "running")
  - Validate HMAC if `secret_hash` set (X-Webhook-Signature header)
  - Branch on `webhook.orchestration_mode`:
    - `direct`: execute handler function via sandbox
    - `reason_first`: orchestrate with payload as context
    - `run_then_reason`: execute handler, orchestrate with result
  - Record AgentRun with trigger_type="webhook"
  - Return 200 with result

### Task 5.2: Register webhook route
**File:** `src/mcpworks_api/main.py`
**Depends on:** Task 5.1

- Import webhook router
- Register at root level (not under `/v1/`): `app.include_router(webhook_router)`
- Ensure MCPTransportMiddleware doesn't intercept `/webhook/` paths

### Task 5.3: Update MCP tool definitions — add_schedule
**File:** `src/mcpworks_api/mcp/create_handler.py`
**Depends on:** Task 1.1

- Add `orchestration_mode` to `add_schedule` tool input_schema (optional, default "direct")
- Update `_add_schedule` handler to pass `orchestration_mode` to AgentService
- Update `list_schedules` response to include `orchestration_mode`

### Task 5.4: Update MCP tool definitions — add_webhook
**File:** `src/mcpworks_api/mcp/create_handler.py`
**Depends on:** Task 1.1

- Add `orchestration_mode` to `add_webhook` tool input_schema (optional, default "direct")
- Update `_add_webhook` handler to pass `orchestration_mode` to AgentService
- Update `list_webhooks` response to include `orchestration_mode`

### Task 5.5: Update MCP tool definitions — configure_agent_ai + describe_agent
**File:** `src/mcpworks_api/mcp/create_handler.py`
**Depends on:** Task 1.1

- Add `auto_channel` to `configure_agent_ai` tool input_schema (optional)
- Update `_configure_agent_ai` handler to pass `auto_channel` to AgentService
- Update `describe_agent` response to include `auto_channel`

### Task 5.6: Update AgentService for new fields
**File:** `src/mcpworks_api/services/agent_service.py`
**Depends on:** Task 1.1

- `add_schedule()`: add `orchestration_mode` param, set on model
- `add_webhook()`: add `orchestration_mode` param, set on model
- `configure_ai()`: add `auto_channel` param, set on agent
- `clone_agent()`: copy `auto_channel`, `orchestration_mode` fields

---

## Phase 6: Discord Listener (P2)

### Task 6.1: Implement Discord bot listener
**File:** `src/mcpworks_api/tasks/discord_listener.py` (new)
**Depends on:** Task 3.4

- Implement `async def run_discord_listener() -> None`:
  - Query all agents with `channel_type="discord"` and `enabled=True`
  - Decrypt channel configs to get bot tokens
  - Group agents by bot token (multiple agents may share a token)
  - For each unique bot token: create a `discord.Client` and connect
  - On message (not from bot): look up agent, call `run_orchestration(trigger_type="channel")`
  - Periodic re-sync: poll for new/removed channels every 60s
- Add `DISCORD_BOT_ENABLED` to settings (default False)

### Task 6.2: Wire Discord listener into lifespan
**File:** `src/mcpworks_api/main.py`
**Depends on:** Task 6.1

- Add `discord_task = asyncio.create_task(run_discord_listener())` to lifespan
- Gate behind `settings.discord_bot_enabled`
- Cancel on shutdown (same pattern as scheduler)

---

## Phase 7: Tests

### Task 7.1: Unit test — tool definition builder
**File:** `tests/unit/test_ai_tools.py` (new)
**Depends on:** Task 3.1

- Test tool name format: `{service}__{function}`
- Test input_schema mapping from function versions
- Test platform tools are always included
- Test empty namespace (only platform tools)

### Task 7.2: Unit test — AI client chat_with_tools
**File:** `tests/unit/test_ai_client_tools.py` (new)
**Depends on:** Task 2.4

- Mock httpx responses for each provider
- Test Anthropic tool_use response normalization
- Test OpenAI tool_calls response normalization (including JSON string parsing)
- Test Google functionCall response normalization
- Test error handling per provider

### Task 7.3: Unit test — orchestrator
**File:** `tests/unit/test_orchestrator.py` (new)
**Depends on:** Task 3.4

- Mock `chat_with_tools` with canned response queues
- Test single text response (no tool use)
- Test one tool call then text response
- Test multiple sequential tool calls
- Test max_iterations limit enforcement
- Test max_tokens limit enforcement
- Test max_seconds timeout enforcement
- Test max_functions limit enforcement
- Test fallback to direct when AI not configured
- Test platform tool dispatch (get_state, set_state, send_to_channel)
- Test namespace function dispatch
- Test unknown function error handling
- Test auto_channel routing
- Test per-agent concurrency lock

### Task 7.4: Unit test — scheduler orchestration
**File:** `tests/unit/test_scheduler_orchestration.py` (new)
**Depends on:** Task 4.1

- Test direct mode unchanged
- Test run_then_reason flow (function first, then orchestration)
- Test reason_first flow (orchestration only)
- Test FR-009 fallback (no AI → direct mode with warning)

### Task 7.5: Unit test — webhook ingress
**File:** `tests/unit/test_webhook_ingress.py` (new)
**Depends on:** Task 5.1

- Test path resolution
- Test HMAC validation (valid/invalid/missing)
- Test orchestration mode dispatch
- Test stopped agent rejection
- Test unknown path 404

---

## Implementation Order (recommended)

```
1.1 → 1.2 → 2.1 → 2.2 → 2.3 → 2.4 → 3.1 → 3.2 → 3.3 → 3.4 → 3.5
                                                                    ↓
                                                              4.1 + 5.6
                                                                    ↓
                                                        5.1 → 5.2 + 5.3 + 5.4 + 5.5
                                                                    ↓
                                                              6.1 → 6.2
                                                                    ↓
                                                    7.1 + 7.2 + 7.3 + 7.4 + 7.5
```

Total: 24 tasks across 7 phases.

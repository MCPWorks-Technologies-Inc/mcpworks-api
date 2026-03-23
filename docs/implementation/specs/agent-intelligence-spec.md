# Agent Intelligence Enhancements - Specification

**Version:** 1.0.0
**Created:** 2026-03-20
**Status:** Approved
**Spec Author:** Simon Carr + Claude
**Origin:** OpenClaw architecture analysis

---

## 1. Overview

### 1.1 Purpose

Four enhancements to the agent orchestration system that make agents smarter, more autonomous, and more observable. These close the remaining gaps between mcpworks agents and leading autonomous agent harnesses (OpenClaw), while maintaining our "sniper agent" advantage.

### 1.2 User Value

- Agents that remember conversations across runs (no amnesia)
- Agents that program their own future behavior via heartbeat
- Agents that can search their own state without knowing exact keys
- Operators who can monitor context health and prevent performance degradation

### 1.3 Success Criteria

- [ ] Heartbeat runs inject `__heartbeat_instructions__` into trigger context
- [ ] Conversation history persists in state and is injected on chat/orchestration
- [ ] Compaction summarizes history when token threshold is exceeded
- [ ] `search_state` and `list_state_keys` platform tools available during orchestration
- [ ] `context_tokens` field reported in telemetry and orchestration results
- [ ] All features respect existing tier limits (state size, token caps)

### 1.4 Scope

**In Scope:**
- Feature 1: Self-programming heartbeat via `__heartbeat_instructions__`
- Feature 2: Conversation memory with LLM-driven compaction
- Feature 3: `search_state` and `list_state_keys` platform tools
- Feature 4: Context budget tracking and telemetry

**Out of Scope:**
- Vector/embedding-based semantic search (future — simple keyword matching for now)
- Agent self-scheduling via platform tools (future spec)
- Cross-agent memory sharing

---

## 2. Feature 1: Self-Programming Heartbeat

### 2.1 Concept

The agent can write to `__heartbeat_instructions__` via `set_state`. On the next heartbeat tick, those instructions are injected into the trigger context alongside `__soul__` and `__goals__`. This lets the agent program its own future behavior.

### 2.2 Changes

**File:** `src/mcpworks_api/tasks/scheduler.py` — `_execute_heartbeat()`

Current trigger context construction (lines 342-350):
```python
trigger_context = "Heartbeat tick. You are waking up on your configured interval.\n"
if soul:
    trigger_context += f"\nYour soul:\n{soul}\n"
if goals:
    trigger_context += f"\nYour current goals:\n{goals}\n"
trigger_context += (
    "\nReview your state and decide if any actions are needed. "
    "If nothing needs doing, respond briefly that all is well."
)
```

New trigger context construction:
```python
trigger_context = "Heartbeat tick. You are waking up on your configured interval.\n"
if soul:
    trigger_context += f"\nYour identity:\n{soul}\n"
if goals:
    trigger_context += f"\nYour current goals:\n{goals}\n"

instructions = agent_state.get("__heartbeat_instructions__", "")
if instructions:
    trigger_context += f"\nYour instructions for this heartbeat:\n{instructions}\n"

trigger_context += (
    "\nReview your state and instructions, then decide what actions to take. "
    "You can update __heartbeat_instructions__ via set_state to change "
    "what you do on your next heartbeat. "
    "If nothing needs doing, respond briefly that all is well."
)
```

**No schema changes.** Uses existing `set_state` platform tool and `AgentState` model.

### 2.3 Behavior

- Agent sets `__heartbeat_instructions__` to `"Check GitHub for new issues and post summary to #general"`
- Next heartbeat fires → instructions injected into trigger context
- Agent acts on instructions, optionally updates them for next time
- Agent can clear instructions by setting to `""` or deleting the key
- If key doesn't exist, heartbeat works exactly as it does today (backward compatible)

---

## 3. Feature 2: Conversation Memory with Compaction

### 3.1 Concept

Agents persist conversation turns in state key `__conversation_history__`. Before each chat or orchestration run, recent history is loaded and injected as context. When token count exceeds a threshold, the oldest portion is summarized by the LLM and replaced with a compact summary.

### 3.2 Data Model

**State key:** `__conversation_history__`
**Format:**
```json
{
  "turns": [
    {"role": "user", "content": "...", "ts": "2026-03-20T10:00:00Z", "trigger": "chat"},
    {"role": "assistant", "content": "...", "ts": "2026-03-20T10:00:05Z"},
    {"role": "user", "content": "...", "ts": "2026-03-20T11:00:00Z", "trigger": "heartbeat"}
  ],
  "summary": "Previously: User asked about GitHub issues. Agent found 3 new issues and posted summary to Discord.",
  "compacted_at": "2026-03-20T09:00:00Z"
}
```

### 3.3 New Module

**File:** `src/mcpworks_api/core/conversation_memory.py`

```python
"""Conversation memory: persist, load, and compact conversation history."""

MAX_HISTORY_TURNS = 50          # Hard cap on stored turns
COMPACTION_TURN_THRESHOLD = 30  # Compact when turns exceed this
COMPACTION_KEEP_RECENT = 10     # Keep this many recent turns verbatim after compaction
MAX_HISTORY_CHARS = 50_000      # Hard cap on total chars in history
SUMMARY_MAX_CHARS = 2_000       # Max chars for compacted summary

async def load_history(agent_state: dict) -> tuple[str | None, list[dict]]:
    """Load summary + recent turns from agent state.

    Returns (summary, recent_turns).
    """

async def append_turn(
    agent_id: UUID,
    account_id: UUID,
    agent_name: str,
    role: str,
    content: str,
    tier: str,
    trigger: str = "chat",
) -> None:
    """Append a conversation turn to persistent state."""

async def compact_history(
    agent: Agent,
    api_key: str,
    agent_state: dict,
    tier: str,
) -> None:
    """Summarize older turns via LLM, keep recent turns verbatim."""
```

### 3.4 Integration Points

**In `chat_with_agent()` (agent_service.py):**
1. After loading agent state, call `load_history(agent_state)` → get (summary, turns)
2. Prepend summary as a system message: `"Previous conversation summary: {summary}"`
3. Prepend recent turns before current message
4. After response, call `append_turn()` for both user message and assistant response
5. If turns exceed `COMPACTION_TURN_THRESHOLD`, run `compact_history()` asynchronously

**In `run_orchestration()` (orchestrator.py):**
1. Same load_history pattern — inject summary + recent turns into messages
2. After orchestration completes, append a single turn summarizing what happened
3. Skip compaction during orchestration (runs are usually short)

**In `_execute_heartbeat()` (scheduler.py):**
1. Load history → inject summary (not full turns — heartbeats should be lightweight)
2. After heartbeat, append a brief turn: `{"role": "assistant", "content": result_summary, "trigger": "heartbeat"}`

### 3.5 Compaction Algorithm

```
1. Load __conversation_history__ from state
2. If len(turns) < COMPACTION_TURN_THRESHOLD: return (no-op)
3. Split: old_turns = turns[:-COMPACTION_KEEP_RECENT], keep_turns = turns[-COMPACTION_KEEP_RECENT:]
4. Build compaction prompt:
   "Summarize this conversation history in under 500 words.
    Focus on: decisions made, tasks completed, current state of work,
    and anything the agent should remember going forward."
   + existing summary (if any)
   + old_turns formatted as conversation
5. Call chat() (simple, no tools) with agent's AI engine
6. Store: {"turns": keep_turns, "summary": new_summary, "compacted_at": now}
7. Save to __conversation_history__ via set_state
```

### 3.6 Token Budget

- Summary: ~500 tokens max
- Recent turns (10): ~1000-2000 tokens depending on content
- Total context injection: ~1500-2500 tokens
- This stays well within the sniper agent philosophy

### 3.7 Tier Enforcement

History uses regular `AgentState` storage, so existing tier-based size limits apply:
- trial-agent: 10MB state → ~10MB of conversation history possible
- dedicated-agent: 1GB state → effectively unlimited

No new tier limits needed.

---

## 4. Feature 3: State Search Platform Tools

### 4.1 New Platform Tools

**`list_state_keys`** — List all state keys with sizes
```json
{
    "name": "list_state_keys",
    "description": "List all keys in persistent agent state with their sizes",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}
```

Response:
```json
{
    "keys": ["__soul__", "__goals__", "github_issues", "last_check"],
    "count": 4,
    "total_size_bytes": 2048
}
```

**`search_state`** — Keyword search across state keys and values
```json
{
    "name": "search_state",
    "description": "Search persistent agent state by keyword. Matches against key names and string values.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keyword (case-insensitive substring match)"
            }
        },
        "required": ["query"]
    }
}
```

Response:
```json
{
    "matches": [
        {"key": "github_issues", "preview": "3 open issues: #42 fix login bug, #43 add..."},
        {"key": "__goals__", "preview": "...monitor GitHub issues and report..."}
    ],
    "query": "github",
    "total_searched": 4
}
```

### 4.2 Implementation

**File:** `src/mcpworks_api/core/ai_tools.py`

Add to `PLATFORM_TOOLS` list:
```python
{
    "name": "list_state_keys",
    "description": "List all keys in persistent agent state with their sizes",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
},
{
    "name": "search_state",
    "description": "Search persistent agent state by keyword. Matches against key names and string values.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keyword (case-insensitive substring match)",
            },
        },
        "required": ["query"],
    },
},
```

**File:** `src/mcpworks_api/tasks/orchestrator.py` — `_execute_platform_tool()`

Add handlers:
```python
elif tool_name == "list_state_keys":
    async with get_db_context() as db:
        service = AgentService(db)
        keys_info = await service.list_state_keys(account.id, agent.name, tier)
        return json.dumps({
            "keys": keys_info["keys"],
            "count": len(keys_info["keys"]),
            "total_size_bytes": keys_info["total_size_bytes"],
        })

elif tool_name == "search_state":
    query = tool_input.get("query", "").lower()
    if not query:
        return json.dumps({"error": "query is required"})
    matches = []
    # agent_state is already loaded and decrypted at orchestration start
    for key, value in (agent_state or {}).items():
        value_str = json.dumps(value, default=str) if not isinstance(value, str) else value
        if query in key.lower() or query in value_str.lower():
            preview = value_str[:100] + ("..." if len(value_str) > 100 else "")
            matches.append({"key": key, "preview": preview})
    return json.dumps({
        "matches": matches[:20],
        "query": query,
        "total_searched": len(agent_state or {}),
    })
```

### 4.3 Permissions

- `list_state_keys`: Available in all contexts (chat, heartbeat, cron, webhook)
- `search_state`: Available in all contexts
- Both added to `PUBLIC_SAFE_PLATFORM_TOOLS` (read-only, no mutation)

---

## 5. Feature 4: Context Budget Monitoring

### 5.1 Concept

Track the estimated token count of the context sent to the LLM on each orchestration call. Report it in telemetry and log warnings when context exceeds thresholds.

### 5.2 Token Estimation

Simple heuristic: `estimated_tokens = len(text) / 4` (standard approximation for English text with code).

Applied to:
- System prompt (base + augmented tool list)
- Conversation history (summary + recent turns)
- Tool definitions (JSON serialized)
- Current messages

### 5.3 Implementation

**File:** `src/mcpworks_api/core/context_budget.py`

```python
"""Context budget estimation and monitoring."""

import json

# Thresholds (estimated tokens)
CONTEXT_GREEN = 4_000      # Healthy
CONTEXT_YELLOW = 8_000     # Watch
CONTEXT_ORANGE = 16_000    # Warning
CONTEXT_RED = 32_000       # Danger — performance degradation likely

def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English/code mix."""
    return len(text) // 4

def estimate_context_budget(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
) -> dict:
    """Estimate total context tokens and return budget report."""
    prompt_tokens = estimate_tokens(system_prompt)

    messages_text = json.dumps(messages, default=str)
    messages_tokens = estimate_tokens(messages_text)

    tools_text = json.dumps(tools, default=str)
    tools_tokens = estimate_tokens(tools_text)

    total = prompt_tokens + messages_tokens + tools_tokens

    if total < CONTEXT_GREEN:
        level = "green"
    elif total < CONTEXT_YELLOW:
        level = "yellow"
    elif total < CONTEXT_ORANGE:
        level = "orange"
    else:
        level = "red"

    return {
        "total_estimated_tokens": total,
        "breakdown": {
            "system_prompt": prompt_tokens,
            "messages": messages_tokens,
            "tools": tools_tokens,
        },
        "level": level,
    }
```

### 5.4 Integration

**In `run_orchestration()` — before first AI call:**
```python
budget = estimate_context_budget(effective_system_prompt, messages, tools)
_emit("context_budget", **budget)

if budget["level"] in ("orange", "red"):
    logger.warning(
        "orchestration_context_budget_high",
        agent_name=agent.name,
        level=budget["level"],
        total_tokens=budget["total_estimated_tokens"],
    )
```

**In `OrchestrationResult`:**
```python
@dataclass
class OrchestrationResult:
    ...
    context_tokens: int = 0  # New field
```

**In telemetry events:**
- New event type: `context_budget` with `total_estimated_tokens`, `breakdown`, `level`
- Emitted once at orchestration start

**In `describe_agent` MCP tool response:**
- Add `context_health: "green"` (or yellow/orange/red) based on last known budget
- This lets external MCP clients see agent health at a glance

---

## 6. Implementation Order

### Phase 1 (smallest delta, biggest impact)

1. **Self-programming heartbeat** — ~20 lines changed in `scheduler.py`
2. **State search tools** — ~60 lines in `ai_tools.py` + `orchestrator.py`

### Phase 2 (larger, depends on Phase 1 working)

3. **Context budget monitoring** — new module + integration in orchestrator
4. **Conversation memory** — new module + integration in chat/orchestrator/scheduler

### Rationale

Phase 1 changes are additive and zero-risk (backward compatible, no schema changes). Phase 2 introduces a new module and touches more code paths.

---

## 7. Testing Requirements

### 7.1 Unit Tests

- `test_heartbeat_instructions_injected` — verify `__heartbeat_instructions__` appears in trigger context
- `test_heartbeat_no_instructions` — backward compat when key doesn't exist
- `test_search_state_matches` — keyword matching across keys and values
- `test_search_state_case_insensitive` — case insensitivity
- `test_search_state_empty_query` — error response
- `test_list_state_keys_response_format` — correct JSON shape
- `test_context_budget_estimation` — token estimates in correct range
- `test_context_budget_levels` — green/yellow/orange/red thresholds
- `test_conversation_memory_load` — loads summary + recent turns
- `test_conversation_memory_append` — appends turn correctly
- `test_conversation_memory_compaction` — reduces turns, produces summary

### 7.2 Integration Tests

- `test_heartbeat_with_instructions_e2e` — full heartbeat cycle with instructions set
- `test_chat_with_history` — multi-turn chat preserves history
- `test_orchestration_with_search_state` — AI uses search_state tool successfully

---

## 8. Approval

**Status:** Approved

**Approvals:**
- [x] CTO (Simon Carr) — 2026-03-20

---

## Changelog

**v1.0.0 (2026-03-20):**
- Initial spec: 4 features from OpenClaw analysis
- Approved for implementation

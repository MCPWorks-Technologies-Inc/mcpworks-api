# Research: Fix Procedure Step Execution & Conversation Memory

**Feature**: 017-fix-procedure-execution
**Date**: 2026-04-01

## R-001: Why procedure steps fail

### Root Cause Analysis

Examined production logs from 2026-04-01 for procedure `post-bluesky-single` and `post-bluesky-thread`. Both fail at step 1 with `procedure_step_failed` after exhausting all retries.

**Three contributing factors identified:**

1. **Tool overload**: The step AI receives all 36+ namespace tools. It must select `social__post-to-bluesky` from a list of 36 tools. Even when told "you MUST call `social__post-to-bluesky`", the AI sometimes responds with text instead of a tool call (stop_reason=`end_turn` instead of `tool_use`).

2. **Context as raw JSON**: `accumulated_context` is dumped via `json.dumps()` and injected into the system prompt. The AI sees `{"input": {"text": "..."}}` and must figure out that "text" in the input maps to the "text" parameter of `post-to-bluesky`. With nested step results this gets worse.

3. **Missing schema**: The AI doesn't know the function's parameter names. It sees the tool definition in the tools array, but the system prompt doesn't reinforce what parameters are expected.

### Decision

Apply all three fixes simultaneously — they are independent and each improves success rate:
- Single-tool presentation (eliminates selection confusion)
- Structured context variables (eliminates JSON parsing)
- Schema in system prompt (eliminates parameter guessing)

### Evidence

The `post-bluesky-single` procedure worked successfully when the outer chat AI called `post-to-bluesky` directly (single tool in mind, clear parameters from user message). The difference: the chat AI had user intent in natural language + knew the function schema from the tool definition. The procedure step AI had neither.

## R-002: Conversation memory compaction failure

### Root Cause

`conversation_memory.py` line 186:
```python
await chat(engine=..., model=..., api_key=..., messages=[...], system_prompt=...)
```

`ai_client.py` line 43:
```python
async def chat(engine, model, api_key, message: str, system_prompt=None, max_tokens=4096)
```

`messages` is not a valid parameter. Should be `message` (singular, string type).

### Decision

One-line fix: `messages=[{"role": "user", "content": compaction_prompt}]` → `message=compaction_prompt`

### Impact

This error fires on every agent interaction (visible in production logs as `conversation_memory_compaction_failed`). It's fire-and-forget so it doesn't block the agent, but it means conversation history is never compacted — leading to growing token usage over time.

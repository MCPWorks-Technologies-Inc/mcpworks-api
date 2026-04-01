# Implementation Plan: Fix Procedure Step Execution & Conversation Memory

**Branch**: `017-fix-procedure-execution` | **Date**: 2026-04-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/017-fix-procedure-execution/spec.md`

## Summary

Fix two bugs preventing procedure-first enforcement from working end-to-end:

1. **Procedure step execution** — The inner AI orchestration at each step fails to call the required function because: (a) context is presented as a raw JSON dump, (b) all 36+ tools are presented instead of just the required one, and (c) the function's input_schema is not included in the step prompt. Fix by restructuring the step system prompt, limiting tools to the single required function, and including explicit parameter mapping.

2. **Conversation memory compaction** — `compact_history()` calls `chat(messages=[...])` but the function signature is `chat(message: str)`. Fix by passing the correct argument.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), httpx, structlog
**Storage**: PostgreSQL 15+ (existing), Redis 7+ (existing)
**Testing**: pytest with existing unit test suite (526 passing)
**Target Platform**: Linux server (production on server0.pop11)
**Project Type**: Single backend API
**Performance Goals**: Procedure step first-attempt success rate >80% (currently 0%)
**Constraints**: Changes must not break existing scheduled procedure execution (cron/webhook triggers)
**Scale/Scope**: 3 files changed, ~50 lines modified

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec 017 written and reviewed before implementation |
| II. Token Efficiency | PASS | Reducing tools from 36 to 1 per step saves tokens in procedure execution |
| III. Transaction Safety | PASS | No transaction changes — procedure steps already have retry/rollback |
| IV. Observability | PASS | Existing structlog events for procedure steps preserved |
| V. Test Coverage | PASS | Will add unit tests for new prompt structure and compaction fix |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/017-fix-procedure-execution/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── spec.md              # Feature specification
├── checklists/
│   └── requirements.md  # Quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (affected files)

```text
src/mcpworks_api/
├── tasks/
│   └── orchestrator.py          # Bug 1: procedure step prompt + tool filtering
├── core/
│   ├── ai_tools.py              # Helper: get function input_schema for step prompt
│   └── conversation_memory.py   # Bug 2: chat() signature fix
└── services/
    └── function.py              # Read: get input_schema for a function by ref

tests/unit/
├── test_procedure_step_prompt.py    # New: verify step prompt structure
└── test_conversation_memory.py      # New: verify compaction calls chat() correctly
```

## Research (Phase 0)

### R-001: Procedure step prompt effectiveness

**Decision**: Restructure the step system prompt to include three key improvements:
1. Present only the required function as a tool (not all 36+)
2. Include the function's input_schema in the prompt so the AI knows exact parameter names
3. Format accumulated context as explicit variable assignments, not raw JSON

**Rationale**: The current prompt gives the inner AI a JSON dump of context and 36 tools. The AI must: parse JSON, identify the right tool, map context values to parameters. With 1 tool and explicit variables, the AI only needs to construct the function call.

**Alternatives considered**:
- Deterministic execution (bypass AI entirely, hard-code parameter mapping in step config) — rejected because it removes the AI's ability to adapt and compose (e.g., crafting a Discord summary from multiple step results)
- Few-shot examples in prompt — adds tokens without addressing the root cause (tool selection confusion)

### R-002: Conversation memory chat() fix

**Decision**: Change `compact_history()` to call `chat(message=compaction_prompt)` instead of `chat(messages=[...])`.

**Rationale**: The `chat()` function signature takes `message: str`. The `messages` keyword was likely a typo or confusion with the `chat_with_tools()` function which does take `messages: list`.

**Alternatives considered**:
- Change `chat()` to accept `messages` — rejected because `chat()` is a simple single-turn wrapper and other callers use it correctly

## Design (Phase 1)

### D-001: Step prompt restructuring (orchestrator.py)

**Current** (line ~980 of orchestrator.py):
```python
system_prompt = (
    f"You are executing step {step_num} of a procedure.\n\n"
    f"## Step: {step_name}\n"
    f"## Instructions\n{instructions}\n\n"
    f"## Required Function\n"
    f"You MUST call the function `{tool_name}` to complete this step.\n"
    f"Do NOT respond with text only — you must make a tool call to `{tool_name}`.\n\n"
    f"## Context from prior steps\n{ctx_str}\n"
)
```

**New**: Add input_schema, format context as variables, strengthen call instruction:
```python
# Get input_schema for the target function
schema_str = json.dumps(fn_input_schema, indent=2) if fn_input_schema else "{}"

# Format context as named variables
ctx_lines = []
if input_context:
    for k, v in input_context.items():
        ctx_lines.append(f"  {k} = {json.dumps(v)}")
for prev_step_key, prev_step_val in accumulated_context.items():
    if prev_step_key == "input":
        continue
    result = prev_step_val.get("result", {})
    ctx_lines.append(f"  {prev_step_key}_result = {json.dumps(result, default=str)}")
ctx_formatted = "\n".join(ctx_lines) if ctx_lines else "  (none)"

system_prompt = (
    f"You are executing step {step_num} of a procedure.\n\n"
    f"## Step: {step_name}\n"
    f"## Instructions\n{instructions}\n\n"
    f"## Required Function: `{tool_name}`\n"
    f"Parameter schema:\n```json\n{schema_str}\n```\n\n"
    f"## Available Data\n{ctx_formatted}\n\n"
    f"## RULES\n"
    f"- You MUST make a tool call to `{tool_name}`. Do NOT respond with text.\n"
    f"- Use the available data above to fill the function parameters.\n"
    f"- Do NOT fabricate data that is not in the available data section.\n"
)
```

**Tool filtering**: Pass only the required function's tool definition to `chat_with_tools`, not all tools:
```python
step_tools = [t for t in tools if t["name"] == tool_name]
```

### D-002: Get function input_schema helper

Add a helper to fetch the input_schema for a function by its `service.function` reference. This is called once per step to include the schema in the prompt.

### D-003: Conversation memory fix (conversation_memory.py)

**Current** (line 186):
```python
new_summary = await chat(
    engine=ai_engine,
    model=ai_model,
    api_key=api_key,
    messages=[{"role": "user", "content": compaction_prompt}],
    system_prompt="You are a concise conversation summarizer.",
)
```

**New**:
```python
new_summary = await chat(
    engine=ai_engine,
    model=ai_model,
    api_key=api_key,
    message=compaction_prompt,
    system_prompt="You are a concise conversation summarizer.",
)
```

### D-004: Retry enhancement

On retry attempts (attempt > 0), append to the system prompt:
```python
if attempt > 0:
    system_prompt += (
        f"\n\n## PREVIOUS ATTEMPT FAILED\n"
        f"You must call `{tool_name}` with the correct parameters. "
        f"Do not respond with text. Make the tool call now."
    )
```

## No new data models, API contracts, or quickstart needed

This is a bug fix affecting internal orchestration code only. No new endpoints, no schema changes, no new entities. The `data-model.md`, `contracts/`, and `quickstart.md` artifacts are not applicable.

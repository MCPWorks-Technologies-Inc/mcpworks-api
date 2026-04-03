# 016: Procedure-First Enforcement

**Status:** Implemented (2026-04-02)
**Author:** Simon Carr / Claude
**Date:** 2026-04-01
**Affects:** orchestrator, agent_service, ai_tools

---

## Overview

### Problem

Procedures exist to prevent LLM hallucination of function calls — they force step-by-step execution with verifiable proof. But currently, the agent AI can simply ignore procedures and call raw functions directly. There is no enforcement. The LLM sees a flat list of tools (36 functions + platform tools including `run_procedure`) and picks whatever seems fastest, which is usually the raw function.

This was observed on 2026-04-01: the mcpworkssocial agent was asked to post a Bluesky thread. A `post-bluesky-thread` procedure exists for exactly this purpose. The agent ignored it, called `post-to-bluesky` directly (or rather, hallucinated calling it), and fabricated URIs. The procedure was only used when the user explicitly demanded it.

**If the user has to tell the agent to use a procedure, the procedure framework has failed.**

### Purpose

Make procedures the default execution path. When a procedure exists for a workflow, the agent MUST use it. Raw function calls should be the exception (ad-hoc operations, debugging), not the rule.

### Success Criteria

1. Agent AI always uses `run_procedure` when a matching procedure exists
2. Functions covered by procedures are visibly marked as "use via procedure" in the tool list
3. Optional hard enforcement: `procedure_only` functions are rejected if called directly during agent orchestration
4. Zero changes needed to existing procedures — enforcement is platform-level
5. No impact on external MCP tool calls (create/run endpoints) — this only affects agent orchestration

### Scope

**In scope:**
- System prompt injection for procedure priority
- `procedure_only` flag on functions
- Procedure-covered function detection
- Orchestrator-level enforcement (reject direct calls)
- Tool list presentation changes

**Out of scope:**
- Changes to the procedure execution engine itself
- External API behavior (MCP create/run endpoints unaffected)
- Human-initiated function calls via run endpoint

---

## Design

### 1. System Prompt Injection

`augment_system_prompt()` in `core/ai_tools.py` currently lists tools in a flat list. Change it to:

**Before functions, inject a procedures section:**

```
## Procedures (USE THESE FIRST)

When a procedure exists for the task you're about to do, you MUST use
`run_procedure` instead of calling the underlying functions directly.
Procedures enforce step-by-step execution with proof — they exist to
prevent errors. Calling raw functions that are covered by a procedure
is a violation.

Available procedures:
- `social / post-bluesky-thread` — Post a threaded Bluesky conversation (2+ posts)
- `social / daily-intel` — Full daily intelligence pipeline (5 steps)
- `social / share-news` — Find and share news to Bluesky safely (3 steps)

## Your callable tools
[... existing tool list ...]
```

**Implementation:** `augment_system_prompt` receives a new `procedures` parameter (list of procedure summaries). If non-empty, the procedures section is prepended before tools.

### 2. `procedure_only` Flag on Functions

Add an optional boolean column `procedure_only` to the `function_versions` table (or `functions` table).

```sql
ALTER TABLE functions ADD COLUMN procedure_only BOOLEAN DEFAULT FALSE;
```

When `procedure_only = True`:
- The function is hidden from the agent's direct tool list during orchestration
- The function can still be called by the procedure engine (which calls functions internally)
- The function can still be called via the external MCP run endpoint (human-initiated)
- The function appears in `list_functions` output with a `[procedure_only]` marker

**Use case:** `post-to-bluesky` and `reply-to-post` should be `procedure_only` since the `post-bluesky-thread` procedure covers them. This prevents the agent from even seeing them as direct options.

**API change:** Add `procedure_only` parameter to `make_function` and `update_function` MCP tools.

### 3. Procedure-Covered Function Detection

When building the tool list for agent orchestration, query procedures for the namespace and extract which functions they reference:

```python
async def get_procedure_covered_functions(namespace_id: UUID, db: AsyncSession) -> set[str]:
    """Return set of function refs (service.function) covered by any procedure."""
    procedures = await proc_service.list_procedures(namespace_id)
    covered = set()
    for proc in procedures:
        version = proc.get_active_version_obj()
        if version:
            for step in version.steps:
                covered.add(step["function_ref"])
    return covered
```

This set is used in two places:
- Tool list assembly: mark covered functions with `(use via procedure: {procedure_name})`
- Hard enforcement: reject direct calls if the function has `procedure_only = True`

### 4. Tool List Presentation

For functions covered by procedures but NOT marked `procedure_only`, append a hint:

```
- `social__post-to-bluesky` — Post to Bluesky via AT Protocol... ⚠️ USE PROCEDURE: post-bluesky-thread
```

For functions marked `procedure_only`, exclude from the agent tool list entirely. They don't appear as callable options.

### 5. Orchestrator Enforcement

In `orchestrator.py`, when the agent AI requests a tool call during chat orchestration:

```python
if tool_name in procedure_only_functions:
    # Find which procedure covers this function
    covering_proc = procedure_map.get(tool_name)
    return {
        "error": f"This function is procedure-only. Use run_procedure with "
                 f"'{covering_proc}' instead of calling {tool_name} directly."
    }
```

This is a soft error — the agent gets a message telling it to use the procedure, not a hard crash. The agent can self-correct on the next turn.

### 6. Enforcement Levels

Three levels, configurable per-namespace (default: `hint`):

| Level | Behavior |
|-------|----------|
| `hint` | Procedures listed prominently in system prompt. Covered functions annotated with "use procedure X". No blocking. |
| `warn` | Same as hint, plus: if agent calls a covered function directly, the result includes a warning: "This call succeeded but should use procedure X." |
| `enforce` | Same as warn, plus: `procedure_only` functions are rejected with an error directing the agent to the correct procedure. |

**Default:** `hint` (backward compatible, no breaking changes).

Stored in namespace settings:
```sql
ALTER TABLE namespaces ADD COLUMN procedure_enforcement VARCHAR(10) DEFAULT 'hint';
```

---

## Data Model Changes

```sql
-- Function-level flag
ALTER TABLE functions ADD COLUMN procedure_only BOOLEAN DEFAULT FALSE;

-- Namespace-level enforcement setting
ALTER TABLE namespaces ADD COLUMN procedure_enforcement VARCHAR(10) DEFAULT 'hint';
```

Alembic migration required.

---

## Affected Files

| File | Change |
|------|--------|
| `core/ai_tools.py` | `augment_system_prompt` — add procedures section, annotate covered functions |
| `core/ai_tools.py` | `build_tool_definitions` — filter `procedure_only` functions in agent mode |
| `tasks/orchestrator.py` | Chat orchestration — check procedure_only enforcement before executing tool calls |
| `models/function.py` | Add `procedure_only` column |
| `models/namespace.py` | Add `procedure_enforcement` column |
| `mcp/tool_registry.py` | `make_function` / `update_function` — accept `procedure_only` parameter |
| `services/procedure_service.py` | Add `get_covered_functions()` helper |

---

## Token Efficiency

Procedure section in system prompt: ~100-200 tokens (scales with procedure count, not function count). Acceptable overhead — procedures are few, and the enforcement text prevents wasted turns from hallucinated calls.

---

## Security

- `procedure_only` enforcement only applies during agent orchestration (`agent_mode=True`)
- External MCP calls (create/run endpoints) are never restricted by this
- Human-initiated function calls via `execute` tool are unaffected
- No new attack surface — this restricts agent capability, doesn't expand it

---

## Testing

### Unit Tests

1. `test_augment_system_prompt_with_procedures` — procedures section appears before tools
2. `test_build_tools_hides_procedure_only` — `procedure_only` functions excluded in agent mode
3. `test_build_tools_shows_procedure_only_in_non_agent_mode` — functions visible for external callers
4. `test_covered_function_annotation` — covered functions get "use procedure X" hint
5. `test_procedure_only_enforcement` — orchestrator rejects direct call, returns helpful error
6. `test_enforcement_levels` — hint/warn/enforce behave correctly
7. `test_procedure_covered_detection` — correctly identifies functions referenced by procedures

### Integration Tests

1. Agent chat with `enforce` level: agent tries direct function → gets error → uses procedure → succeeds
2. Agent chat with `hint` level: agent sees procedure section, should prefer it (LLM behavior test)
3. External MCP call to `procedure_only` function: succeeds (not restricted)

---

## What Actually Shipped (2026-04-02)

The spec proposed a graduated approach (hint → warn → enforce) with a `procedure_only` flag. Implementation went further — **hard runtime enforcement for ALL covered functions**, no flag or per-namespace config needed.

### Implemented

1. **System prompt injection** (spec step 1) — `augment_system_prompt` lists procedures with "USE THESE FIRST" and annotates covered functions with "⚠️ USE PROCEDURE". Shipped 2026-04-01.

2. **Covered function detection** (spec step 2) — `_build_covered_function_set()` in `core/ai_tools.py` maps tool names to their covering procedure. Used for both prompt annotation and runtime enforcement.

3. **Hard runtime enforcement** (replaces spec steps 3-5) — `_dispatch_tool` in `orchestrator.py` and `_dispatch_chat_tool` in `agent_service.py` check if a namespace function is covered by a procedure. If so, the call returns a hard error directing the agent to `run_procedure`. No `procedure_only` flag needed — coverage is automatic from procedure step definitions. No enforcement levels — it's always enforced.

4. **Procedure execution exempt** — calls originating from within procedure step execution do NOT pass `procedure_covered`, so procedures can still call their underlying functions.

### Not Implemented (unnecessary)

- `procedure_only` column on functions — not needed, coverage is derived from procedures
- `procedure_enforcement` column on namespaces — not needed, enforcement is always on
- hint/warn/enforce levels — prompt hints kept for AI guidance, but enforcement is hard regardless

### Files Changed

| File | Change |
|------|--------|
| `core/ai_tools.py` | `augment_system_prompt` — procedures section + covered annotations. `_build_covered_function_set` + `get_procedure_summaries` |
| `tasks/orchestrator.py` | `_dispatch_tool` — `procedure_covered` param, blocks direct calls to covered functions |
| `services/agent_service.py` | `_dispatch_chat_tool` — same enforcement for chat path |
| `tests/unit/test_procedure_enforcement.py` | 6 unit tests for covered-function mapping and error format |

### Tests

6 unit tests in `test_procedure_enforcement.py`:
- `test_empty_summaries` / `test_single_procedure_single_function` / `test_multiple_procedures_multiple_functions` / `test_uncovered_function_not_in_set` — covered function mapping
- `test_error_message_contains_procedure_name` / `test_uncovered_function_not_blocked` — enforcement error format

---

## Approval

- [x] Spec reviewed
- [x] Implemented and deployed 2026-04-02
- [ ] Enforcement levels approved
- [ ] Migration plan approved

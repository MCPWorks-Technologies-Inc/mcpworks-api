# Feature Specification: Schema-Driven Procedure Input Mappings

**Spec ID**: 019-schema-driven-procedures
**Created**: 2026-04-07
**Status**: Draft
**Depends on**: 013-add-procedures-framework, 017-fix-procedure-execution
**Input**: Production failure — `post-bluesky-thread` procedure fails because the orchestrator LLM cannot reliably extract values from `input_context` arrays and map them to function parameters. `post-bluesky-single` succeeds because the input key (`text`) directly matches the function schema. The systemic issue: procedures rely on natural language instructions for data flow instead of explicit schema mappings.

## Problem Statement

Procedures have two LLM touchpoints with an ambiguity gap between them:

| Phase | LLM role | What it sees |
|---|---|---|
| **Authoring** | Creates procedure steps | Function schemas, natural language intent |
| **Execution** | Runs procedure steps | Step instructions, input_context blob, function schema |

Step instructions are natural language, but function inputs are structured. The authoring LLM writes "Post the FIRST message from the input context" and the executing LLM must figure out `input_context.posts[0]` → `{"text": "..."}`. This interpretation fails for anything beyond trivial key-name matches.

Spec 017 addresses the immediate symptom (better prompting for the inner AI). This spec addresses the root cause: **procedures should declare explicit data mappings, not rely on LLM interpretation for parameter binding**.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Explicit input mappings on procedure steps (Priority: P1)

An operator creates a `post-bluesky-thread` procedure. Step 1 (post-root) needs the first item from a `posts` array passed as the `text` parameter to `post-to-bluesky`. Instead of writing instructions that say "extract the first post," the operator declares `input_mapping: {text: "$.posts[0]"}`. The orchestrator resolves the mapping before invoking the LLM, so the inner AI receives pre-extracted parameters.

**Why this priority**: This is the core fix. Without explicit mappings, every non-trivial procedure is fragile.

**Acceptance Scenarios**:

1. **Given** a procedure step with `input_mapping: {text: "$.posts[0]"}` and input_context `{"posts": ["Hello", "World"]}`, **When** the step executes, **Then** the function receives `{"text": "Hello"}` without LLM interpretation.
2. **Given** a procedure step with `input_mapping: {parent_uri: "$.steps.post-root.result.uri"}`, **When** step 2 executes after step 1 succeeded, **Then** the function receives the URI from step 1's result.
3. **Given** a procedure step with an `input_mapping` that references a missing path, **When** the step executes, **Then** the step fails with a clear error: "Mapping failed: $.steps.post-root.result.uri not found in context" — not a silent LLM hallucination.
4. **Given** a procedure step with partial `input_mapping` (some params mapped, some not), **When** the step executes, **Then** mapped params are pre-resolved and unmapped params are left for the LLM to fill from instructions.

---

### User Story 2 - Step output declarations (Priority: P1)

Each step declares which fields from the function result should be captured into the accumulated context, and under what key. This replaces the current behavior where the entire function result is dumped as a JSON blob.

**Why this priority**: Without structured outputs, step chaining via input_mapping has nothing reliable to reference.

**Acceptance Scenarios**:

1. **Given** a step with `output_mapping: {post_uri: "$.uri", post_cid: "$.cid"}`, **When** the function returns `{"success": true, "uri": "at://...", "cid": "abc123"}`, **Then** the accumulated context stores `{"steps": {"post-root": {"post_uri": "at://...", "post_cid": "abc123"}}}`.
2. **Given** a step with no `output_mapping`, **When** the function returns, **Then** the full result is stored under the step name (backward compatible).

---

### User Story 3 - Authoring guardrails (Priority: P2)

When an LLM (or human) creates a procedure via `make_procedure` or `update_procedure`, the system validates that:
- Every `input_mapping` path is syntactically valid
- Every `input_mapping` target matches a field in the referenced function's input_schema
- Step chaining references (e.g., `$.steps.post-root.result.uri`) refer to steps that precede the current step

**Acceptance Scenarios**:

1. **Given** a procedure step mapping `text` to `"$.posts[0]"` for a function whose input_schema has a `text` field, **When** the procedure is saved, **Then** validation passes.
2. **Given** a procedure step mapping `nonexistent_param` to `"$.posts[0]"` for a function without that param, **When** the procedure is saved, **Then** validation fails with "nonexistent_param is not in post-to-bluesky input schema."
3. **Given** a step 2 with `input_mapping: {parent_uri: "$.steps.step-3.result.uri"}` referencing a later step, **When** the procedure is saved, **Then** validation fails with "step-3 has not executed before step 2."

---

### User Story 4 - Backward compatibility (Priority: P2)

Existing procedures without `input_mapping` or `output_mapping` continue to work using the current behavior (LLM interprets instructions + raw context). This allows incremental migration.

**Acceptance Scenarios**:

1. **Given** an existing procedure with no `input_mapping` on any step, **When** executed, **Then** behavior is identical to current (spec 017 prompting improvements apply).
2. **Given** a procedure where some steps have `input_mapping` and others don't, **When** executed, **Then** mapped steps use schema resolution, unmapped steps use LLM interpretation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Procedure steps MAY declare an `input_mapping` object: keys are function parameter names, values are JSONPath expressions evaluated against accumulated context
- **FR-002**: Procedure steps MAY declare an `output_mapping` object: keys are context variable names, values are JSONPath expressions evaluated against the function result
- **FR-003**: The orchestrator MUST resolve `input_mapping` before presenting the step to the inner AI — the AI receives pre-extracted values, not raw context
- **FR-004**: If an `input_mapping` path fails to resolve, the step MUST fail with a descriptive error (not silently fall back to LLM interpretation)
- **FR-005**: If a step has both `input_mapping` and `instructions`, the mapping is authoritative for data flow; instructions provide supplementary context for the AI
- **FR-006**: `make_procedure` and `update_procedure` MUST validate input_mapping targets against the referenced function's input_schema
- **FR-007**: `make_procedure` and `update_procedure` MUST validate that step-chaining references point to preceding steps only
- **FR-008**: Steps without `input_mapping` MUST behave identically to the current implementation (backward compatible)

### Data Model Changes

```
procedure_steps table additions:
  input_mapping   JSONB NULL   -- {param_name: "$.jsonpath.expression"}
  output_mapping  JSONB NULL   -- {context_var: "$.jsonpath.expression"}
```

### Key Design Decisions

- **JSONPath over Jinja/template strings**: JSONPath is well-specified, has Python libraries, and is familiar from API tooling. No need for a custom expression language.
- **Pre-resolution over LLM interpretation**: The orchestrator resolves mappings deterministically. The LLM only handles what can't be expressed as a path (e.g., summarization, reformatting).
- **Fail-closed on mapping errors**: A broken mapping is a procedure authoring bug, not something the LLM should paper over.

## Success Criteria *(mandatory)*

- **SC-001**: `post-bluesky-thread` with `input_mapping` completes all 3 steps on first attempt (currently fails at step 1)
- **SC-002**: Procedure step first-attempt success rate exceeds 95% for steps with `input_mapping` (currently ~50% for simple cases, 0% for array/chaining cases)
- **SC-003**: Existing procedures without mappings continue to work with no behavior change
- **SC-004**: Invalid mappings are caught at authoring time, not at execution time

## Relationship to Other Specs

- **013-add-procedures-framework**: Defines the procedure model. This spec extends it with `input_mapping` and `output_mapping` on steps.
- **017-fix-procedure-execution**: Addresses the immediate symptom (better inner AI prompting). This spec addresses the root cause (schema-driven data flow). Both should ship — 017 improves the LLM fallback path, 019 makes the LLM fallback unnecessary for most cases.

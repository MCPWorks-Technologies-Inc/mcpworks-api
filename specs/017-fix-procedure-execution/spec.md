# Feature Specification: Fix Procedure Step Execution & Conversation Memory

**Feature Branch**: `017-fix-procedure-execution`  
**Created**: 2026-04-01  
**Status**: Draft  
**Input**: User description: "Fix procedure step execution failures — the procedure engine's inner AI orchestration fails to call functions correctly at each step. When run_procedure is called from chat, the procedure orchestrator spawns a nested AI loop for each step, but that inner AI fails to extract text from input_context and pass it to the function. Also fix conversation_memory compaction (chat() got unexpected keyword argument 'messages') which errors on every agent interaction."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Procedure steps execute functions correctly (Priority: P1)

When an agent uses `run_procedure` to execute a multi-step procedure (e.g., posting a Bluesky thread), each step's inner AI orchestration must correctly extract data from the accumulated context and pass it as arguments to the required function. Currently the inner AI sees the context as a JSON dump in its system prompt but fails to map values to function parameters, causing every step to fail after max retries.

**Why this priority**: Procedures are the core safety mechanism preventing agent hallucination. If steps can't execute, the entire procedure framework is useless — agents fall back to raw function calls which bypass verification.

**Independent Test**: Create a test procedure with 2 steps (step 1: call a simple function with a text parameter from input_context, step 2: call another function using step 1's result). Execute via `run_procedure`. Both steps must complete with verified results.

**Acceptance Scenarios**:

1. **Given** a procedure `post-bluesky-single` with input_context `{"text": "Hello world"}`, **When** `run_procedure` is called, **Then** step 1 calls `post-to-bluesky` with `text="Hello world"` and returns a valid URI
2. **Given** a procedure `post-bluesky-thread` with input_context containing post1_text and post2_text, **When** `run_procedure` is called, **Then** step 1 posts the root, step 2 replies using the URI from step 1, and step 3 sends a Discord report with links to both posts
3. **Given** a procedure step that receives accumulated context from prior steps, **When** the inner AI is prompted, **Then** it can extract specific values (URIs, text, IDs) from the context and pass them as function arguments
4. **Given** a procedure step where the inner AI responds with text instead of a tool call, **When** the step retries, **Then** subsequent attempts include clearer instructions referencing the exact parameter names from the function's input schema

---

### User Story 2 - Conversation memory compaction works (Priority: P2)

Agent conversation memory compaction silently fails on every interaction due to a function signature mismatch. The `compact_history` function calls `chat()` with `messages=[...]` but `chat()` expects `message: str`. This means conversation history grows unbounded and older context is never summarized.

**Why this priority**: While not a showstopper (agents still function), unbounded conversation history wastes tokens on every interaction and eventually degrades agent performance as context fills up.

**Independent Test**: Trigger conversation memory compaction by having an agent accumulate more turns than the compaction threshold. Verify the summary is generated and old turns are pruned.

**Acceptance Scenarios**:

1. **Given** an agent with conversation history exceeding the compaction threshold, **When** compaction runs, **Then** older turns are summarized into a concise summary and recent turns are preserved verbatim
2. **Given** compaction completes successfully, **When** the next agent interaction occurs, **Then** the summary is included in the system prompt context without errors

---

### Edge Cases

- What happens when a procedure step's required function has been deleted or renamed since the procedure was created?
- How does the system handle a procedure step where the inner AI calls the wrong function on every retry attempt?
- What happens when input_context contains deeply nested objects that the inner AI must destructure?
- How does compaction handle agent state that has been corrupted or has an unexpected format?
- What happens when the compaction LLM call itself fails (rate limit, timeout)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The procedure step system prompt MUST include the target function's input_schema so the inner AI knows exactly what parameters to pass
- **FR-002**: The procedure step system prompt MUST present input_context values as named variables with clear labels, not as a raw JSON dump that the AI must parse
- **FR-003**: When a procedure step fails because the AI responded with text instead of a tool call, the retry prompt MUST include explicit parameter mapping hints derived from the input_context and the function's schema
- **FR-004**: The conversation memory compaction function MUST call the AI chat function with the correct signature
- **FR-005**: Procedure step execution MUST pass accumulated context from prior steps in a structured format that explicitly maps step results to variable names the current step can reference
- **FR-006**: When a procedure step succeeds, the result MUST be stored in accumulated context with the function's output field names preserved
- **FR-007**: The step system prompt MUST present only the required function as a tool — not all 36+ namespace functions — to eliminate tool selection confusion

### Key Entities

- **Procedure Step Context**: The accumulated data passed between steps — must be structured for AI extraction, not raw JSON
- **Step Execution Attempt**: A single try at executing a step — includes the system prompt sent, the AI response, and whether the correct function was called with valid arguments
- **Conversation Memory**: Summary + recent turns stored in agent state — compaction summarizes old turns via LLM

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Procedure `post-bluesky-single` completes successfully on first attempt (both steps) when called via `run_procedure` from chat
- **SC-002**: Procedure `post-bluesky-thread` completes all 3 steps on first attempt when called via `run_procedure` from chat
- **SC-003**: Conversation memory compaction runs without errors after agent interactions exceed the compaction threshold
- **SC-004**: Procedure step first-attempt success rate exceeds 80% (currently 0% — all steps fail and exhaust retries)
- **SC-005**: No `conversation_memory_compaction_failed` errors appear in production logs after fix is deployed

## Assumptions

- The underlying functions (`post-to-bluesky`, `reply-to-post`, `send-discord-report`) work correctly when called with proper arguments — verified by direct sandbox execution
- The AI engine (OpenRouter/Claude Sonnet) is capable of making tool calls when given clear instructions and schema — the current failure is due to insufficient context in the step prompt, not an AI capability limitation
- The `chat()` function signature (`message: str`) is the intended interface and `compact_history` should conform to it
- Presenting only the required function (not all 36+ tools) to the step AI will significantly improve tool call accuracy

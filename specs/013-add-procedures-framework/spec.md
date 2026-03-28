# Feature Specification: Procedures Framework

**Feature Branch**: `013-add-procedures-framework`
**Created**: 2026-03-28
**Status**: Draft
**Input**: User description: "Add a Procedures framework to MCPWorks that solves the problem of LLM hallucination during agent orchestration by creating sequential, auditable execution pipelines that force the LLM to prove each step was actually executed."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create and Execute a Procedure (Priority: P1)

A platform operator has a social media agent that needs to post to BlueSky. Previously, the LLM hallucinated calling the post function and declared success without actually executing anything. The operator creates a procedure that defines the exact sequence of steps (authenticate → create post → verify post), each requiring the LLM to return verifiable proof from the actual function execution before moving to the next step.

**Why this priority**: This is the core value proposition. Without the ability to define and execute procedures with step-by-step verification, the entire feature has no purpose.

**Independent Test**: Can be fully tested by creating a procedure with 3 steps referencing existing namespace functions, executing it via the agent, and verifying that each step's result contains actual function output data — not hallucinated responses.

**Acceptance Scenarios**:

1. **Given** a namespace with existing functions (e.g., `socialmedia__bluesky_auth`, `socialmedia__bluesky_post`, `socialmedia__bluesky_get_post`), **When** the operator creates a procedure named "post-to-bluesky" with 3 ordered steps each referencing one of those functions, **Then** the procedure is saved with its step definitions, instructions, failure policies, and validation rules.
2. **Given** a saved procedure "post-to-bluesky", **When** the agent is triggered to execute it, **Then** the orchestrator presents step 1 to the LLM with the step's instructions and required function, waits for the LLM to call that function, captures the actual function result into the procedure's step 1 result object, and only then presents step 2.
3. **Given** a procedure mid-execution at step 2, **When** the LLM returns a text response instead of calling the required function, **Then** the orchestrator rejects the response, instructs the LLM to call the required function, and counts this as a retry attempt.
4. **Given** a procedure mid-execution, **When** the LLM calls a function that is not the one specified in the current step, **Then** the orchestrator rejects the call and instructs the LLM to call the correct function for this step.

---

### User Story 2 - Step Failure Handling and Retries (Priority: P1)

An operator has a procedure where step 2 (create post) sometimes fails due to rate limiting. The operator configures step 2 with `max_retries: 3` and `failure_policy: required`. Step 3 (verify post) is configured with `failure_policy: allowed` because verification is nice-to-have but not critical.

**Why this priority**: Without failure handling, any transient error would break the entire procedure. Failure policies are essential for real-world reliability and are tied to P1 because procedures without them are unusable in production.

**Independent Test**: Can be tested by creating a procedure where one step's function returns an error, verifying the retry behavior, and confirming the failure policy determines whether execution continues or halts.

**Acceptance Scenarios**:

1. **Given** a procedure step with `failure_policy: required` and `max_retries: 3`, **When** the function fails on the first attempt, **Then** the orchestrator retries up to 3 times before marking the step as failed.
2. **Given** a procedure step with `failure_policy: required` that has exhausted all retries, **When** the step is marked failed, **Then** the entire procedure execution is halted and marked as failed with details about which step failed and why.
3. **Given** a procedure step with `failure_policy: allowed` and `max_retries: 1`, **When** the function fails and the retry also fails, **Then** the step is marked as failed but execution continues to the next step with a note that the previous step's data is unavailable.
4. **Given** a procedure step with `failure_policy: skip`, **When** the function fails on the first attempt, **Then** the step is immediately marked as skipped (no retries) and execution continues to the next step.
5. **Given** a procedure where step 1 succeeded and step 2 has `failure_policy: allowed` and failed, **When** step 3 begins, **Then** step 3 receives the accumulated context from step 1's success data and a marker indicating step 2 produced no data.

---

### User Story 3 - Audit and Inspect Procedure Executions (Priority: P1)

An operator wants to verify that the social media agent actually posted to BlueSky. They inspect the procedure execution record and see a complete audit trail: each step's instructions, the function that was called, the exact result returned, timestamps, retry counts, and final status.

**Why this priority**: Auditability is the fundamental reason procedures exist — proving execution happened. Without inspection, procedures offer no advantage over the current orchestration model.

**Independent Test**: Can be tested by executing a procedure, then querying the execution record and verifying it contains step-by-step results with function outputs, timestamps, and status for each step.

**Acceptance Scenarios**:

1. **Given** a completed procedure execution, **When** the operator queries the execution record, **Then** the response includes: procedure name, overall status, start/end timestamps, and for each step: step number, step name, function called, instructions given, result data, status (success/failed/skipped), retry count, and per-attempt timestamps.
2. **Given** a failed procedure execution, **When** the operator queries the execution record, **Then** the failing step includes the error details from each retry attempt, making it clear exactly what went wrong and how many times it was retried.
3. **Given** multiple procedure executions over time, **When** the operator lists executions with filters (by procedure name, status, date range), **Then** matching execution records are returned in reverse chronological order.

---

### User Story 4 - Manage Procedures via MCP and REST (Priority: P2)

An operator wants to create, update, list, and delete procedures through the same interfaces they use for functions — both MCP tools (via the create endpoint) and REST API.

**Why this priority**: Management APIs are necessary for adoption but are standard CRUD — the core innovation is in execution and auditing (P1 stories).

**Independent Test**: Can be tested by creating a procedure via MCP `make_procedure` tool, listing it, describing it, updating it (which creates a new version), and deleting it.

**Acceptance Scenarios**:

1. **Given** a namespace with existing functions, **When** the operator calls `make_procedure` with a name, description, and step definitions, **Then** the procedure is created at version 1 with the specified configuration.
2. **Given** an existing procedure at version 1, **When** the operator calls `update_procedure` with modified step definitions, **Then** a new immutable version 2 is created and set as the active version. Version 1 remains unchanged for audit purposes.
3. **Given** an existing procedure, **When** the operator calls `describe_procedure`, **Then** the response includes the procedure's name, description, active version, all step definitions with their instructions, function references, failure policies, and validation rules.
4. **Given** an existing procedure, **When** the operator calls `delete_procedure`, **Then** the procedure is soft-deleted and no longer appears in listings or is available for execution, but historical execution records remain intact.

---

### User Story 5 - Trigger Procedures from Schedules, Webhooks, and Channels (Priority: P2)

An operator wants to schedule a procedure to run daily at 9 AM, post a summary to BlueSky. They also want to trigger a different procedure when a webhook fires. The existing trigger infrastructure (schedules, webhooks, channels) should support procedures as a target alongside direct function calls.

**Why this priority**: Integration with existing trigger mechanisms is important for real-world use but builds on top of the P1 execution engine.

**Independent Test**: Can be tested by creating an agent schedule with `orchestration_mode: procedure` and a `procedure_name`, triggering the schedule, and verifying the procedure executes with full step-by-step audit.

**Acceptance Scenarios**:

1. **Given** an agent with a schedule configured with `orchestration_mode: procedure` and `procedure_name: post-to-bluesky`, **When** the schedule fires, **Then** the orchestrator executes the named procedure with full step sequencing and audit recording.
2. **Given** an agent webhook configured to trigger a procedure, **When** the webhook receives a request, **Then** the procedure is executed with the webhook payload available as input context to step 1.
3. **Given** a channel message that triggers a procedure, **When** the procedure completes, **Then** the final result is sent back to the channel (same as current orchestration behavior).

---

### User Story 6 - Data Forwarding Between Steps (Priority: P2)

An operator creates a procedure where step 1 authenticates and returns an access token, step 2 needs that token to create a post, and step 3 needs the post URI from step 2 to verify. Each step should automatically receive the accumulated results from all prior steps as context.

**Why this priority**: Data forwarding between steps makes procedures practical for multi-step workflows. Without it, each step would operate in isolation, severely limiting usefulness.

**Independent Test**: Can be tested by creating a 3-step procedure where step 2's instructions reference step 1's output, executing it, and verifying step 2 received step 1's result data in its context.

**Acceptance Scenarios**:

1. **Given** a procedure where step 1 returns `{"access_token": "abc123"}`, **When** step 2 begins, **Then** the LLM receives step 2's instructions along with the accumulated context: `{"step_1": {"status": "success", "result": {"access_token": "abc123"}}}`.
2. **Given** a procedure where step 2 has `failure_policy: allowed` and failed, **When** step 3 begins, **Then** the accumulated context includes `{"step_2": {"status": "failed", "result": null}}` so step 3 can adapt its behavior.
3. **Given** a procedure with 5 steps, **When** step 5 begins, **Then** the accumulated context includes results from all 4 prior steps, maintaining the complete execution history for the LLM to reference.

---

### Edge Cases

- What happens when a procedure references a function that has been deleted? The procedure execution should fail immediately at that step with a clear error ("function not found") rather than allowing the LLM to hallucinate an alternative.
- What happens when a procedure is executed but the agent's AI engine is unavailable? The procedure execution should fail with an appropriate error before any steps are attempted.
- What happens when the orchestration loop reaches its iteration limit mid-procedure? The procedure should be marked as failed at the current step with a "timeout/iteration limit exceeded" status.
- What happens when a procedure has zero steps defined? Creation should be rejected — a procedure must have at least one step.
- What happens when two procedures are triggered simultaneously for the same agent? Each procedure execution should be independent with its own execution record, subject to the agent's existing concurrency limits.
- What happens when a step's validation rule doesn't match the result but the function succeeded? The step should be marked as failed (validation failure) and retried if retries remain — a function returning unexpected data is treated as a failure.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow users to create procedures within a namespace, each consisting of an ordered list of steps with function references, instructions, failure policies, max retries, and optional validation rules.
- **FR-002**: System MUST enforce sequential step execution — the orchestrator presents one step at a time and only advances after capturing the function's actual result.
- **FR-003**: System MUST reject LLM responses that do not include a call to the step's required function, counting such responses as retry attempts.
- **FR-004**: System MUST implement three failure policies per step: `required` (must succeed or procedure fails), `allowed` (continue on failure with unclean data), and `skip` (skip step on first failure without retrying).
- **FR-005**: System MUST support configurable retry counts per step (default: 1, minimum: 0, maximum: 5).
- **FR-006**: System MUST capture and persist a complete execution record for every procedure run, including per-step results, function outputs, retry counts, timestamps, and final status.
- **FR-007**: System MUST version procedures immutably — updates create new versions, old versions remain for audit trail.
- **FR-008**: System MUST forward accumulated step results to subsequent steps, giving the LLM context from all prior steps.
- **FR-009**: System MUST support procedure execution via schedules, webhooks, manual triggers, and channel messages by adding `procedure` as an orchestration mode.
- **FR-010**: System MUST expose procedure management (create, read, update, delete, list) via both MCP tools and REST API.
- **FR-011**: System MUST validate that all functions referenced in a procedure exist in the namespace at creation time.
- **FR-012**: System MUST support optional validation rules per step that check the function result for required fields or patterns before marking the step as successful.
- **FR-013**: System MUST record procedure executions as AgentRun records with `trigger_type` indicating the source and the full step-by-step audit data stored in the result.
- **FR-014**: System MUST enforce that a procedure contains at least one step and that each step references exactly one function.
- **FR-015**: System MUST soft-delete procedures while preserving all historical execution records for audit purposes.

### Key Entities

- **Procedure**: A named, versioned template defining an ordered sequence of steps. Belongs to a namespace service (like functions). Key attributes: name, description, active version, service association.
- **ProcedureVersion**: An immutable snapshot of a procedure's step definitions. Created on each update. Key attributes: version number, steps definition, creator, creation timestamp.
- **ProcedureStep** (embedded in version): A single step within a procedure version. Key attributes: step number, name, function reference (service__function), instructions for the LLM, failure policy, max retries, validation rules.
- **ProcedureExecution**: A runtime instance of a procedure being executed. Key attributes: procedure reference, version executed, overall status, start/end timestamps, trigger type, agent association.
- **ProcedureStepResult** (embedded in execution): The result of executing a single step. Key attributes: step number, status (pending/running/success/failed/skipped), function called, result data, error details, attempt count, per-attempt timestamps.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When a procedure is executed, 100% of steps produce verifiable function output in the execution record — no step can be marked "success" without captured function result data.
- **SC-002**: Operators can trace the complete execution history of any procedure run, seeing exactly which functions were called, what they returned, and how long each step took.
- **SC-003**: Procedures with `failure_policy: required` halt immediately on step failure (after retries), preventing downstream steps from executing with missing prerequisites.
- **SC-004**: Procedures eliminate hallucinated function execution — the orchestrator only marks a step complete when the actual function backend returns a result, not when the LLM claims it called the function.
- **SC-005**: Operators can create and manage procedures through the same interfaces they use for functions (MCP tools and REST API) with no additional tooling required.
- **SC-006**: Existing agent triggers (schedules, webhooks, channels, manual) can target procedures without requiring changes to the trigger configuration model beyond selecting "procedure" mode and specifying a procedure name.
- **SC-007**: Procedure execution overhead adds no more than 10% to the total execution time compared to manually calling the same functions in sequence.

## Assumptions

- Procedures follow the same organizational hierarchy as functions: Namespace → Service → Procedure.
- Procedures reference functions by their `service__function` naming convention, consistent with existing tool naming.
- Step validation rules use a simple declarative format (e.g., "result must contain field X") rather than arbitrary code execution, to keep validation deterministic and safe.
- The existing orchestration loop will be extended to support procedure mode rather than creating a separate execution engine.
- Procedure execution respects existing tier-based orchestration limits (max iterations, token budgets, execution time).
- Each step maps to exactly one function call to keep the execution model simple and auditable. Multi-function steps can be achieved by composing functions or using sequential steps.
- The LLM is still involved in executing each step (interpreting instructions, calling the function with appropriate arguments) — procedures constrain *which* function must be called but the LLM still handles *how* to call it (argument construction from context).

## Scope

**In Scope:**
- Procedure data model (Procedure, ProcedureVersion) with database migrations
- Procedure execution engine integrated into the orchestrator
- Step-by-step result capture and validation
- Failure policies (required, allowed, skip) and configurable retries
- Data forwarding between steps (accumulated context)
- Procedure CRUD via MCP tools and REST API
- Procedure as an orchestration mode for schedules, webhooks, channels, and manual triggers
- Execution audit records with full step-by-step detail
- Immutable versioning consistent with function versioning

**Out of Scope:**
- Parallel step execution (steps are strictly sequential in this version) — future enhancement
- Conditional branching (if step 2 fails, go to step 5 instead of step 3) — future enhancement
- Procedure composition (a procedure step that calls another procedure) — future enhancement
- Visual procedure builder UI — future, separate feature
- Cross-namespace procedure references (procedures can only reference functions in their own namespace)
- Step-level timeout configuration (uses existing orchestration-level timeouts)

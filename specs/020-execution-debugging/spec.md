# Feature Specification: Developer-Friendly Execution Debugging

**Feature Branch**: `020-execution-debugging`
**Created**: 2026-04-07
**Status**: Draft
**Input**: User description: "Developer-friendly execution debugging with error chain replay (issue #54)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Query Function Execution History (Priority: P1)

A developer wants to see recent executions for a specific function — what ran, when, whether it succeeded or failed, and what the error was. They query by function name and time range, and get a list of executions with status, duration, and error summaries.

**Why this priority**: This is the most basic debugging need — "did it work, and if not, what happened?" Without queryable execution history, developers are blind to what their functions are doing in production.

**Independent Test**: Can be fully tested by executing a function (both success and failure cases), then querying the execution history and verifying the records appear with correct status, timing, and error information.

**Acceptance Scenarios**:

1. **Given** a function that has been executed 5 times (3 successes, 2 failures), **When** the developer queries execution history for that function, **Then** all 5 executions are returned with their status, duration, and timestamps.
2. **Given** a function execution that failed with "Text is 313 graphemes, max 300", **When** the developer views that execution, **Then** the error message is visible without needing to check server logs.
3. **Given** multiple functions across services, **When** the developer queries with a status filter of "failed", **Then** only failed executions are returned.
4. **Given** execution history spanning multiple days, **When** the developer queries with a time range, **Then** only executions within that range are returned.

---

### User Story 2 - View Execution Detail with Input/Output (Priority: P1)

A developer investigating a specific failure wants to see the full execution record: what input was provided, what output was returned (or what error occurred), which function version ran, and how long it took. This is the "zoom in" from the history list.

**Why this priority**: Knowing a function failed isn't enough — developers need to see the inputs that caused the failure and the exact error to diagnose the issue.

**Independent Test**: Can be fully tested by executing a function with known inputs, then retrieving the execution detail and verifying all fields match.

**Acceptance Scenarios**:

1. **Given** a completed execution, **When** the developer retrieves execution detail by ID, **Then** they see: function name, service name, function version, input data, output data, status, start time, end time, and duration.
2. **Given** a failed execution, **When** the developer retrieves execution detail, **Then** they see the error message, error code, and the input data that caused the failure.
3. **Given** an execution where the output was truncated (large result), **When** the developer retrieves execution detail, **Then** the truncation is indicated and the truncated output is shown.

---

### User Story 3 - Procedure Execution Error Chain (Priority: P2)

A developer investigating a failed procedure wants to see the full chain: which step failed, what inputs were provided to that step, what the LLM attempted, and what error the function returned. For multi-attempt steps, all attempts are visible with their individual errors.

**Why this priority**: Procedures involve multiple steps with AI orchestration. When they fail, the developer needs to see the full decision chain — not just "step 1 failed" but "step 1 failed because the LLM sent 313 graphemes when the limit is 300, and it retried 3 times with the same input."

**Independent Test**: Can be fully tested by running a procedure that fails at a specific step, then querying the procedure execution and verifying the step-by-step error chain is complete.

**Acceptance Scenarios**:

1. **Given** a procedure that failed at step 2 after 3 attempts, **When** the developer queries the procedure execution, **Then** they see all 3 attempts for step 2 with individual error messages and timestamps.
2. **Given** a procedure where step 1 succeeded and step 2 failed, **When** the developer views the execution, **Then** step 1 shows its result and step 2 shows its error chain, with the accumulated context that was available to step 2.
3. **Given** a procedure execution, **When** the developer queries it via MCP tools, **Then** the response includes the input_context that was provided to the procedure.

---

### User Story 4 - Execution History via MCP Tools (Priority: P2)

A developer using Claude Desktop or another MCP client wants to query execution history and debug failures without leaving their AI assistant. New MCP tools on the create endpoint expose execution history and detail.

**Why this priority**: Developers interact with MCPWorks through MCP clients. If debugging requires switching to a separate API or dashboard, it breaks their workflow.

**Independent Test**: Can be fully tested by calling the new MCP tools and verifying they return execution data matching the REST API responses.

**Acceptance Scenarios**:

1. **Given** a namespace with recent executions, **When** the developer calls `list_executions(service="social", function="post-to-bluesky", status="failed")`, **Then** failed executions for that function are returned.
2. **Given** an execution ID, **When** the developer calls `describe_execution(execution_id="...")`, **Then** the full execution detail is returned.
3. **Given** a namespace with many executions, **When** the developer calls `list_executions(limit=10)`, **Then** only the 10 most recent are returned with a total count.

---

### Edge Cases

- What happens when execution records exceed retention limits? Records older than the retention period are automatically pruned. Default retention: 30 days for detailed records, 90 days for summary records.
- What happens when a function execution produces very large output? Output is truncated to a size limit (configurable per tier) and the truncation is flagged in the execution record.
- What happens when the execution table grows very large? Indexes on (namespace_id, function_name, created_at) and (namespace_id, status) ensure query performance. Older records are pruned by a background task.
- What happens when stderr contains sensitive data? Error messages are scrubbed using the existing `_scrub_error_message()` function before storage.
- What happens when a function is deleted but its execution history exists? Execution records are retained (soft reference) — the function name is stored as a string, not a foreign key.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST persist execution records for every function call via the run endpoint, including: function name, service name, function version, input data, output/error, status, timing, and execution ID.
- **FR-002**: System MUST provide a REST API endpoint to list executions with filtering by: function name, service name, status, and time range.
- **FR-003**: System MUST provide a REST API endpoint to retrieve a single execution record by ID with full detail (input, output, error, timing).
- **FR-004**: System MUST provide MCP tools (`list_executions`, `describe_execution`) on the create endpoint for execution history queries.
- **FR-005**: System MUST persist stdout and stderr output from function executions for debugging (truncated to a per-tier size limit).
- **FR-006**: Procedure execution records MUST include per-step attempt details with individual error messages, timestamps, and the accumulated context available to each step.
- **FR-007**: Error messages in execution records MUST be scrubbed of PII and sensitive data before storage.
- **FR-008**: Execution records MUST be scoped to the namespace — users can only query executions for namespaces they own or have access to.
- **FR-009**: System MUST support pagination for execution history queries (limit/offset).
- **FR-010**: System MUST automatically prune execution records older than a configurable retention period (default: 30 days).

### Key Entities

- **Execution Record**: A persistent record of a single function execution. Contains: execution ID, namespace, service, function, version, input, output/error, status, timing, stdout/stderr (truncated).
- **Procedure Execution**: Already exists — extended to be queryable via REST API and MCP tools with full step detail.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can find why a specific function failed within 30 seconds using either the REST API or MCP tools (query history → view detail → read error).
- **SC-002**: 100% of function executions via the run endpoint produce a queryable execution record.
- **SC-003**: Execution history queries return results in under 500ms for namespaces with up to 100,000 records.
- **SC-004**: Procedure execution detail includes all step attempts with individual error messages — no black boxes.
- **SC-005**: Sensitive data (PII, credentials) is never present in stored execution records.

## Assumptions

- The existing `Execution` model in `models/execution.py` is the foundation — it already captures most of the needed fields. The main gap is that execution records are not consistently persisted for all run endpoint calls, and there's no API to query them.
- Stdout/stderr from sandbox execution is captured in the `ExecutionResult` but currently discarded after the response is sent. Persisting it requires extending the execution record.
- Procedure execution records already exist with step-level detail (`ProcedureExecution` model) — US3 is primarily about exposing them via queryable API, not creating new data.
- Retention and pruning will use a background task similar to the existing scheduler.

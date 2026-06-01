# Feature Specification: Orchestration Pipeline Observability

**Feature Branch**: `027-orchestration-observability`  
**Created**: 2026-04-14  
**Status**: Draft  
**Input**: PROBLEM-029 — Orchestration pipeline between "cron fires" and "function executes" is invisible. Agents hallucinate explanations for their own behavior and failures go undetected.

## Clarifications

### Session 2026-04-14

- Q: What level of AI reasoning should be captured in orchestration run steps? → A: Structured decision log — record decision type (called function, skipped function, no action) plus a reason category enum (quality_threshold_not_met, no_matching_data, limit_reached, error, etc.). No free-text AI summaries to avoid PII exposure from ingested tool results.
- Q: What happens when a cron fires while a previous run is still active? → A: No gating — the system does not prevent concurrent runs. Every fire is recorded and produces a run. Overlapping runs appear in history so the owner can see concurrency and adjust their schedule if needed. The scheduler has no reliable way to check run state without introducing race conditions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Diagnose Why a Scheduled Agent Didn't Act (Priority: P1)

A namespace owner has an agent running on a cron schedule (e.g., find news and post to social media every 6 hours). The agent stops producing output. The owner needs to determine whether the agent chose not to act, failed silently, hit an orchestration limit, or never fired at all — without contacting the platform operator.

**Why this priority**: This is the exact scenario that triggered PROBLEM-029. Without this, every "why isn't my agent doing X?" question requires platform operator intervention. This is the #1 barrier to client self-service for scheduled automation.

**Independent Test**: Can be fully tested by running a scheduled agent, then querying its orchestration run history to see the trigger, reasoning steps, function calls made, and final outcome. Delivers immediate diagnostic value.

**Acceptance Scenarios**:

1. **Given** an agent with a cron schedule that has fired 5 times in the last 24 hours, **When** the owner queries orchestration run history for that agent, **Then** they see all 5 runs with trigger source, start/end time, steps taken, and final outcome.
2. **Given** an orchestration run where the agent AI decided not to call any functions, **When** the owner views that run, **Then** the outcome is clearly marked as "no action taken" (not indistinguishable from a failure or a non-fire).
3. **Given** an orchestration run that terminated because it hit `max_iterations`, **When** the owner views that run, **Then** the outcome shows "limit hit" with which limit was reached and current vs. configured values.
4. **Given** an agent with zero orchestration runs in a time period, **When** the owner checks cron fire history, **Then** they can distinguish "schedule didn't fire" from "schedule fired but produced no recorded run."

---

### User Story 2 - Trace a Function Execution Back to Its Trigger (Priority: P2)

A namespace owner sees a function execution in their activity log and needs to understand what caused it — was it a cron schedule, a chat message, a webhook, or a manual invocation? They need to see the full context: what else happened in the same orchestration run, what the agent was trying to accomplish, and whether it succeeded.

**Why this priority**: Without execution-to-run correlation, function executions are disconnected data points. Owners can see individual calls but not the story they're part of. This is essential for understanding agent behavior patterns and debugging multi-step workflows.

**Independent Test**: Can be tested by triggering an orchestration run that calls multiple functions, then navigating from any single function execution to the parent run and seeing all sibling executions.

**Acceptance Scenarios**:

1. **Given** a function execution that was triggered by a cron-initiated orchestration run, **When** the owner views that execution, **Then** they see a reference to the parent orchestration run.
2. **Given** an orchestration run that called 3 functions, **When** the owner views the run, **Then** they see all 3 function executions listed with their individual outcomes and execution order.
3. **Given** a function execution that was triggered by a direct API call (no orchestration), **When** the owner views that execution, **Then** the orchestration run reference is absent (not a fake "direct" run).

---

### User Story 3 - Cron Fire History (Priority: P2)

A namespace owner has a cron schedule configured and wants to verify it's firing on time. Today they can only see a `consecutive_failures` counter and an `enabled` flag. They need actual fire history: when did it fire, what orchestration run did each fire produce, and did any fires fail to start a run.

**Why this priority**: This closes the first gap in the pipeline — without fire history, owners can't distinguish "cron isn't firing" from "cron fires but the run produces nothing useful." Tied with User Story 2 because fire history and execution correlation together provide end-to-end traceability.

**Independent Test**: Can be tested by enabling a cron schedule, waiting for several fires, then querying fire history and verifying timestamps and associated run IDs.

**Acceptance Scenarios**:

1. **Given** a cron schedule that has fired 10 times, **When** the owner queries fire history, **Then** they see the last N fires with timestamps and the orchestration run ID each produced.
2. **Given** a cron fire that failed to start an orchestration run (e.g., agent was stopped), **When** the owner views fire history, **Then** that fire shows a clear error status rather than being silently absent.
3. **Given** a schedule with `consecutive_failures: 3`, **When** the owner queries fire history, **Then** they can see the specific fires that failed and why.

---

### User Story 4 - Receive Orchestration Run Summaries via Webhook (Priority: P3)

A namespace owner has external tooling (a Discord bot, a Datadog integration, a custom dashboard) and wants to receive a summary whenever an orchestration run completes. Today, telemetry webhooks only fire on individual tool calls — the owner needs run-level events to build holistic monitoring without polling.

**Why this priority**: This extends existing telemetry infrastructure to support the new observability data. Lower priority because the API-based queries (Stories 1-3) provide the core value; webhooks add push-based integration for advanced users.

**Independent Test**: Can be tested by configuring a telemetry webhook with orchestration run events enabled, triggering a run, and verifying the webhook payload includes the run summary.

**Acceptance Scenarios**:

1. **Given** a namespace with a telemetry webhook configured for orchestration run events, **When** an orchestration run completes, **Then** the webhook fires with a payload containing: run ID, agent name, trigger source, outcome, duration, steps taken, and limits consumed.
2. **Given** a namespace with a telemetry webhook configured only for tool call events (existing behavior), **When** an orchestration run completes, **Then** no additional webhook fires (backward compatible).
3. **Given** an orchestration run that failed, **When** the webhook fires, **Then** the payload includes the error details sufficient for an external system to create an alert.

---

### Edge Cases

- What happens when an orchestration run is still in progress and the owner queries it? It should show as "running" with steps recorded so far.
- What happens when cron fire history exceeds retention limits? Oldest entries are pruned; the API indicates whether older history exists.
- What happens when an orchestration run produces zero function calls and zero AI reasoning (e.g., immediate error)? It still appears in run history with an appropriate error outcome.
- What happens when the agent is stopped mid-orchestration-run? The run is marked as "cancelled" with the step it was on when stopped.
- What happens when the telemetry webhook endpoint is unreachable? Same fire-and-forget behavior as existing tool call webhooks — no retry, logged as delivery failure.
- What happens when a cron fires while a previous run for the same agent is still active? The system does not gate on concurrent runs. Both fires are recorded, both produce runs, and the overlap is visible in run history. The owner can see concurrency and adjust their schedule interval if needed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST record every orchestration run as a queryable entity with a unique identifier, trigger source (cron schedule, chat message, webhook, manual), agent identity, orchestration mode, start time, end time, and final outcome.
- **FR-002**: System MUST classify orchestration run outcomes as one of: completed, no_action_taken, limit_hit, error, cancelled, timed_out.
- **FR-003**: System MUST record each step within an orchestration run as a structured decision log: decision type (called function, skipped function, no action) plus a reason category from a fixed enum (e.g., quality_threshold_not_met, no_matching_data, limit_reached, error). No free-text AI summaries are stored, to prevent PII exposure from ingested tool results.
- **FR-004**: System MUST record which specific limit was hit when an orchestration run terminates due to a limit (iterations, AI tokens, functions called, execution time) and the consumed vs. configured values.
- **FR-005**: System MUST allow namespace owners to list orchestration runs filtered by agent, trigger type, outcome, and time range.
- **FR-006**: System MUST allow namespace owners to view the full detail of a single orchestration run including all steps, function executions, and outcome.
- **FR-007**: System MUST record each cron schedule fire with timestamp, the orchestration run it produced (if any), and error details if the fire failed to start a run.
- **FR-008**: System MUST allow namespace owners to query fire history for a specific schedule, returning the most recent N fires.
- **FR-009**: System MUST correlate every function execution produced by an orchestration run back to that run, so owners can navigate from execution to run and from run to executions.
- **FR-010**: System MUST support an optional telemetry webhook event type for orchestration run completion, including the run summary in the payload.
- **FR-011**: Enabling orchestration run webhook events MUST NOT affect existing tool call webhook behavior (backward compatible).
- **FR-012**: System MUST retain orchestration run history and cron fire history for a configurable period, with a reasonable default retention window.
- **FR-013**: System MUST expose orchestration run data through the same access patterns as existing namespace management (MCP create server tools and REST API).

### Key Entities

- **Orchestration Run**: A single end-to-end execution of the orchestration pipeline for an agent. Triggered by a cron fire, chat message, webhook, or manual invocation. Contains ordered steps, resource consumption, and a final outcome.
- **Orchestration Step**: A structured decision record within a run. Contains a decision type (called function, skipped function, no action), the target function (if applicable), a reason category from a fixed enum, and the sequence position within the run. No free-text fields — all fields are enumerated or reference existing entities.
- **Schedule Fire**: A record of a cron schedule triggering. Links to the orchestration run it produced (if successful) or captures why no run was started.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Namespace owners can determine why a scheduled agent didn't act within 60 seconds of investigation, without contacting the platform operator.
- **SC-002**: 100% of orchestration runs are recorded and queryable — no "dark" runs that execute but leave no trace.
- **SC-003**: 100% of cron schedule fires are recorded — the gap between `call_count` and `list_executions` results is fully explained by the fire and run history.
- **SC-004**: Any function execution produced by an orchestration run can be traced back to the run and its trigger source in a single query.
- **SC-005**: External monitoring tools can receive orchestration run summaries in real-time via webhook without polling, enabling alerting on failures within seconds of occurrence.
- **SC-006**: Platform operator intervention for "why isn't my agent doing X?" questions is reduced to zero for cases where the answer is observable in run history.

## Assumptions

- The existing `AgentRun` model and telemetry bus provide a foundation to build on rather than replacing from scratch.
- Orchestration run retention defaults to 30 days, matching typical log retention expectations.
- Cron fire history retention defaults to 90 days (fires are small records, higher retention is cheap).
- Steps use structured decision logs (decision type + reason category enum) rather than free-text AI summaries, eliminating PII risk from ingested tool results while preserving diagnostic value.
- MCP tool exposure follows the same pattern as existing `list_executions` / `describe_execution` tools.

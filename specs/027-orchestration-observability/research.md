# Research: Orchestration Pipeline Observability

**Date**: 2026-04-14
**Branch**: `027-orchestration-observability`

## R1: Existing AgentRun Model — Extend vs Replace

**Decision**: Extend the existing `AgentRun` model with new columns.

**Rationale**: `AgentRun` already has the core structure (agent_id, trigger_type, trigger_detail, status, started_at, completed_at, duration_ms, result_summary, error) and is persisted by the orchestrator in `_record_run()`. The `agent_run_id` FK on `Execution` already exists (added in 025-observability-excellence). Adding columns for outcome classification, limits consumed/configured, and orchestration_mode is lower risk than creating a parallel entity.

**Alternatives considered**:
- New `OrchestrationRun` table: Would require migrating existing `AgentRun` data, updating all FK references, and duplicating the recording logic in orchestrator.py. No benefit over extending.
- JSONB metadata column: Would avoid schema changes but lose query filtering capability on outcome/limits.

## R2: Structured Decision Log — Where to Store

**Decision**: Extend the existing `AgentToolCall` model with a `decision_type` and `reason_category` column. The `AgentToolCall` table already records per-step data within a run (sequence_number, tool_name, status). Adding two enum columns captures the decision semantics without a new table.

**Rationale**: `AgentToolCall` is already ordered by sequence_number within an AgentRun and captures tool invocations. Steps where the agent decides NOT to call a function are currently not recorded — adding a row with `decision_type='skip'` and `reason_category='quality_threshold_not_met'` fills this gap. Steps where a function IS called already have a row; we just add `decision_type='call'` (defaulting existing rows).

**Alternatives considered**:
- Separate `OrchestrationStep` table: Additional join, additional migration, no benefit over extending AgentToolCall which already serves this purpose.
- JSONB array on AgentRun: Loses per-step queryability, harder to index.

## R3: Schedule Fire Recording — New Table

**Decision**: Create a new `schedule_fires` table with FK to `agent_schedules` and optional FK to `agent_runs`.

**Rationale**: No existing table records individual cron fires. The `AgentSchedule` model only has `consecutive_failures`, `last_run_at`, and `next_run_at`. A dedicated table is the cleanest approach — each row is a fire event with timestamp, status (fired, error, skipped), error details, and the resulting run ID.

**Alternatives considered**:
- JSONB array on AgentSchedule: Unbounded growth, no indexing, awkward retention.
- Overload AgentRun: Not all fires produce runs (e.g., agent stopped); fires that fail before a run starts need their own record.

## R4: MCP Tool Pattern

**Decision**: Follow the existing `list_executions` / `describe_execution` pattern. New tools: `list_orchestration_runs`, `describe_orchestration_run`, `list_schedule_fires`.

**Rationale**: The MCP create server handler already dispatches tools via a name→method dict. The tool_registry.py defines tool schemas. This pattern is well-established and clients already understand it.

**Alternatives considered**: None — this is the standard pattern.

## R5: Telemetry Webhook Enhancement

**Decision**: Add `orchestration_run` as a new event type in `telemetry_config`. When enabled, `emit_telemetry_event` fires a run-completion payload after the orchestrator records the run. Backward compatible — existing `tool_call` behavior unchanged unless the namespace opts in.

**Rationale**: The telemetry service already supports config-driven event types via `telemetry_config` JSONB on the Namespace model. Adding a new event type requires no schema change — just a new key in the config dict and a new emit call in the orchestrator.

**Alternatives considered**:
- SSE via telemetry bus: Already exists for real-time streaming, but ephemeral (lost on restart). The webhook provides durable push notification.

## R6: Retention Strategy

**Decision**: Background task prunes `agent_runs` older than 30 days and `schedule_fires` older than 90 days. Configurable via namespace-level settings (future, not MVP).

**Rationale**: 500 runs/day × 30 days = 15,000 rows per agent. With ~10 steps per run, ~150,000 tool_call rows per agent. At ~50 active agents, total is <10M rows — well within PostgreSQL comfort zone. Fires are smaller (~1,000 per agent over 90 days).

**Alternatives considered**:
- Partition by month: Premature optimization at current scale.
- No retention: Risk of unbounded growth.

## R7: Outcome Classification

**Decision**: Extend `RUN_STATUSES` from `("running", "completed", "failed", "timeout")` to include `"no_action"` and `"limit_hit"`. The orchestrator already sets status; this adds two new values that map to FR-002's outcome taxonomy.

**Rationale**: The spec requires distinguishing "completed successfully", "completed but chose not to act", "hit a limit", "errored", "cancelled", and "timed out". Mapping: `completed` → completed, `no_action` → no_action_taken, `limit_hit` → limit_hit, `failed` → error, `cancelled` → cancelled (new), `timeout` → timed_out (existing).

**Alternatives considered**:
- Separate `outcome` column: Would require keeping `status` and `outcome` in sync. Better to extend the existing status enum.

## R8: Limits Tracking

**Decision**: Add `limits_consumed` and `limits_configured` JSONB columns to `agent_runs`. Structure: `{"iterations": N, "ai_tokens": N, "functions_called": N, "execution_seconds": N}`.

**Rationale**: The orchestrator already tracks these values in `OrchestrationResult`. Persisting them as JSONB avoids 8 new columns while still being queryable via PostgreSQL JSON operators. The spec requires showing "consumed vs. configured" for limit_hit diagnosis.

**Alternatives considered**:
- 8 individual columns (4 consumed + 4 configured): Verbose, inflexible if new limits are added.
- Only store on limit_hit runs: Loses diagnostic value for runs that completed near limits.

# Data Model: Orchestration Pipeline Observability

**Date**: 2026-04-14
**Branch**: `027-orchestration-observability`

## Entity Changes

### 1. AgentRun (EXTEND existing `agent_runs` table)

Existing columns preserved. New columns:

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `orchestration_mode` | `String(20)` | YES | `NULL` | Which mode was used (direct, reason_first, run_then_reason, procedure) |
| `outcome` | `String(20)` | YES | `NULL` | Structured outcome: completed, no_action, limit_hit, error, cancelled, timeout |
| `limits_consumed` | `JSONB` | YES | `NULL` | `{"iterations": N, "ai_tokens": N, "functions_called": N, "execution_seconds": N}` |
| `limits_configured` | `JSONB` | YES | `NULL` | Same structure — the limits that were in effect for this run |
| `schedule_id` | `UUID FK → agent_schedules.id` | YES | `NULL` | Which schedule triggered this run (if cron-triggered) |
| `functions_called_count` | `Integer` | YES | `NULL` | Count of functions actually called (faster than counting tool_calls) |

**Status values** (extend `RUN_STATUSES`): `running`, `completed`, `failed`, `timeout`, `no_action`, `limit_hit`, `cancelled`

**Indexes**:
- `ix_agent_runs_outcome` on `(outcome)` — for filtering by outcome type
- `ix_agent_runs_schedule` on `(schedule_id)` — for fire→run correlation

**Relationships**:
- `schedule_fires` ← `ScheduleFire.agent_run_id` (one run can have one fire; one fire produces zero or one run)

### 2. AgentToolCall (EXTEND existing `agent_tool_calls` table)

Existing columns preserved. New columns:

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `decision_type` | `String(20)` | NO | `'call'` | One of: `call`, `skip`, `no_action`, `limit_check` |
| `reason_category` | `String(50)` | YES | `NULL` | Enum: `success`, `error`, `quality_threshold_not_met`, `no_matching_data`, `limit_reached`, `rate_limited`, `access_denied`, `timeout`, `not_applicable` |

**Default `'call'`** ensures backward compatibility — existing rows (which are all function calls) get the correct decision_type without backfill.

### 3. ScheduleFire (NEW `schedule_fires` table)

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` PK | NO | `uuid4()` | UUIDMixin |
| `schedule_id` | `UUID FK → agent_schedules.id` | NO | — | Which schedule fired |
| `agent_id` | `UUID FK → agents.id` | NO | — | Denormalized for faster queries without join |
| `fired_at` | `DateTime(tz)` | NO | `now()` | When the fire occurred |
| `status` | `String(20)` | NO | — | `started`, `error`, `skipped` |
| `agent_run_id` | `UUID FK → agent_runs.id` | YES | `NULL` | The run this fire produced (NULL if fire failed to start a run) |
| `error_detail` | `String(500)` | YES | `NULL` | Why the fire failed (e.g., "agent stopped", "function not found") |
| `created_at` | `DateTime(tz)` | NO | `now()` | UUIDMixin |

**Indexes**:
- `ix_schedule_fires_schedule_fired` on `(schedule_id, fired_at)` — primary query path
- `ix_schedule_fires_agent_fired` on `(agent_id, fired_at)` — for agent-level fire listing
- `ix_schedule_fires_created` on `(created_at)` — for retention pruning

**Relationships**:
- `schedule` → `AgentSchedule` (many fires per schedule)
- `agent_run` → `AgentRun` (optional, one-to-one)

## State Transitions

### AgentRun Status

```
running → completed     (normal completion with function calls)
running → no_action     (AI decided not to call any functions)
running → limit_hit     (max_iterations, max_ai_tokens, etc. exceeded)
running → failed        (unrecoverable error during orchestration)
running → timeout       (max_execution_seconds exceeded)
running → cancelled     (agent stopped mid-run)
```

### ScheduleFire Status

```
started     (fire initiated, run in progress or completed)
error       (fire failed before a run could start)
skipped     (fire suppressed — e.g., schedule disabled mid-fire, future use)
```

## Retention

| Table | Default Retention | Pruning Strategy |
|-------|-------------------|------------------|
| `agent_runs` | 30 days | DELETE WHERE created_at < now() - interval '30 days' |
| `agent_tool_calls` | Cascades with agent_runs | ON DELETE CASCADE |
| `schedule_fires` | 90 days | DELETE WHERE created_at < now() - interval '90 days' |

Pruning runs as a periodic background task (daily at low-traffic hours).

## Migration Notes

- `AgentRun` new columns are all nullable — zero-downtime migration, no backfill required
- `AgentToolCall.decision_type` has server_default `'call'` — existing rows get correct value
- `AgentToolCall.reason_category` is nullable — existing rows remain NULL (interpreted as "not categorized")
- `ScheduleFire` is a new table — no data migration
- `RUN_STATUSES` tuple extended in Python model; no DB constraint (validated in application)

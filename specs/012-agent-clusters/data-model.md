# Data Model: Agent Clusters

**Branch**: `012-agent-clusters`

## Existing Tables Modified

### `agents` (cluster spec)

| Column | Change | Type | Notes |
|--------|--------|------|-------|
| `target_replicas` | ADD | `Integer NOT NULL DEFAULT 1` | Desired replica count |
| `container_id` | DEPRECATE | `String(255)` | Moved to `agent_replicas`. Keep nullable for backward compat during migration. |
| `status` | SEMANTIC CHANGE | `String(20)` | Becomes derived: all replicas running → "running", any error → "degraded", all stopped → "stopped", creating → "creating" |

**Migration strategy**: Existing agents with `container_id` get a single `AgentReplica` row created from their current container. `target_replicas` defaults to 1.

### `agent_schedules`

| Column | Change | Type | Notes |
|--------|--------|------|-------|
| `mode` | ADD | `String(10) NOT NULL DEFAULT 'single'` | `single` (exactly-once) or `cluster` (all replicas) |

## New Tables

### `agent_replicas`

Tracks individual running container instances of an agent spec.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | Standard UUIDMixin |
| `agent_id` | `UUID` | FK → agents.id ON DELETE CASCADE | Which cluster this belongs to |
| `replica_name` | `String(63)` | NOT NULL | Verb-animal name (e.g., "daring-duck") |
| `container_id` | `String(255)` | NULLABLE | Docker container ID |
| `status` | `String(20)` | NOT NULL DEFAULT 'creating' | starting, running, stopped, error |
| `last_heartbeat` | `DateTime(tz)` | NULLABLE | Last health check timestamp |
| `created_at` | `DateTime(tz)` | NOT NULL, server_default=now() | When replica was created |

**Indexes**:
- `ix_agent_replicas_agent_id` on `agent_id`
- `uq_agent_replica_name` UNIQUE on `(agent_id, replica_name)`
- `ix_agent_replicas_status` on `(agent_id, status)` — for fast "count running replicas" queries

**Relationships**:
- `Agent.replicas` → `list[AgentReplica]` (one-to-many, cascade delete)
- `AgentReplica.agent` → `Agent` (many-to-one)

### `scheduled_jobs`

Records individual schedule fire events for exactly-once claim semantics.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | Standard UUIDMixin |
| `agent_id` | `UUID` | FK → agents.id ON DELETE CASCADE | Which cluster |
| `schedule_id` | `UUID` | FK → agent_schedules.id ON DELETE CASCADE | Which schedule fired |
| `replica_id` | `UUID` | FK → agent_replicas.id ON DELETE SET NULL, NULLABLE | For cluster-mode: target replica. For single-mode: null until claimed. |
| `fire_time` | `DateTime(tz)` | NOT NULL | When the schedule was supposed to fire |
| `status` | `String(20)` | NOT NULL DEFAULT 'pending' | pending, claimed, running, complete, failed |
| `claimed_by` | `UUID` | FK → agent_replicas.id ON DELETE SET NULL, NULLABLE | Which replica claimed this job |
| `claimed_at` | `DateTime(tz)` | NULLABLE | When it was claimed |
| `completed_at` | `DateTime(tz)` | NULLABLE | When execution finished |
| `error` | `Text` | NULLABLE | Error message if failed |
| `created_at` | `DateTime(tz)` | NOT NULL, server_default=now() | Row creation time |

**Indexes**:
- `ix_scheduled_jobs_pending` on `(agent_id, status)` WHERE `status = 'pending'` — partial index for fast claim queries
- `ix_scheduled_jobs_schedule` on `(schedule_id, fire_time)` — dedup check
- `ix_scheduled_jobs_cleanup` on `(status, completed_at)` — for retention cleanup

**Claim query pattern**:
```sql
UPDATE scheduled_jobs
SET status = 'claimed', claimed_by = :replica_id, claimed_at = now()
WHERE id = (
    SELECT id FROM scheduled_jobs
    WHERE agent_id = :agent_id AND status = 'pending' AND replica_id IS NULL
    ORDER BY fire_time ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING *;
```

## Entity Relationship

```
Account 1──N Agent (cluster spec)
Agent 1──N AgentReplica
Agent 1──N AgentSchedule
Agent 1──N AgentWebhook
Agent 1──N AgentState (shared K/V)
Agent 1──N AgentChannel
Agent 1──N AgentRun
AgentSchedule 1──N ScheduledJob
AgentReplica 0──N ScheduledJob (claimed_by)
```

## State Transitions

### Agent (cluster-level derived status)

```
creating → running    (all replicas healthy)
creating → degraded   (some replicas failed during creation)
creating → error      (all replicas failed)
running → degraded    (one or more replicas unhealthy)
running → stopped     (operator stops all replicas)
degraded → running    (unhealthy replicas recovered/replaced)
degraded → stopped    (operator stops all replicas)
stopped → running     (operator starts cluster)
any → destroying      (operator destroys cluster)
```

### AgentReplica (per-container status)

```
creating → running    (container started, first heartbeat received)
creating → error      (Docker create/start failed)
running → stopped     (graceful stop via operator or scale-down)
running → error       (heartbeat timeout or container crash)
stopped → running     (operator restarts specific replica)
error → running       (auto-replacement or manual restart)
```

### ScheduledJob (per-fire-event status)

```
pending → claimed     (replica locks the row)
claimed → running     (execution started)
running → complete    (execution succeeded)
running → failed      (execution errored)
pending → failed      (expired — no replica claimed within timeout)
```

## Migration Plan

### Alembic Migration: `add_agent_clusters`

1. Add `target_replicas` column to `agents` (default 1)
2. Add `mode` column to `agent_schedules` (default 'single')
3. Create `agent_replicas` table
4. Create `scheduled_jobs` table
5. **Data migration**: For each existing agent with a `container_id`:
   - Generate a verb-animal replica name
   - Insert an `AgentReplica` row with the existing `container_id` and status
   - Set `target_replicas = 1`
6. After migration stabilizes: `container_id` on `agents` can be dropped in a future migration

## Affected Existing Files

| File | Changes |
|------|---------|
| `src/mcpworks_api/models/agent.py` | Add `AgentReplica`, `ScheduledJob` models; add columns to `Agent`, `AgentSchedule` |
| `src/mcpworks_api/services/agent_service.py` | `scale_agent()`, rolling restart, LIFO teardown, replica-aware create/start/stop/destroy |
| `src/mcpworks_api/tasks/scheduler.py` | Job creation (single vs cluster mode), claim via `SKIP LOCKED` |
| `src/mcpworks_api/mcp/create_handler.py` | `scale_agent` tool handler, `replica` param on `chat_with_agent`/`start_agent`/`stop_agent` |
| `src/mcpworks_api/mcp/tool_registry.py` | `scale_agent` tool definition, updated schemas |
| `src/mcpworks_api/schemas/agent.py` | `AgentReplicaResponse`, updated `AgentResponse` with replicas list |
| `docs/guide.md` | Agent clusters section |
| `docs/llm-reference.md` | `scale_agent` tool, updated `chat_with_agent` schema |

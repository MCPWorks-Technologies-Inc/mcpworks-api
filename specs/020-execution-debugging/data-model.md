# Data Model: Execution Debugging

## Modified Entity: Execution

**Table**: `executions` (existing)

**New columns**:

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `namespace_id` | UUID (FK → namespaces.id) | No | — | Namespace the function belongs to |
| `service_name` | String(255) | Yes | NULL | Service name (denormalized for fast queries) |
| `function_name` | String(255) | Yes | NULL | Function name (denormalized for fast queries) |
| `execution_time_ms` | Integer | Yes | NULL | Execution duration in milliseconds |

**Extended use of existing columns**:

| Column | Current Use | New Use |
|--------|------------|---------|
| `backend_metadata` | Mostly empty | Store `stdout` (truncated 4KB), `stderr` (truncated 4KB), `sandbox_tier` |
| `workflow_id` | Legacy workflow reference | Repurposed as execution_id string for backward compat |

**New indexes**:

| Index | Columns | Purpose |
|-------|---------|---------|
| `ix_executions_namespace_id` | namespace_id | Namespace-scoped queries |
| `ix_executions_ns_function` | namespace_id, service_name, function_name | Function-specific queries |
| `ix_executions_ns_status` | namespace_id, status | Status filtering |
| `ix_executions_ns_created` | namespace_id, created_at DESC | Time-range queries |

## No New Tables

Procedure execution records already exist in the `procedure_executions` table with full step detail. No new tables needed.

## Execution Record Lifecycle

```
Function call arrives at RunMCPHandler.dispatch_tool()
  → Create Execution record (status: running)
  → Execute via backend
  → Update record (status: completed/failed, result/error, stdout/stderr in backend_metadata)
```

## Retention

Records older than 30 days are pruned by a periodic background task. The `created_at` index supports efficient deletion.

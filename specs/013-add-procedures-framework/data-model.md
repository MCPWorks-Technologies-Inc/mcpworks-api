# Data Model: Procedures Framework

**Branch**: `013-add-procedures-framework`

## New Tables

### `procedures`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | Standard UUIDMixin |
| `namespace_id` | `UUID` | FK → namespaces.id ON DELETE CASCADE | Which namespace |
| `service_id` | `UUID` | FK → namespace_services.id ON DELETE CASCADE | Which service (same hierarchy as functions) |
| `name` | `String(255)` | NOT NULL | Procedure name |
| `description` | `Text` | NULLABLE | Human-readable description |
| `active_version` | `Integer` | NOT NULL DEFAULT 1 | Current active version number |
| `is_deleted` | `Boolean` | NOT NULL DEFAULT false | Soft delete (preserves execution records) |
| `created_at` | `DateTime(tz)` | NOT NULL, server_default=now() | |
| `updated_at` | `DateTime(tz)` | NOT NULL, server_default=now() | |

**Indexes**:
- `uq_procedure_service_name` UNIQUE on `(service_id, name)` WHERE `is_deleted = false`
- `ix_procedures_namespace_id` on `namespace_id`

### `procedure_versions`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | Standard UUIDMixin |
| `procedure_id` | `UUID` | FK → procedures.id ON DELETE CASCADE | Parent procedure |
| `version` | `Integer` | NOT NULL | Version number (1, 2, 3...) |
| `steps` | `JSONB` | NOT NULL | Array of step definitions (see schema below) |
| `created_by` | `String(255)` | NULLABLE | Who created this version |
| `created_at` | `DateTime(tz)` | NOT NULL, server_default=now() | |

**Indexes**:
- `uq_procedure_version` UNIQUE on `(procedure_id, version)`
- `ix_procedure_versions_procedure_id` on `procedure_id`

**Steps JSONB schema**:
```json
[
  {
    "step_number": 1,
    "name": "step-name",
    "function_ref": "service.function-name",
    "instructions": "What the LLM should do at this step",
    "failure_policy": "required|allowed|skip",
    "max_retries": 3,
    "validation": {"required_fields": ["field1", "field2"]}
  }
]
```

### `procedure_executions`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | Standard UUIDMixin |
| `procedure_id` | `UUID` | FK → procedures.id ON DELETE CASCADE | Which procedure |
| `procedure_version` | `Integer` | NOT NULL | Which version was executed |
| `agent_id` | `UUID` | FK → agents.id ON DELETE SET NULL, NULLABLE | Which agent ran it |
| `trigger_type` | `String(20)` | NOT NULL | cron, webhook, manual, channel, heartbeat |
| `status` | `String(20)` | NOT NULL DEFAULT 'running' | running, completed, failed |
| `current_step` | `Integer` | NOT NULL DEFAULT 1 | Which step is currently executing |
| `step_results` | `JSONB` | NOT NULL DEFAULT '[]' | Array of step result objects |
| `input_context` | `JSONB` | NULLABLE | Initial context (e.g., webhook payload) |
| `started_at` | `DateTime(tz)` | NOT NULL, server_default=now() | |
| `completed_at` | `DateTime(tz)` | NULLABLE | |
| `error` | `Text` | NULLABLE | Overall error message if failed |
| `created_at` | `DateTime(tz)` | NOT NULL, server_default=now() | |

**Indexes**:
- `ix_procedure_executions_procedure_id` on `procedure_id`
- `ix_procedure_executions_agent_id` on `agent_id`
- `ix_procedure_executions_status` on `(procedure_id, status)`

**Step results JSONB schema**:
```json
[
  {
    "step_number": 1,
    "name": "authenticate",
    "status": "success|failed|skipped|running|pending",
    "function_called": "social.bluesky-auth",
    "result": {},
    "error": null,
    "attempt_count": 1,
    "attempts": [
      {
        "attempt": 1,
        "started_at": "2026-03-29T10:00:00Z",
        "completed_at": "2026-03-29T10:00:01Z",
        "success": true,
        "error": null
      }
    ]
  }
]
```

## Existing Tables Modified

### `agent_schedules`

- `ORCHESTRATION_MODES` tuple: add `"procedure"`
- Add `procedure_name` column: `String(255)`, NULLABLE, required when `orchestration_mode = 'procedure'`

### `agent_webhooks`

- Add `procedure_name` column: `String(255)`, NULLABLE, required when `orchestration_mode = 'procedure'`

## Entity Relationship

```
Namespace 1──N NamespaceService 1──N Procedure
Procedure 1──N ProcedureVersion
Procedure 1──N ProcedureExecution
Agent 0──N ProcedureExecution
```

## State Transitions

### ProcedureExecution

```
running → completed    (all required steps succeeded)
running → failed       (a required step failed after retries)
```

### Step Result (within execution)

```
pending → running      (step presented to LLM)
running → success      (function called, result captured, validation passed)
running → failed       (function failed after retries, or validation failed)
running → skipped      (failure_policy=skip, function failed on first attempt)
```

## Migration Plan

### Alembic Migration: `add_procedures`

1. Create `procedures` table
2. Create `procedure_versions` table
3. Create `procedure_executions` table
4. Add `procedure_name` column to `agent_schedules` (nullable)
5. Add `procedure_name` column to `agent_webhooks` (nullable)
6. Update `ORCHESTRATION_MODES` in code (not a migration — code change)

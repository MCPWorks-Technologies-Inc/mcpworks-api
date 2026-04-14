# REST API Contracts: Orchestration Pipeline Observability

## Endpoints

### GET /v1/agents/{agent_id}/runs

List orchestration runs for an agent.

**Query Parameters**:
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `trigger_type` | string | no | — | Filter: cron, webhook, manual, ai, heartbeat |
| `outcome` | string | no | — | Filter: completed, no_action, limit_hit, failed, timeout, cancelled |
| `since` | datetime | no | — | Only runs after this timestamp |
| `until` | datetime | no | — | Only runs before this timestamp |
| `limit` | int | no | 20 | Max results (1-100) |
| `offset` | int | no | 0 | Pagination offset |

**Response 200**:
```json
{
  "runs": [
    {
      "id": "uuid",
      "agent_id": "uuid",
      "trigger_type": "cron",
      "trigger_detail": "orchestration:cron",
      "orchestration_mode": "run_then_reason",
      "schedule_id": "uuid | null",
      "outcome": "completed",
      "status": "completed",
      "functions_called_count": 3,
      "started_at": "2026-04-14T10:00:00Z",
      "completed_at": "2026-04-14T10:00:45Z",
      "duration_ms": 45000,
      "error": null
    }
  ],
  "total": 142,
  "limit": 20,
  "offset": 0
}
```

### GET /v1/agents/{agent_id}/runs/{run_id}

Get full detail of a single orchestration run.

**Response 200**:
```json
{
  "id": "uuid",
  "agent_id": "uuid",
  "trigger_type": "cron",
  "trigger_detail": "orchestration:cron",
  "orchestration_mode": "run_then_reason",
  "schedule_id": "uuid | null",
  "outcome": "completed",
  "status": "completed",
  "started_at": "2026-04-14T10:00:00Z",
  "completed_at": "2026-04-14T10:00:45Z",
  "duration_ms": 45000,
  "functions_called_count": 3,
  "limits_consumed": {
    "iterations": 4,
    "ai_tokens": 12500,
    "functions_called": 3,
    "execution_seconds": 45
  },
  "limits_configured": {
    "iterations": 25,
    "ai_tokens": 1000000,
    "functions_called": 25,
    "execution_seconds": 300
  },
  "error": null,
  "steps": [
    {
      "sequence_number": 1,
      "decision_type": "call",
      "tool_name": "find-shareable-news",
      "reason_category": "success",
      "duration_ms": 5200,
      "status": "success"
    },
    {
      "sequence_number": 2,
      "decision_type": "call",
      "tool_name": "post-to-bluesky",
      "reason_category": "success",
      "duration_ms": 1200,
      "status": "success"
    },
    {
      "sequence_number": 3,
      "decision_type": "skip",
      "tool_name": "send-discord-report",
      "reason_category": "quality_threshold_not_met",
      "duration_ms": null,
      "status": "success"
    }
  ]
}
```

### GET /v1/schedules/{schedule_id}/fires

List fire history for a schedule.

**Query Parameters**:
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `status` | string | no | — | Filter: started, error, skipped |
| `since` | datetime | no | — | Only fires after this timestamp |
| `limit` | int | no | 20 | Max results (1-100) |
| `offset` | int | no | 0 | Pagination offset |

**Response 200**:
```json
{
  "fires": [
    {
      "id": "uuid",
      "schedule_id": "uuid",
      "agent_id": "uuid",
      "fired_at": "2026-04-14T10:00:00Z",
      "status": "started",
      "agent_run_id": "uuid",
      "error_detail": null
    }
  ],
  "total": 48,
  "limit": 20,
  "offset": 0
}
```

## MCP Tool Contracts

### list_orchestration_runs

**Description** (≤20 tokens): List orchestration runs for an agent with optional filters.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "agent": {"type": "string", "description": "Agent name"},
    "trigger_type": {"type": "string", "enum": ["cron", "webhook", "manual", "ai", "heartbeat"]},
    "outcome": {"type": "string", "enum": ["completed", "no_action", "limit_hit", "failed", "timeout", "cancelled"]},
    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50}
  },
  "required": ["agent"]
}
```

**Output**: Summary list matching REST `/runs` response format.

### describe_orchestration_run

**Description** (≤20 tokens): Get full detail of an orchestration run including steps and limits.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "run_id": {"type": "string", "description": "Orchestration run ID"}
  },
  "required": ["run_id"]
}
```

**Output**: Full run detail matching REST `/runs/{run_id}` response format.

### list_schedule_fires

**Description** (≤20 tokens): List fire history for a cron schedule.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "agent": {"type": "string", "description": "Agent name"},
    "schedule_id": {"type": "string", "description": "Schedule ID"},
    "status": {"type": "string", "enum": ["started", "error", "skipped"]},
    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50}
  },
  "required": ["agent"]
}
```

**Output**: Fire history list matching REST `/fires` response format.

## Telemetry Webhook Event

### Event Type: `orchestration_run`

Added to `telemetry_config` as opt-in:
```json
{
  "events": ["tool_call", "orchestration_run"]
}
```

**Payload**:
```json
{
  "event_type": "orchestration_run",
  "timestamp": "2026-04-14T10:00:45Z",
  "namespace": "mcpworkssocial",
  "agent": "social-bot",
  "run_id": "uuid",
  "trigger_type": "cron",
  "orchestration_mode": "run_then_reason",
  "outcome": "completed",
  "duration_ms": 45000,
  "functions_called_count": 3,
  "steps_count": 4,
  "limits_consumed": {"iterations": 4, "ai_tokens": 12500, "functions_called": 3, "execution_seconds": 45},
  "limits_configured": {"iterations": 25, "ai_tokens": 1000000, "functions_called": 25, "execution_seconds": 300},
  "error": null
}
```

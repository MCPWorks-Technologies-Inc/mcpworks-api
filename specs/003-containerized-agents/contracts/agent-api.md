# API Contracts: Agent Management

**Branch**: `003-containerized-agents` | **Date**: 2026-03-11

## Agent Lifecycle Endpoints

### Create Agent

```
POST /api/v1/agents
Authorization: Bearer {jwt}

Request:
{
  "name": "dogedetective",
  "display_name": "Doge Detective",
  "memory_limit_mb": 256,        // optional, defaults to tier allocation
  "cpu_limit": 0.25               // optional, defaults to tier allocation
}

Response 201:
{
  "id": "uuid",
  "name": "dogedetective",
  "display_name": "Doge Detective",
  "namespace": "dogedetective",
  "status": "creating",
  "memory_limit_mb": 256,
  "cpu_limit": 0.25,
  "created_at": "2026-03-11T00:00:00Z"
}

Response 402: { "error": "agent_tier_required", "detail": "Account must be on an agent-enabled tier" }
Response 409: { "error": "agent_slots_exhausted", "detail": "All 5 agent slots are in use", "used": 5, "max": 5 }
Response 409: { "error": "name_taken", "detail": "Agent name already in use" }
```

### List Agents

```
GET /api/v1/agents
Authorization: Bearer {jwt}

Response 200:
{
  "agents": [
    {
      "id": "uuid",
      "name": "dogedetective",
      "status": "running",
      "memory_limit_mb": 256,
      "cpu_limit": 0.25,
      "created_at": "2026-03-11T00:00:00Z"
    }
  ],
  "slots": { "used": 1, "max": 5 }
}
```

### Get Agent

```
GET /api/v1/agents/{agent_id}
Authorization: Bearer {jwt}

Response 200:
{
  "id": "uuid",
  "name": "dogedetective",
  "display_name": "Doge Detective",
  "namespace": "dogedetective",
  "status": "running",
  "container_id": "abc123",
  "memory_limit_mb": 256,
  "cpu_limit": 0.25,
  "ai_engine": "anthropic",
  "ai_model": "claude-haiku-4-5-20251001",
  "enabled": true,
  "schedules_count": 2,
  "webhooks_count": 1,
  "state_size_bytes": 4096,
  "channels": ["discord"],
  "created_at": "2026-03-11T00:00:00Z",
  "updated_at": "2026-03-11T00:00:00Z"
}
```

### Start Agent

```
POST /api/v1/agents/{agent_id}/start
Authorization: Bearer {jwt}

Response 200: { "id": "uuid", "status": "running" }
Response 409: { "error": "invalid_state", "detail": "Agent is already running" }
```

### Stop Agent

```
POST /api/v1/agents/{agent_id}/stop
Authorization: Bearer {jwt}

Response 200: { "id": "uuid", "status": "stopped" }
Response 409: { "error": "invalid_state", "detail": "Agent is not running" }
```

### Destroy Agent

```
DELETE /api/v1/agents/{agent_id}
Authorization: Bearer {jwt}

Response 200: { "id": "uuid", "status": "destroyed", "namespace_deleted": true }
```

### Clone Agent

```
POST /api/v1/agents/{agent_id}/clone
Authorization: Bearer {jwt}

Request:
{
  "new_name": "dogedetective-v2"
}

Response 201:
{
  "id": "new-uuid",
  "name": "dogedetective-v2",
  "cloned_from": "uuid",
  "status": "creating",
  "schedules_copied": 3,
  "functions_copied": 5,
  "state_keys_copied": 12,
  "note": "Schedules are disabled by default on cloned agents"
}

Response 409: { "error": "agent_slots_exhausted" }
```

## AI Configuration

### Configure AI Engine

```
PUT /api/v1/agents/{agent_id}/ai
Authorization: Bearer {jwt}

Request:
{
  "engine": "anthropic",
  "model": "claude-haiku-4-5-20251001",
  "api_key": "sk-ant-..."  // pragma: allowlist secret
}

Response 200: { "id": "uuid", "ai_engine": "anthropic", "ai_model": "claude-haiku-4-5-20251001" }
```

### Remove AI Configuration

```
DELETE /api/v1/agents/{agent_id}/ai
Authorization: Bearer {jwt}

Response 200: { "id": "uuid", "ai_engine": null, "ai_model": null }
```

## Schedules

### Add Schedule

```
POST /api/v1/agents/{agent_id}/schedules
Authorization: Bearer {jwt}

Request:
{
  "function_name": "check-price",
  "cron_expression": "*/5 * * * *",
  "timezone": "America/Toronto",
  "failure_policy": {
    "strategy": "auto_disable",
    "max_failures": 5
  }
}

Response 201:
{
  "id": "uuid",
  "function_name": "check-price",
  "cron_expression": "*/5 * * * *",
  "timezone": "America/Toronto",
  "failure_policy": { "strategy": "auto_disable", "max_failures": 5 },
  "enabled": true,
  "next_run_at": "2026-03-11T00:05:00Z"
}

Response 422: { "error": "interval_too_short", "detail": "Minimum interval for builder tier is 5 minutes", "min_seconds": 300 }
Response 422: { "error": "failure_policy_required", "detail": "Schedule must include a failure_policy with strategy" }
```

### List Schedules

```
GET /api/v1/agents/{agent_id}/schedules
Authorization: Bearer {jwt}

Response 200:
{
  "schedules": [
    {
      "id": "uuid",
      "function_name": "check-price",
      "cron_expression": "*/5 * * * *",
      "enabled": true,
      "last_run_at": "2026-03-11T00:00:00Z",
      "next_run_at": "2026-03-11T00:05:00Z"
    }
  ]
}
```

### Remove Schedule

```
DELETE /api/v1/agents/{agent_id}/schedules/{schedule_id}
Authorization: Bearer {jwt}

Response 200: { "deleted": true }
```

## Webhooks

### Add Webhook

```
POST /api/v1/agents/{agent_id}/webhooks
Authorization: Bearer {jwt}

Request:
{
  "path": "price-alert",
  "handler_function_name": "handle-price-alert",
  "secret": "<webhook-secret>"                      // optional
}

Response 201:
{
  "id": "uuid",
  "path": "price-alert",
  "handler_function_name": "handle-price-alert",
  "has_secret": true,
  "url": "https://dogedetective.agent.mcpworks.io/webhook/price-alert",
  "enabled": true
}
```

### Remove Webhook

```
DELETE /api/v1/agents/{agent_id}/webhooks/{webhook_id}
Authorization: Bearer {jwt}

Response 200: { "deleted": true }
```

### Webhook Ingress (external caller)

```
POST https://{agent-name}.agent.mcpworks.io/webhook/{path}
X-Webhook-Secret: whsec_...    // if secret configured
Content-Type: application/json

{body}

Response 200: { "run_id": "uuid", "status": "accepted" }
Response 404: { "error": "agent_not_found" }
Response 403: { "error": "invalid_webhook_secret" }
Response 413: { "error": "payload_too_large", "max_bytes": 262144 }
Response 503: { "error": "agent_not_running" }
```

## State

### Set State

```
PUT /api/v1/agents/{agent_id}/state/{key}
Authorization: Bearer {jwt} OR Agent API key

Request:
{
  "value": <any JSON value>
}

Response 200: { "key": "last_price", "size_bytes": 24, "updated_at": "2026-03-11T00:00:00Z" }
Response 413: { "error": "state_limit_exceeded", "current_bytes": 10485760, "max_bytes": 10485760 }
```

### Get State

```
GET /api/v1/agents/{agent_id}/state/{key}
Authorization: Bearer {jwt} OR Agent API key

Response 200: { "key": "last_price", "value": 42150.50, "size_bytes": 24, "updated_at": "2026-03-11T00:00:00Z" }
Response 404: { "error": "key_not_found" }
```

### Delete State

```
DELETE /api/v1/agents/{agent_id}/state/{key}
Authorization: Bearer {jwt} OR Agent API key

Response 200: { "deleted": true }
```

### List State Keys

```
GET /api/v1/agents/{agent_id}/state
Authorization: Bearer {jwt} OR Agent API key

Response 200:
{
  "keys": [
    { "key": "last_price", "size_bytes": 24, "updated_at": "2026-03-11T00:00:00Z" },
    { "key": "alert_history", "size_bytes": 1024, "updated_at": "2026-03-11T00:00:00Z" }
  ],
  "total_size_bytes": 1048,
  "max_size_bytes": 10485760
}
```

## Channels

### Add Channel

```
POST /api/v1/agents/{agent_id}/channels
Authorization: Bearer {jwt}

Request:
{
  "channel_type": "discord",
  "config": {
    "bot_token": "...",
    "channel_id": "123456789",
    "guild_id": "987654321"
  }
}

Response 201: { "id": "uuid", "channel_type": "discord", "enabled": true }
Response 409: { "error": "channel_exists", "detail": "Discord channel already configured for this agent" }
```

### Remove Channel

```
DELETE /api/v1/agents/{agent_id}/channels/{channel_id}
Authorization: Bearer {jwt}

Response 200: { "deleted": true }
```

## Function Locking

### Lock Function

```
POST /api/v1/namespaces/{ns}/functions/{fn}/lock
Authorization: Bearer {jwt} (admin scope)

Response 200: { "function": "check-price", "locked": true, "locked_by": "user-uuid", "locked_at": "2026-03-11T00:00:00Z" }
Response 403: { "error": "admin_required" }
```

### Unlock Function

```
DELETE /api/v1/namespaces/{ns}/functions/{fn}/lock
Authorization: Bearer {jwt} (admin scope)

Response 200: { "function": "check-price", "locked": false }
```

## Agent Runs

### List Runs

```
GET /api/v1/agents/{agent_id}/runs?limit=50&offset=0
Authorization: Bearer {jwt}

Response 200:
{
  "runs": [
    {
      "id": "uuid",
      "trigger_type": "cron",
      "trigger_detail": "*/5 * * * *",
      "function_name": "check-price",
      "status": "completed",
      "started_at": "2026-03-11T00:05:00Z",
      "duration_ms": 1234,
      "result_summary": "Price checked: $42,150.50"
    }
  ],
  "total": 150,
  "retention_days": 30
}
```

## Admin Endpoints

### Upgrade Account to Agent Tier

```
POST /api/v1/admin/accounts/{account_id}/upgrade
X-Admin-Key: {admin_key}

Request:
{
  "tier": "pro-agent",
  "billing_period": "monthly"
}

Response 200: { "account_id": "uuid", "tier": "pro-agent", "agent_slots": 5, "audit_logged": true }
Response 409: { "error": "agents_exist", "detail": "Cannot downgrade: 2 agents still exist. Destroy them first." }
```

### List All Agents (Platform-wide)

```
GET /api/v1/admin/agents?limit=50&offset=0
X-Admin-Key: {admin_key}

Response 200:
{
  "agents": [
    {
      "id": "uuid",
      "name": "dogedetective",
      "account_id": "uuid",
      "account_email": "user@example.com",
      "status": "running",
      "memory_limit_mb": 512,
      "cpu_limit": 0.5,
      "uptime_seconds": 86400
    }
  ],
  "total": 3
}
```

### Force Restart Agent

```
POST /api/v1/admin/agents/{agent_id}/restart
X-Admin-Key: {admin_key}

Response 200: { "id": "uuid", "status": "running", "restarted": true }
```

### Force Destroy Agent

```
DELETE /api/v1/admin/agents/{agent_id}
X-Admin-Key: {admin_key}

Response 200: { "id": "uuid", "status": "destroyed" }
```

### Agent Fleet Health

```
GET /api/v1/admin/agents/health
X-Admin-Key: {admin_key}

Response 200:
{
  "total_agents": 8,
  "running": 6,
  "stopped": 1,
  "error": 1,
  "total_memory_mb": 2048,
  "total_cpu": 2.0,
  "available_memory_mb": 4752,
  "available_cpu": 1.2,
  "agents": [
    {
      "id": "uuid",
      "name": "dogedetective",
      "status": "running",
      "container_status": "healthy",
      "uptime_seconds": 86400,
      "restart_count": 0,
      "memory_usage_mb": 180,
      "cpu_usage_percent": 5.2
    }
  ]
}
```

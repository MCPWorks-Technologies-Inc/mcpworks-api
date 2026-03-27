# MCP Tool Contracts: Agent Clusters

**Branch**: `012-agent-clusters`

## New Tool: `scale_agent`

```json
{
  "name": "scale_agent",
  "description": "Scale an agent to a target number of replicas. Each replica runs the same configuration (functions, AI engine, schedules, webhooks). Each replica counts as one agent slot toward your tier limit.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": {
        "type": "string",
        "description": "Agent name"
      },
      "replicas": {
        "type": "integer",
        "minimum": 0,
        "description": "Target replica count. 0 stops all replicas without destroying the agent."
      }
    },
    "required": ["name", "replicas"]
  }
}
```

**Response (success)**:
```json
{
  "agent": "social-monitor",
  "target_replicas": 3,
  "replicas": [
    {"name": "daring-duck", "status": "running"},
    {"name": "swift-falcon", "status": "running"},
    {"name": "calm-crane", "status": "starting"}
  ],
  "slots_used": 5,
  "slots_limit": 20
}
```

**Response (error — tier limit)**:
```json
{
  "error": "agent_slot_limit",
  "message": "Scaling to 5 replicas would use 8 slots (limit: 5)",
  "slots_used": 3,
  "slots_limit": 5
}
```

## Modified Tool: `chat_with_agent`

```json
{
  "name": "chat_with_agent",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": {
        "type": "string",
        "description": "Agent name"
      },
      "message": {
        "type": "string",
        "description": "Message to send"
      },
      "replica": {
        "type": "string",
        "description": "Target a specific replica for session continuity. Omit for any available replica."
      }
    },
    "required": ["name", "message"]
  }
}
```

**Response** (adds `replica` field):
```json
{
  "response": "I found 3 brand mentions today...",
  "replica": "daring-duck",
  "agent": "social-monitor"
}
```

## Modified Tool: `start_agent` / `stop_agent`

Adds optional `replica` parameter:

```json
{
  "properties": {
    "name": {"type": "string", "description": "Agent name"},
    "replica": {"type": "string", "description": "Target a specific replica. Omit to target entire cluster."}
  },
  "required": ["name"]
}
```

## Modified Tool: `add_schedule`

Adds `mode` parameter:

```json
{
  "properties": {
    "name": {"type": "string"},
    "function_name": {"type": "string"},
    "cron_expression": {"type": "string"},
    "mode": {
      "type": "string",
      "enum": ["single", "cluster"],
      "default": "single",
      "description": "single: exactly one replica executes (default). cluster: all replicas execute independently."
    }
  }
}
```

## Modified Tool: `describe_agent`

Response adds `target_replicas` and `replicas` fields:

```json
{
  "name": "social-monitor",
  "status": "running",
  "target_replicas": 3,
  "replicas": [
    {
      "name": "daring-duck",
      "status": "running",
      "last_heartbeat": "2026-03-27T14:30:00Z",
      "created_at": "2026-03-27T10:00:00Z"
    },
    {
      "name": "swift-falcon",
      "status": "running",
      "last_heartbeat": "2026-03-27T14:30:05Z",
      "created_at": "2026-03-27T12:00:00Z"
    }
  ],
  "schedules": [...],
  "ai_engine": "anthropic",
  "ai_model": "claude-sonnet-4-6"
}
```

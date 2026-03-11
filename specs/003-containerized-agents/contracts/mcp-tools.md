# MCP Tool Contracts: Agent Management

**Branch**: `003-containerized-agents` | **Date**: 2026-03-11

All tools below are added to `CreateMCPHandler` and only visible to users on agent-enabled tiers.

## Phase A Tools (Agent Shell)

### make_agent

```json
{
  "name": "make_agent",
  "description": "Create a new autonomous agent with its own namespace and container",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": { "type": "string", "description": "Agent name (lowercase, alphanumeric + hyphens, 1-63 chars)" },
      "display_name": { "type": "string", "description": "Human-readable label (optional)" }
    },
    "required": ["name"]
  }
}
```

### list_agents

```json
{
  "name": "list_agents",
  "description": "List all agents for your account with status and slot usage",
  "inputSchema": { "type": "object", "properties": {} }
}
```

### describe_agent

```json
{
  "name": "describe_agent",
  "description": "Get full details of an agent: status, schedules, webhooks, channels, state usage",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": { "type": "string", "description": "Agent name" }
    },
    "required": ["name"]
  }
}
```

### start_agent

```json
{
  "name": "start_agent",
  "description": "Start a stopped agent container",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": { "type": "string", "description": "Agent name" }
    },
    "required": ["name"]
  }
}
```

### stop_agent

```json
{
  "name": "stop_agent",
  "description": "Stop a running agent container",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": { "type": "string", "description": "Agent name" }
    },
    "required": ["name"]
  }
}
```

### destroy_agent

```json
{
  "name": "destroy_agent",
  "description": "Permanently destroy an agent, its container, namespace, and all data",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": { "type": "string", "description": "Agent name" },
      "confirm": { "type": "boolean", "description": "Must be true to confirm destruction" }
    },
    "required": ["name", "confirm"]
  }
}
```

## Phase B Tools (Webhooks + Scheduling)

### add_schedule

```json
{
  "name": "add_schedule",
  "description": "Add a cron schedule to an agent. Requires a failure_policy.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string" },
      "function_name": { "type": "string" },
      "cron_expression": { "type": "string", "description": "5-field cron (e.g., '*/5 * * * *')" },
      "timezone": { "type": "string", "default": "UTC" },
      "failure_policy": {
        "type": "object",
        "description": "Required. Strategy: 'continue', 'auto_disable' (with max_failures), or 'backoff' (with backoff_factor)",
        "properties": {
          "strategy": { "type": "string", "enum": ["continue", "auto_disable", "backoff"] },
          "max_failures": { "type": "integer" },
          "backoff_factor": { "type": "number" }
        },
        "required": ["strategy"]
      }
    },
    "required": ["agent_name", "function_name", "cron_expression", "failure_policy"]
  }
}
```

### remove_schedule

```json
{
  "name": "remove_schedule",
  "description": "Remove a cron schedule from an agent",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string" },
      "schedule_id": { "type": "string" }
    },
    "required": ["agent_name", "schedule_id"]
  }
}
```

### add_webhook

```json
{
  "name": "add_webhook",
  "description": "Register a webhook path on an agent that triggers a handler function",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string" },
      "path": { "type": "string", "description": "URL path segment (e.g., 'price-alert')" },
      "handler_function_name": { "type": "string" },
      "secret": { "type": "string", "description": "Optional webhook secret for verification" }
    },
    "required": ["agent_name", "path", "handler_function_name"]
  }
}
```

### remove_webhook

```json
{
  "name": "remove_webhook",
  "description": "Remove a webhook registration from an agent",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string" },
      "webhook_id": { "type": "string" }
    },
    "required": ["agent_name", "webhook_id"]
  }
}
```

## Phase C Tools (State + Locking + Cloning)

### set_agent_state

```json
{
  "name": "set_agent_state",
  "description": "Set a key-value pair in an agent's persistent state",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string" },
      "key": { "type": "string" },
      "value": { "description": "Any JSON-serializable value" }
    },
    "required": ["agent_name", "key", "value"]
  }
}
```

### get_agent_state

```json
{
  "name": "get_agent_state",
  "description": "Get a value from an agent's persistent state",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string" },
      "key": { "type": "string", "description": "State key, or omit to list all keys" }
    },
    "required": ["agent_name"]
  }
}
```

### lock_function

```json
{
  "name": "lock_function",
  "description": "Lock a function so only admin API keys can modify it",
  "inputSchema": {
    "type": "object",
    "properties": {
      "namespace": { "type": "string" },
      "function_name": { "type": "string" }
    },
    "required": ["namespace", "function_name"]
  }
}
```

### unlock_function

```json
{
  "name": "unlock_function",
  "description": "Unlock a previously locked function",
  "inputSchema": {
    "type": "object",
    "properties": {
      "namespace": { "type": "string" },
      "function_name": { "type": "string" }
    },
    "required": ["namespace", "function_name"]
  }
}
```

### clone_agent

```json
{
  "name": "clone_agent",
  "description": "Clone an agent to a new independent copy. Schedules are disabled on the clone.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string", "description": "Source agent name" },
      "new_name": { "type": "string", "description": "Name for the cloned agent" }
    },
    "required": ["agent_name", "new_name"]
  }
}
```

## Phase D Tools (AI Engine + Communication)

### configure_agent_ai

```json
{
  "name": "configure_agent_ai",
  "description": "Set or update the AI engine on an agent (BYOAI)",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string" },
      "engine": { "type": "string", "enum": ["anthropic", "openai", "google", "openrouter"] },
      "model": { "type": "string" },
      "api_key": { "type": "string" },
      "system_prompt": { "type": "string", "description": "Optional system prompt for AI reasoning" }
    },
    "required": ["agent_name", "engine", "model", "api_key"]
  }
}
```

### add_channel

```json
{
  "name": "add_channel",
  "description": "Configure a communication channel on an agent",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string" },
      "channel_type": { "type": "string", "enum": ["discord", "slack", "whatsapp", "email"] },
      "config": { "type": "object", "description": "Channel-specific configuration (bot token, channel ID, etc.)" }
    },
    "required": ["agent_name", "channel_type", "config"]
  }
}
```

### remove_channel

```json
{
  "name": "remove_channel",
  "description": "Remove a communication channel from an agent",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent_name": { "type": "string" },
      "channel_type": { "type": "string", "enum": ["discord", "slack", "whatsapp", "email"] }
    },
    "required": ["agent_name", "channel_type"]
  }
}
```

## Tool Scopes

All agent tools require at minimum `write` scope. The existing `TOOL_SCOPES` dict in `create_handler.py` will be extended:

| Tool | Scope |
|------|-------|
| list_agents, describe_agent, get_agent_state | read |
| make_agent, start_agent, stop_agent, clone_agent | write |
| destroy_agent | write |
| add_schedule, remove_schedule | write |
| add_webhook, remove_webhook | write |
| set_agent_state | write |
| lock_function, unlock_function | write (admin only) |
| configure_agent_ai, add_channel, remove_channel | write |

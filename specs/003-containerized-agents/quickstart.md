# Quickstart: MCPWorks Containerized Agents

**Branch**: `003-containerized-agents` | **Date**: 2026-03-11

## Prerequisites

- Running mcpworks-api instance with Docker socket access
- Account upgraded to an agent-enabled tier (admin operation)
- MCP client connected to `{namespace}.create.mcpworks.io`

## Step 1: Create an Agent

```
MCP Tool: make_agent
Input: { "name": "dogedetective", "display_name": "Doge Detective" }
```

This creates:
- A new namespace `dogedetective` with write+execute API keys
- A Docker container `agent-dogedetective` on the `mcpworks-agents` network
- The agent starts automatically and enters `running` status

## Step 2: Add Functions to the Agent

Use the existing function management tools to create functions in the agent's namespace:

```
MCP Tool: make_function
Input: {
  "namespace": "dogedetective",
  "service": "core",
  "name": "check-price",
  "code": "import httpx\nresult = httpx.get('https://api.example.com/price').json()\nprint(result['price'])"
}
```

## Step 3: Schedule a Function

```
MCP Tool: add_schedule
Input: {
  "agent_name": "dogedetective",
  "function_name": "check-price",
  "cron_expression": "*/5 * * * *",
  "timezone": "America/Toronto",
  "failure_policy": { "strategy": "auto_disable", "max_failures": 5 }
}
```

The agent now checks the price every 5 minutes. If 5 consecutive failures occur, the schedule auto-disables.

## Step 4: Register a Webhook

```
MCP Tool: add_webhook
Input: {
  "agent_name": "dogedetective",
  "path": "price-alert",
  "handler_function_name": "handle-alert",
  "secret": "whsec_mysecret123"  # pragma: allowlist secret
}
```

External systems can now POST to:
```
https://dogedetective.agent.mcpworks.io/webhook/price-alert
```

## Step 5: Store Persistent State

```
MCP Tool: set_agent_state
Input: { "agent_name": "dogedetective", "key": "last_price", "value": 42150.50 }
```

Functions can read this state between runs to detect changes.

## Step 6: Lock Critical Functions

```
MCP Tool: lock_function
Input: { "namespace": "dogedetective", "function_name": "check-price" }
```

The agent can still execute `check-price` but cannot modify its code.

## Step 7 (Optional): Configure AI Engine

```
MCP Tool: configure_agent_ai
Input: {
  "agent_name": "dogedetective",
  "engine": "anthropic",
  "model": "claude-haiku-4-5-20251001",
  "api_key": "sk-ant-...",  # pragma: allowlist secret
  "system_prompt": "You are Doge Detective, a crypto price monitoring agent."
}
```

## Step 8 (Optional): Add Communication Channel

```
MCP Tool: add_channel
Input: {
  "agent_name": "dogedetective",
  "channel_type": "discord",
  "config": { "bot_token": "...", "channel_id": "123456789" }
}
```

## Agent Management

```
MCP Tool: list_agents          → View all your agents and slot usage
MCP Tool: describe_agent       → Full details of a specific agent
MCP Tool: stop_agent           → Stop the container (preserves config)
MCP Tool: start_agent          → Restart a stopped agent
MCP Tool: clone_agent          → Duplicate an agent with all its config
MCP Tool: destroy_agent        → Permanently delete agent and all data
```

## Monitoring

Agent runs are automatically recorded. View recent runs:
```
GET /api/v1/agents/{agent_id}/runs?limit=10
```

Admin fleet overview:
```
GET /api/v1/admin/agents/health
```

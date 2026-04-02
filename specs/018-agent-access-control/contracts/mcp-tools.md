# MCP Tool Contracts: Per-Agent Access Control

## Tool: configure_agent_access

**Endpoint**: `/mcp/create/{namespace}` (existing create handler)  
**Scope**: write

### Input Schema

```json
{
  "type": "object",
  "properties": {
    "agent_name": {
      "type": "string",
      "description": "Name of the agent to configure access rules for."
    },
    "rule": {
      "type": "object",
      "description": "Access rule definition. Must include 'type' and 'patterns'.",
      "properties": {
        "type": {
          "type": "string",
          "enum": ["allow_services", "deny_services", "allow_functions", "deny_functions", "allow_keys", "deny_keys"],
          "description": "Rule type. *_services and *_functions control function access. *_keys control state access."
        },
        "patterns": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Glob patterns (fnmatch-style). For functions: 'service.function' format. For services: service name. For keys: state key name."
        }
      },
      "required": ["type", "patterns"]
    }
  },
  "required": ["agent_name", "rule"]
}
```

### Response

```json
{
  "agent": "social-bot",
  "rule_added": {
    "id": "r-a1b2c3d4",
    "type": "allow_services",
    "patterns": ["social", "content"]
  }
}
```

---

## Tool: list_agent_access_rules

**Endpoint**: `/mcp/create/{namespace}` (existing create handler)  
**Scope**: read

### Input Schema

```json
{
  "type": "object",
  "properties": {
    "agent_name": {
      "type": "string",
      "description": "Name of the agent to list access rules for."
    }
  },
  "required": ["agent_name"]
}
```

### Response

```json
{
  "agent": "social-bot",
  "function_rules": [
    {"id": "r-a1b2c3d4", "type": "allow_services", "patterns": ["social", "content"]},
    {"id": "r-e5f6g7h8", "type": "deny_functions", "patterns": ["admin.delete_*"]}
  ],
  "state_rules": [
    {"id": "r-i9j0k1l2", "type": "allow_keys", "patterns": ["content.*", "cache.*"]}
  ]
}
```

---

## Tool: remove_agent_access_rule

**Endpoint**: `/mcp/create/{namespace}` (existing create handler)  
**Scope**: write

### Input Schema

```json
{
  "type": "object",
  "properties": {
    "agent_name": {
      "type": "string",
      "description": "Name of the agent to remove a rule from."
    },
    "rule_id": {
      "type": "string",
      "description": "ID of the rule to remove (e.g., 'r-a1b2c3d4'). Use list_agent_access_rules to find rule IDs."
    }
  },
  "required": ["agent_name", "rule_id"]
}
```

### Response

```json
{
  "agent": "social-bot",
  "rule_removed": "r-a1b2c3d4",
  "remaining_rules": 2
}
```

---

## Error Responses

### Access Denied (function call blocked)

```json
{
  "error": "agent_access_denied",
  "function": "billing.charge_customer",
  "agent": "social-bot",
  "rule_id": "r-a1b2c3d4",
  "message": "Agent 'social-bot' is not permitted to call 'billing.charge_customer' (rule: r-a1b2c3d4)"
}
```

### Access Denied (state key blocked)

```json
{
  "error": "agent_state_access_denied",
  "key": "secrets.api_token",
  "agent": "social-bot",
  "rule_id": "r-i9j0k1l2",
  "message": "Agent 'social-bot' is not permitted to access state key 'secrets.api_token' (rule: r-i9j0k1l2)"
}
```

# MCP Tool Contracts: Security Scanner Pipeline

## Tool: add_security_scanner

**Scope**: write

```json
{
  "type": "object",
  "properties": {
    "type": {
      "type": "string",
      "enum": ["builtin", "webhook", "python"],
      "description": "Scanner type."
    },
    "name": {
      "type": "string",
      "description": "Human-readable scanner name."
    },
    "direction": {
      "type": "string",
      "enum": ["input", "output", "both"],
      "description": "When to scan: before execution (input), after execution (output), or both."
    },
    "config": {
      "type": "object",
      "description": "Type-specific config. builtin: {name}. webhook: {url, timeout_ms, headers}. python: {module, function, init_kwargs}."
    }
  },
  "required": ["type", "name", "direction", "config"]
}
```

**Response**:
```json
{"scanner_added": {"id": "s-a1b2c3d4", "type": "webhook", "name": "lakera", "direction": "output", "order": 4}}
```

---

## Tool: list_security_scanners

**Scope**: read

```json
{
  "type": "object",
  "properties": {}
}
```

**Response**:
```json
{
  "fallback_policy": "fail_open",
  "scanners": [
    {"id": "s-abc123", "type": "builtin", "name": "pattern_scanner", "direction": "output", "order": 1, "enabled": true},
    {"id": "s-def456", "type": "webhook", "name": "lakera", "direction": "output", "order": 2, "enabled": true}
  ]
}
```

---

## Tool: update_security_scanner

**Scope**: write

```json
{
  "type": "object",
  "properties": {
    "scanner_id": {"type": "string", "description": "Scanner ID (e.g., 's-a1b2c3d4')."},
    "enabled": {"type": "boolean", "description": "Enable or disable the scanner."},
    "config": {"type": "object", "description": "Updated config (merged with existing)."}
  },
  "required": ["scanner_id"]
}
```

---

## Tool: remove_security_scanner

**Scope**: write

```json
{
  "type": "object",
  "properties": {
    "scanner_id": {"type": "string", "description": "Scanner ID to remove."}
  },
  "required": ["scanner_id"]
}
```

---

## Webhook Scanner Protocol

### Request (MCPWorks → Scanner)

```
POST {configured_url}
Content-Type: application/json

{
  "content": "text to scan",
  "direction": "output",
  "namespace": "myns",
  "service": "social",
  "function": "post-to-bluesky",
  "metadata": {
    "execution_id": "...",
    "function_version": 2,
    "output_trust": "data"
  }
}
```

### Response (Scanner → MCPWorks)

```json
{"action": "pass|flag|block", "score": 0.0, "reason": "..."}
```

### Python Scanner Interface

```python
def scan(content: str, context: dict) -> dict:
    return {"action": "pass", "score": 0.0, "reason": "clean"}
```

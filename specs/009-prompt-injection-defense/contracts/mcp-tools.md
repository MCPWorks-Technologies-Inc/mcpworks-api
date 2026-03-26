# MCP Tool Contracts: Prompt Injection Defense

**Feature**: 009-prompt-injection-defense

## Modified Tools

### make_function (modified)

**New required parameter:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| output_trust | string | yes | `prompt` (trusted output) or `data` (untrusted external content). If omitted, returns error with auto-classification suggestion. |

**Error when omitted:**
```json
{
  "error": "output_trust is required. Suggested: 'data' (function imports mcp__google_workspace tools). Set output_trust='data' or output_trust='prompt'."
}
```

### update_function (modified)

**New optional parameter:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| output_trust | string | no | Change trust level to `prompt` or `data` |

### describe_function (modified)

**New field in response:** `output_trust` shown in function details.

---

## New Tools (added to MCP_SERVER_TOOLS group)

### add_mcp_server_rule

**Description**: Add a request or response rule to an MCP server. Rules are evaluated on every proxy call.

**Authorization**: Namespace owner only.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | yes | MCP server name |
| direction | string | yes | `request` or `response` |
| rule | object | yes | Rule definition (see types below) |

**Request rule types:**
- `{"type": "inject_param", "tool": "*", "key": "maxResults", "value": 100}`
- `{"type": "block_tool", "tool": "delete_channel"}`
- `{"type": "require_param", "tool": "search_*", "key": "query"}`
- `{"type": "cap_param", "tool": "*", "key": "limit", "max": 200}`

**Response rule types:**
- `{"type": "wrap_trust_boundary", "tools": "*"}`
- `{"type": "scan_injection", "tools": "*", "strictness": "flag"}`
- `{"type": "strip_html", "tools": ["get_gmail_message_content"]}`
- `{"type": "inject_header", "tools": "*", "text": "WARNING: External data."}`
- `{"type": "redact_fields", "tools": "*", "fields": ["raw_html", "headers.cookie"]}`

**Success response:**
```json
{
  "status": "added",
  "server": "slack",
  "direction": "response",
  "rule_id": "r-abc123",
  "rule": {"type": "scan_injection", "tools": "*", "strictness": "flag"}
}
```

### remove_mcp_server_rule

**Authorization**: Namespace owner only.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | yes | MCP server name |
| rule_id | string | yes | Rule ID to remove |

**Success:** `{"status": "removed", "server": "slack", "rule_id": "r-abc123"}`

### list_mcp_server_rules

**Authorization**: Read access.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | yes | MCP server name |

**Success response:**
```json
{
  "server": "slack",
  "request_rules": [
    {"id": "r1", "type": "block_tool", "tool": "delete_channel"}
  ],
  "response_rules": [
    {"id": "default-trust", "type": "wrap_trust_boundary", "tools": "*"},
    {"id": "default-scan", "type": "scan_injection", "tools": "*", "strictness": "warn"}
  ]
}
```

# MCP Tool Contracts: Third-Party MCP Server Integration

**Feature**: 008-mcp-server-plugins
**Endpoint**: `{namespace}.create.mcpworks.io/mcp`

11 tools on the create endpoint (management operations).

---

## add_mcp_server

**Description**: Register a third-party MCP server on this namespace. Connects, discovers tools, encrypts credentials, stores config.

**Authorization**: Namespace owner only.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | yes | Server identifier (DNS-safe, unique per namespace). Example: 'slack' |
| url | string | yes* | HTTPS endpoint URL. *Required for sse/streamable_http. |
| transport | string | no | `sse`, `streamable_http` (default), `stdio` |
| auth_token | string | no | Bearer token (set as Authorization header) |
| headers | object | no | Additional headers (key-value pairs) |
| command | string | no* | Binary path. *Required for stdio. |
| args | array | no | Arguments for stdio command |

**Success response** (~120 tokens):
```json
{
    "status": "added",
    "name": "slack",
    "url": "https://slack-mcp.example.com/mcp",
    "transport": "streamable_http",
    "tool_count": 15,
    "tools": ["send_message", "list_channels", "search_messages", "..."]
}
```

**Errors**: Connection failed (400), name already exists (409), owner only (403), stdio not allowed on Cloud (400)

---

## remove_mcp_server

**Authorization**: Namespace owner only.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | yes | Server name |

**Success**: `{"status": "removed", "name": "slack"}`

---

## list_mcp_servers

**Authorization**: Read access.

**Parameters**: None.

**Success response** (~100 tokens per server):
```json
{
    "servers": [
        {
            "name": "slack",
            "url": "https://slack-mcp.example.com/mcp",
            "transport": "streamable_http",
            "tool_count": 15,
            "enabled": true,
            "last_connected": "2026-03-26T12:00:00Z"
        }
    ]
}
```

---

## describe_mcp_server

**Authorization**: Read access.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | yes | Server name |

**Success response** (~300 tokens):
```json
{
    "name": "slack",
    "url": "https://slack-mcp.example.com/mcp",
    "transport": "streamable_http",
    "enabled": true,
    "settings": {
        "response_limit_bytes": 1048576,
        "timeout_seconds": 30,
        "max_calls_per_execution": 50,
        "retry_on_failure": true,
        "retry_count": 2
    },
    "env_vars": {
        "SLACK_WORKSPACE": "mcpworks"
    },
    "tool_count": 15,
    "tools": [
        {"name": "send_message", "description": "Send a message to a channel"},
        {"name": "list_channels", "description": "List all channels"}
    ],
    "last_connected": "2026-03-26T12:00:00Z"
}
```

---

## refresh_mcp_server

**Authorization**: Namespace owner only.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | yes | Server name |

**Success response**:
```json
{
    "status": "refreshed",
    "name": "slack",
    "tool_count": 16,
    "tools_added": ["new_tool"],
    "tools_removed": []
}
```

---

## update_mcp_server

**Authorization**: Namespace owner only.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | yes | Server name |
| auth_token | string | no | New bearer token |
| headers | object | no | Replace all custom headers |
| url | string | no | Update endpoint URL |

**Success**: `{"status": "updated", "name": "slack"}`

---

## set_mcp_server_setting

**Authorization**: Namespace owner only.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | yes | Server name |
| key | string | yes | Setting key |
| value | any | yes | Setting value |

**Allowed keys**: `response_limit_bytes` (int), `timeout_seconds` (int), `max_calls_per_execution` (int), `retry_on_failure` (bool), `retry_count` (int), `enabled` (bool)

**Success**: Returns full current settings object.

---

## set_mcp_server_env

**Authorization**: Namespace owner only.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | yes | Server name |
| key | string | yes | Env var name |
| value | string | yes | Env var value |

**Success**: Returns full current env_vars object.

---

## remove_mcp_server_env

**Authorization**: Namespace owner only.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | yes | Server name |
| key | string | yes | Env var name to remove |

**Success**: Returns full current env_vars object.

---

## configure_agent_mcp

**Description**: Set which namespace MCP servers an agent can access.

**Authorization**: Namespace owner only.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| agent_name | string | yes | Agent name |
| servers | array | yes | List of MCP server names (e.g., ["slack", "google-workspace"]) |

**Success**:
```json
{
    "agent": "assistantpam",
    "mcp_servers": ["slack", "google-workspace"]
}
```

**Errors**: Agent not found (404), server name not found (400)

---

## Internal Endpoint: MCP Proxy

**Endpoint**: `POST /v1/internal/mcp-proxy`
**Authentication**: Bridge key (`__MCPWORKS_BRIDGE_KEY__`)
**Not in MCP tool registry** — called by sandbox wrapper code only.

**Request**:
```json
{
    "server": "slack",
    "tool": "send_message",
    "arguments": {"channel": "C01234", "text": "hello"}
}
```

**Success response**:
```json
{
    "result": "Message sent to #general",
    "truncated": false
}
```

**Error response**:
```json
{
    "error": "MCP server 'slack' authentication failed",
    "error_type": "AuthenticationError"
}
```

**Behavior**:
1. Validate bridge key → look up ExecutionContext → get namespace_id
2. Verify server exists in namespace and is enabled
3. Read settings (response_limit, timeout, retry config)
4. Get or create pooled connection (decrypt credentials if new connection)
5. Call MCP tool with arguments
6. Enforce response_limit_bytes (truncate if exceeded)
7. Return result

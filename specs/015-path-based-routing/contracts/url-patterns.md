# API Contract: Path-Based URL Patterns

## MCP Endpoints

### Core MCP (JSON-RPC over Streamable HTTP)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/mcp/create/{namespace}` | MCP create (management) endpoint |
| POST | `/mcp/run/{namespace}` | MCP run (execution) endpoint |
| POST | `/mcp/agent/{namespace}` | MCP agent endpoint |
| GET | `/mcp/create/{namespace}` | SSE reconnection (create) |
| GET | `/mcp/run/{namespace}` | SSE reconnection (run) |
| GET | `/mcp/agent/{namespace}` | SSE reconnection (agent) |
| DELETE | `/mcp/create/{namespace}` | Session termination (create) |
| DELETE | `/mcp/run/{namespace}` | Session termination (run) |
| DELETE | `/mcp/agent/{namespace}` | Session termination (agent) |

### Agent Sub-Routes

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/mcp/agent/{namespace}/webhook/{path:path}` | Webhook ingress |
| POST | `/mcp/agent/{namespace}/chat/{token}` | Public chat message |
| GET | `/mcp/agent/{namespace}/view/{token}/` | Scratchpad view (HTML) |

### Discovery

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/mcp` | Protocol discovery |

## Path Parameter Constraints

### `{namespace}`

- Regex: `[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?`
- Min length: 1
- Max length: 63
- Allowed chars: lowercase alphanumeric and hyphens
- Cannot start or end with hyphen

### `{endpoint}`

- Enum: `create`, `run`, `agent`
- Any other value returns 404

### `{path}` (webhook sub-path)

- Free-form path segments (captured by FastAPI's `{path:path}`)
- Example: `github/push`, `stripe/invoice`

### `{token}`

- Opaque string, validated by the handler

## Discovery Response

```json
GET /mcp

{
  "protocol": "mcp",
  "version": "2024-11-05",
  "url_template": "/mcp/{endpoint}/{namespace}",
  "endpoints": ["create", "run", "agent"],
  "docs": "/docs/quickstart"
}
```

## URL Builder Output Examples

### ROUTING_MODE=path (default)

```
create_url("acme")     → https://api.mcpworks.io/mcp/create/acme
run_url("acme")        → https://api.mcpworks.io/mcp/run/acme
agent_url("mybot")     → https://api.mcpworks.io/mcp/agent/mybot
mcp_url("acme", "run") → https://api.mcpworks.io/mcp/run/acme
view_url("mybot", "t") → https://api.mcpworks.io/mcp/agent/mybot/view/t/
chat_url("mybot", "t") → https://api.mcpworks.io/mcp/agent/mybot/chat/t
```

### ROUTING_MODE=subdomain (legacy)

```
create_url("acme")     → https://acme.create.mcpworks.io
run_url("acme")        → https://acme.run.mcpworks.io
agent_url("mybot")     → https://mybot.agent.mcpworks.io
mcp_url("acme", "run") → https://acme.run.mcpworks.io/mcp
view_url("mybot", "t") → https://mybot.agent.mcpworks.io/view/t/
chat_url("mybot", "t") → https://mybot.agent.mcpworks.io/chat/t
```

## Deprecation Headers

When a request arrives via subdomain routing (and `ROUTING_MODE=both`):

```
X-MCPWorks-Deprecated: subdomain-routing; migrate to /mcp/{endpoint}/{namespace}
```

## Error Responses

### Invalid endpoint type

```
GET /mcp/invalid/acme → 404

{
  "detail": {
    "code": "INVALID_ENDPOINT",
    "message": "Invalid endpoint 'invalid'. Must be one of: create, run, agent"
  }
}
```

### Missing namespace

```
GET /mcp/create → 404 (FastAPI default — no route match)
```

### Invalid namespace format

```
GET /mcp/create/UPPERCASE → 400

{
  "detail": {
    "code": "INVALID_NAMESPACE",
    "message": "Invalid namespace 'UPPERCASE'. Must match [a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
  }
}
```

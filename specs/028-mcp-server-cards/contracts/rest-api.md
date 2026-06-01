# API Contracts: MCP Server Cards

## Endpoints

### GET /.well-known/mcp.json (namespace)

**Host**: `{namespace}.create.mcpworks.io`
**Auth**: None (public)
**Cache**: `Cache-Control: public, max-age=300`

#### 200 OK — Namespace Server Card

```json
{
  "schema_version": "0.1.0",
  "name": "busybox",
  "description": "Test and monitoring namespace",
  "protocol_version": "2024-11-05",
  "transports": [
    {"type": "https+sse"}
  ],
  "endpoints": {
    "create": "https://busybox.create.mcpworks.io/mcp",
    "run": "https://busybox.run.mcpworks.io/mcp"
  },
  "tools": [
    {
      "name": "monitor.check-api",
      "description": "Hit the mcpworks API health endpoint and report status.",
      "input_schema": {
        "type": "object",
        "properties": {}
      }
    }
  ],
  "private_tool_count": 8,
  "service_count": 3,
  "total_tool_count": 10
}
```

#### 404 Not Found — Unknown Namespace

```json
{
  "error": "namespace_not_found",
  "message": "No namespace found for this host"
}
```

#### 503 Service Unavailable — Database Error

```json
{
  "error": "service_unavailable",
  "message": "Unable to generate server card"
}
```

---

### GET /.well-known/mcp.json (platform)

**Host**: `api.mcpworks.io`
**Auth**: None (public)
**Cache**: `Cache-Control: public, max-age=300`

#### 200 OK — Platform Server Card

```json
{
  "schema_version": "0.1.0",
  "platform": "mcpworks",
  "description": "Namespace-based function hosting for AI assistants",
  "namespaces": [
    {
      "name": "busybox",
      "description": "Test and monitoring namespace",
      "server_card_url": "https://busybox.create.mcpworks.io/.well-known/mcp.json",
      "tool_count": 10
    }
  ]
}
```

---

## Response Headers

All server card responses include:

| Header | Value | Purpose |
|--------|-------|---------|
| `Content-Type` | `application/json` | Standard JSON |
| `Cache-Control` | `public, max-age=300` | 5-minute cache for crawlers |
| `Access-Control-Allow-Origin` | `*` | Allow browser-based discovery |

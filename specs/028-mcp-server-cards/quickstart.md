# Quickstart: MCP Server Cards

## Try It

Once deployed, discover any namespace:

```bash
curl https://busybox.create.mcpworks.io/.well-known/mcp.json | jq .
```

Discover all public namespaces:

```bash
curl https://api.mcpworks.io/.well-known/mcp.json | jq .
```

## Make a Namespace Discoverable

Via MCP create endpoint (busybox example):

```json
{"method": "tools/call", "params": {"name": "configure_namespace", "arguments": {"discoverable": true}}}
```

Or via admin API:

```bash
curl -X PATCH https://api.mcpworks.io/v1/admin/namespaces/busybox \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -d '{"discoverable": true}'
```

## What You Get Back

**Namespace card** — tools your namespace exposes publicly, connection endpoints, protocol version.

**Platform card** — list of all discoverable namespaces with links to their individual cards.

## Local Development

```bash
# Run the API locally
uvicorn mcpworks_api.main:app --reload --port 8000

# Test namespace card (use Host header to simulate subdomain)
curl -H "Host: busybox.create.localhost" http://localhost:8000/.well-known/mcp.json

# Test platform card
curl -H "Host: api.localhost" http://localhost:8000/.well-known/mcp.json
```

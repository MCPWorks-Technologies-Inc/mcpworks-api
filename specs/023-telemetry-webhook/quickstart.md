# Quickstart: Namespace Telemetry Webhook

## What It Does

Every function execution in your namespace sends execution metadata to your analytics endpoint — MCPCat, Datadog, PostHog, or any HTTP endpoint. Fire-and-forget, never blocks your functions.

## Setup (REST API)

### Configure webhook

```bash
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.mcpworks.io/v1/namespaces/my-namespace/telemetry-webhook" \
  -d '{
    "url": "https://ingest.mcpcat.io/v1/events/proj_abc123",
    "secret": "whsec_mySecretKey123"
  }'
```

### Check configuration

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.mcpworks.io/v1/namespaces/my-namespace/telemetry-webhook"
```

Response:
```json
{
  "url": "https://ingest.mcpcat.io/v1/events/proj_abc123",
  "has_secret": true,
  "batch_enabled": false,
  "batch_interval_seconds": 10
}
```

### Remove webhook

```bash
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  "https://api.mcpworks.io/v1/namespaces/my-namespace/telemetry-webhook"
```

## Setup (MCP Tool)

From your AI assistant connected to `/mcp/create/my-namespace`:

```
configure_telemetry_webhook(url="https://ingest.mcpcat.io/v1/events/proj_abc123", secret="whsec_mySecretKey123")
```

## What Your Endpoint Receives

Every function execution triggers an HTTP POST:

```http
POST /v1/events/proj_abc123 HTTP/1.1
Content-Type: application/json
X-MCPWorks-Signature: sha256=a1b2c3d4e5f6...
User-Agent: MCPWorks-Webhook/1.0

{
  "event": "tool_call",
  "namespace": "my-namespace",
  "data": {
    "function": "social.post-to-bluesky",
    "execution_id": "abc-123-def-456",
    "execution_time_ms": 1250,
    "success": true,
    "backend": "code_sandbox",
    "version": 4,
    "timestamp": "2026-04-08T23:00:00Z"
  }
}
```

## Verifying Signatures

```python
import hashlib
import hmac

def verify_signature(payload_bytes: bytes, secret: str, signature_header: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```

## Enable Batching (High-Volume)

```bash
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.mcpworks.io/v1/namespaces/my-namespace/telemetry-webhook" \
  -d '{
    "url": "https://ingest.mcpcat.io/v1/events/proj_abc123",
    "secret": "whsec_mySecretKey123",
    "batch_enabled": true,
    "batch_interval_seconds": 5
  }'
```

With batching, the payload is an array:

```json
{
  "event": "tool_call_batch",
  "namespace": "my-namespace",
  "data": [
    {"function": "social.post-to-bluesky", "execution_id": "abc-1", ...},
    {"function": "social.post-to-bluesky", "execution_id": "abc-2", ...}
  ]
}
```

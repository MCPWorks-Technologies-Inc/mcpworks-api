# Quickstart: API → MCP

**Feature**: 019-api-to-mcp

Turn any REST API into a token-efficient MCP tool in four steps. Endpoints are **functions-only by default** — they're callable inside the sandbox, and you compose them into clean tools.

---

## 1. Register the API (OpenAPI import + stored credential)

> "Register the Acme Orders API from `https://api.acme.example.com/openapi.json`. Auth with header `X-API-Key` = `sk_live_...` and store it. Enable `list_orders` and `get_order`."

Claude calls `add_api_server`:
```json
{
  "name": "acme",
  "base_url": "https://api.acme.example.com",
  "spec_source": "openapi_url",
  "openapi_url": "https://api.acme.example.com/openapi.json",
  "auth": [{ "name": "api_key", "location": "header", "key": "X-API-Key", "format": "{value}", "source": "stored", "value": "sk_live_..." }],
  "enabled_endpoints": ["list_orders", "get_order"]
}
```
→ *"Added API server 'acme' with 12 endpoints (2 enabled). 10 more are available — enable the ones you need."*

The key is encrypted at rest and never appears again in any response.

## 2. Curate endpoints (optional)

> "Also enable `create_order`."

`enable_endpoint { "server": "acme", "operation_ids": ["create_order"] }`. Only enabled endpoints become sandbox primitives and appear in the catalog.

## 3. Author a composing function

The enabled endpoints are now importable in the sandbox as `api__acme__<operation_id>`:

```python
from functions import api__acme__list_orders

resp = api__acme__list_orders(query={"status": "open", "limit": 200})
# The full 200-order payload stays in the sandbox.
result = [{"id": o["id"], "total": o["total"]} for o in resp["json"]["data"]]
```

Save this as a function (e.g. `orders/open_order_totals`). It's now a single MCP tool whose output is just the `id`/`total` pairs — the raw API response never enters the AI context.

## 4. Call it

Invoking `open_order_totals` returns the compact list. Token cost ≈ the code + the trimmed result, not the 50KB upstream payload — the 70–98% savings story, applied to a plain REST API.

---

## Recipe: passthrough credentials (end-user brings their own key)

Register with a `passthrough` injection bound to an env var — no value stored:
```json
{
  "name": "acme",
  "base_url": "https://api.acme.example.com",
  "spec_source": "openapi_url",
  "openapi_url": "https://api.acme.example.com/openapi.json",
  "auth": [{ "name": "token", "location": "bearer", "format": "Bearer {value}", "source": "passthrough", "env_var": "ACME_TOKEN" }]
}
```
At run time each execution supplies `ACME_TOKEN` via env-passthrough (002). The proxy reads it **server-side** and injects `Authorization: Bearer <token>` — the value never touches sandbox code, is never persisted, and is never logged. Missing var → `{"error":"missing_credential","action":"set ACME_TOKEN in execution env"}`.

---

## Recipe: API without an OpenAPI spec

```
add_api_server { "name": "legacy", "base_url": "https://legacy.example.com", "spec_source": "manual" }
add_manual_endpoint {
  "server": "legacy", "operation_id": "get_widget", "method": "GET", "path": "/v2/widgets/{id}",
  "param_schema": { "path": { "type": "object", "properties": { "id": {"type":"string"} }, "required": ["id"] } }
}
```
Then `api__legacy__get_widget(path={"id":"w_123"})` in the sandbox. Manual endpoints are enabled by default.

---

## Recipe: publish a raw endpoint (opt-in escape hatch)

> "Publish acme's `get_order` directly."

`publish_endpoint { "server": "acme", "operation_id": "get_order" }` → `get_order` becomes a direct MCP tool returning the raw response. Use only for small, clean responses; the functions-only path is preferred for anything list-shaped.

---

## What's protected

- **SSRF**: base URLs resolving to private/link-local/loopback/metadata (`169.254.169.254`, `10.x`, `127.x`, `::1`) are blocked at registration *and* at call time (defeats DNS rebinding); redirects to denied hosts are not followed.
- **Credentials**: stored secrets live in a dedicated encrypted column and are redacted everywhere; passthrough values are read server-side only.
- **Safety on mutations**: POST/PATCH are never auto-retried (no double-create).
- **Telemetry**: each call records server/operation/method/latency/bytes/status in `api_proxy_calls` — never bodies or credentials.

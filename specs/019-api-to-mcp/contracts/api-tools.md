# Contracts: API → MCP Management Tools + Internal Proxy

**Feature**: 019-api-to-mcp
**Date**: 2026-05-29

MCP management tools are exposed on the **create** endpoint (`/mcp/create/{ns}`), registered in `mcp/tool_registry.py` (new `API_SERVER_TOOLS` dict) and dispatched by `CreateMCPHandler` (`mcp/create_handler.py`). Scopes follow the existing `TOOL_SCOPES` convention (`read` / `write`). All responses are token-efficient (progressive disclosure; references over full data) and **never include credential values**.

Conventions:
- `server` = NamespaceApiServer `name` (unique per namespace).
- `operation_id` = ApiEndpoint stable handle.
- Errors use the structured shape `{ "error": "<code>", "reason": "<detail>", "action": "<next step>" }`.

---

## 1. add_api_server  *(scope: write)*

Register a REST API on the namespace and discover its endpoints.

**Input**
```json
{
  "name": "acme",
  "base_url": "https://api.acme.example.com",
  "description": "Acme Orders API",
  "spec_source": "openapi_url",
  "openapi_url": "https://api.acme.example.com/openapi.json",
  "openapi_file": null,
  "auth": [
    { "name": "api_key", "location": "header", "key": "X-API-Key", "format": "{value}", "source": "stored", "value": "sk_live_..." }
  ],
  "default_headers": { "Accept": "application/json" },
  "settings": { "timeout_seconds": 30 },
  "enabled_endpoints": ["list_orders", "get_order"]
}
```
- `spec_source`: `openapi_url` | `openapi_file` | `manual`. For `manual`, omit spec fields and add endpoints with `add_manual_endpoint`. `openapi_file` carries the spec document inline as a JSON/YAML string (MCP tools accept no file handles); the importer detects format by content.
- `auth[].value` is accepted only for `source:"stored"`, immediately encrypted into `credentials_encrypted`, and **stripped from all responses**. `passthrough` injections carry `env_var`, never `value`.
- `enabled_endpoints` (optional): operation_ids to enable at add time. Omitted → all imported endpoints start disabled (curate later).

**Behavior**: validate `base_url` against SSRF denylist → if OpenAPI, fetch + parse (local `$ref` only) → upsert endpoints (default disabled, manual=enabled) → encrypt stored secrets → persist.

**Response** (inventory for curation; credentials redacted)
```json
{
  "server": "acme",
  "spec_source": "openapi_url",
  "endpoint_count": 12,
  "enabled_count": 2,
  "endpoints": [
    { "operation_id": "list_orders", "method": "GET", "path": "/orders", "summary": "List orders", "enabled": true },
    { "operation_id": "get_order",  "method": "GET", "path": "/orders/{id}", "summary": "Get one order", "enabled": true },
    { "operation_id": "create_order", "method": "POST", "path": "/orders", "summary": "Create order", "enabled": false }
  ],
  "note": "10 endpoints discovered but disabled. Enable the ones you need with enable_endpoint."
}
```
**Errors**: `ssrf_blocked`, `openapi_fetch_failed`, `openapi_parse_failed`, `name_conflict`, `invalid_auth`.

---

## 2. refresh_api_endpoints  *(scope: write)*

Re-fetch the OpenAPI spec and diff endpoints, preserving `enabled`/`published` by `operation_id`.

**Input**: `{ "server": "acme" }`
**Response**
```json
{ "server": "acme", "added": ["cancel_order"], "removed": ["legacy_lookup"], "changed": ["get_order"], "unchanged": 10, "preserved_enabled": ["list_orders","get_order"] }
```
**Errors**: `not_found`, `openapi_fetch_failed` (cached endpoints preserved), `manual_server` (no OpenAPI to refresh).

---

## 3. list_api_servers  *(scope: read)*

**Input**: `{}`
**Response**
```json
{ "servers": [ { "name": "acme", "base_url": "https://api.acme.example.com", "spec_source": "openapi_url", "endpoint_count": 12, "enabled_count": 2, "enabled": true, "last_refreshed_at": "2026-05-29T12:00:00Z" } ] }
```

---

## 4. describe_api_server  *(scope: read)*

**Input**: `{ "server": "acme" }`
**Response** (auth definitions shown, **values redacted**)
```json
{
  "name": "acme", "base_url": "...", "spec_source": "openapi_url", "enabled": true,
  "settings": { "response_limit_bytes": 1048576, "timeout_seconds": 30, "max_calls_per_execution": 50, "retry_on_failure": true, "retry_count": 2 },
  "auth": [ { "name": "api_key", "location": "header", "key": "X-API-Key", "format": "{value}", "source": "stored", "value": "***redacted***" } ],
  "endpoints": [ { "operation_id": "list_orders", "method": "GET", "path": "/orders", "enabled": true, "published": false } ],
  "last_refreshed_at": "2026-05-29T12:00:00Z"
}
```

---

## 5. list_endpoints  *(scope: read)*

**Input**: `{ "server": "acme", "filter": "enabled" }`  (`filter`: `all` | `enabled` | `published`, default `all`)
**Response**: `{ "server": "acme", "endpoints": [ { "operation_id": "...", "method": "...", "path": "...", "summary": "...", "enabled": true, "published": false } ] }`

---

## 6. add_manual_endpoint  *(scope: write)*

**Input**
```json
{
  "server": "legacy",
  "operation_id": "get_widget",
  "method": "GET",
  "path": "/v2/widgets/{id}",
  "summary": "Fetch a widget by id",
  "param_schema": { "path": { "type": "object", "properties": { "id": { "type": "string" } }, "required": ["id"] }, "query": {}, "header": {} },
  "request_body_schema": null,
  "response_schema": null
}
```
Manual endpoints default `enabled=true`. **Response**: the created endpoint summary.
**Errors**: `not_found`, `operation_id_conflict`, `invalid_schema`.

---

## 7. enable_endpoint / 8. disable_endpoint  *(scope: write)*

**Input**: `{ "server": "acme", "operation_ids": ["create_order", "cancel_order"] }`
**Response**: `{ "server": "acme", "enabled": [...], "now_enabled_count": 4 }` (or `disabled`).
Enable → endpoint generated as a sandbox primitive; disable → removed from catalog, schema retained.

---

## 9. remove_api_server  *(scope: write)*

**Input**: `{ "server": "acme" }` → **Response**: `{ "removed": "acme", "endpoints_removed": 12 }`. CASCADE deletes endpoints + credential material.

---

## 10. update_api_settings  *(scope: write)*

**Input**: `{ "server": "acme", "settings": { "timeout_seconds": 60, "enabled": false } }`
Validates keys ∈ {`response_limit_bytes`, `timeout_seconds`, `max_calls_per_execution`, `retry_on_failure`, `retry_count`, `enabled`} and value types.
**Response**: full current settings.

---

## 11. set_api_credentials  *(scope: write)*

Set/update a `stored` injection's secret without re-adding the server.
**Input**: `{ "server": "acme", "name": "api_key", "value": "sk_live_new..." }`
**Response**: `{ "server": "acme", "updated": "api_key" }` (value never echoed).
**Errors**: `not_found`, `injection_not_found`, `not_a_stored_injection`.

---

## 12. publish_endpoint / 13. unpublish_endpoint  *(scope: write)*

Toggle direct raw MCP-tool exposure of an endpoint.
**Input**: `{ "server": "acme", "operation_id": "get_order" }`
**Response**: `{ "server": "acme", "operation_id": "get_order", "published": true, "warning": "Raw response is returned unfiltered and counts against context. Prefer a composing function for large responses." }`

---

## 14. configure_agent_api_access  *(scope: write)*

Set which API servers an agent may reach (parallel to `configure_agent_mcp`).
**Input**: `{ "agent": "report-generator", "api_servers": ["acme"] }`
**Response**: `{ "agent": "report-generator", "api_server_names": ["acme"] }`
**Errors**: `agent_not_found`, `api_server_not_found`.

---

## Internal Proxy: POST /v1/internal/api-proxy

Not a public MCP tool. Called by the sandbox bridge (`functions/_api_bridge.py`). Mirrors `/v1/internal/mcp-proxy`.

**Auth**: `Authorization: Bearer <bridge_key>` → `resolve_execution(token)` → `ExecutionContext` (namespace). 403 if missing/expired.

**Request**
```json
{ "server": "acme", "operation_id": "list_orders", "path": {}, "query": { "status": "open", "limit": 200 }, "body": null, "headers": {} }
```
*No credential field — the proxy injects credentials server-side (stored decrypted; passthrough resolved from execution env).*

**Behavior**: resolve server + endpoint (namespace-scoped; 403 cross-namespace) → build `base_url` + templated `path` + query + body + default headers → inject `auth` → **SSRF gate** (resolve, validate, pin; no auto-redirect) → httpx call with `timeout_seconds`, retry only on idempotent methods → run 009 response rules → truncate at `response_limit_bytes` → record `api_proxy_call`.

**Response (success)**
```json
{ "status_code": 200, "json": { "data": [ /* ... */ ] }, "truncated": false, "content_type": "application/json" }
```
Non-JSON → `{ "status_code": 200, "text": "...", "content_type": "text/html", "truncated": true }`.

**Response (error)** — structured, ≤ ~50 tokens:
```json
{ "error": "ssrf_blocked", "reason": "host resolves to 169.254.169.254", "action": "use a public API host" }
```
Codes: `ssrf_blocked`, `missing_credential`, `timeout`, `max_calls_exceeded`, `endpoint_disabled`, `endpoint_not_found`, `upstream_error`.

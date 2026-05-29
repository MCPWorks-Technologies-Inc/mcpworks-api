# Data Model: API → MCP (Ad-Hoc MCP from REST APIs)

**Feature**: 019-api-to-mcp
**Date**: 2026-05-29

Three new tables + one column added to `agents`. Mirrors 008 patterns (encryption columns, `(namespace_id, name)` uniqueness, settings JSONB) with two deliberate divergences documented in [plan.md](plan.md) Complexity Tracking: endpoints get their own table, and stored secrets get a dedicated encrypted column.

---

## New Entity: NamespaceApiServer

Namespace-level registry of registered REST APIs. Parallel to `NamespaceMcpServer` (008) and `NamespaceService`.

Table: `namespace_api_servers`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | |
| namespace_id | UUID | FK → namespaces.id, ON DELETE CASCADE | Owning namespace |
| name | VARCHAR(63) | NOT NULL | Server identifier, unique per namespace, DNS-safe |
| description | VARCHAR(500) | NULLABLE | Human/LLM description |
| base_url | VARCHAR(500) | NOT NULL | API base (plaintext; validated against SSRF denylist at add + call time) |
| spec_source | VARCHAR(20) | NOT NULL | `openapi_url` \| `openapi_file` \| `manual` |
| openapi_url | VARCHAR(500) | NULLABLE | Source spec URL (for refresh); null for `manual`/`openapi_file` |
| auth | JSONB | NOT NULL, DEFAULT '[]' | Credential-injection **definitions only** (no secret values) — see below |
| credentials_encrypted | BYTEA | NULLABLE | name→secret map for `stored` injections (JSON), encrypted with DEK |
| credentials_dek_encrypted | BYTEA | NULLABLE | DEK encrypted with KEK |
| default_headers_encrypted | BYTEA | NULLABLE | Static non-secret headers (JSON), encrypted with DEK |
| default_headers_dek_encrypted | BYTEA | NULLABLE | DEK encrypted with KEK |
| settings | JSONB | NOT NULL, DEFAULT '{}' | LLM-tunable settings (defaults applied at read) |
| enabled | BOOLEAN | NOT NULL, DEFAULT true | LLM can disable the whole server without removing |
| endpoint_count | INTEGER | NOT NULL, DEFAULT 0 | Cached count of discovered endpoints |
| last_refreshed_at | TIMESTAMPTZ | NULLABLE | Last successful discovery/refresh |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes**: UNIQUE(`namespace_id`, `name`); INDEX(`namespace_id`).

**`auth` JSONB** — list of injection definitions (secret values NEVER stored here):
```json
[
  { "name": "api_key", "location": "header", "key": "X-API-Key", "format": "{value}", "source": "stored" },
  { "name": "token",   "location": "bearer", "key": null,        "format": "Bearer {value}", "source": "passthrough", "env_var": "ACME_TOKEN" }
]
```
- `location`: `header` \| `query` \| `bearer` \| `basic`
- `source`: `stored` \| `passthrough` (forward-compatible with future `oauth2`)
- `env_var`: required when `source = passthrough`; ignored otherwise
- `key`: header/query param name; ignored for `bearer`/`basic`

**`credentials_encrypted`** — decrypts to `{ "<injection name>": "<secret>" }` covering only `stored` injections. Encrypted via `encrypt_value()` / decrypted via `decrypt_value()` (`core/encryption.py`). Never returned by any tool; never logged.

**`settings` JSONB** (defaults applied at read time):
```json
{
  "response_limit_bytes": 1048576,
  "timeout_seconds": 30,
  "max_calls_per_execution": 50,
  "retry_on_failure": true,
  "retry_count": 2
}
```
Retries apply only to idempotent methods (GET/HEAD/PUT/DELETE); POST/PATCH are never auto-retried regardless of `retry_on_failure`.

**Relationships**: Namespace 1—0..N NamespaceApiServer (CASCADE). NamespaceApiServer 1—0..N ApiEndpoint (CASCADE).

---

## New Entity: ApiEndpoint

One row per discovered/defined endpoint. Separate table (not JSONB on the server) because `enabled`/`published` are per-row, queryable state. (See plan Complexity Tracking.)

Table: `api_endpoints`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | |
| api_server_id | UUID | FK → namespace_api_servers.id, ON DELETE CASCADE | Owning server |
| operation_id | VARCHAR(128) | NOT NULL | Stable handle → `api__{server}__{operation_id}`; identifier-safe |
| method | VARCHAR(10) | NOT NULL | GET/POST/PUT/PATCH/DELETE/HEAD |
| path | VARCHAR(500) | NOT NULL | Path template with `{param}` placeholders |
| summary | VARCHAR(255) | NULLABLE | One-line description (catalog docstring) |
| param_schema | JSONB | NOT NULL, DEFAULT '{}' | Location-bucketed params: `{path, query, header}` (see research R6) |
| request_body_schema | JSONB | NULLABLE | JSON Schema for the request body |
| response_schema | JSONB | NULLABLE | JSON Schema for the response (informational) |
| enabled | BOOLEAN | NOT NULL, DEFAULT false | Generated as a sandbox primitive when true (manual endpoints default true) |
| published | BOOLEAN | NOT NULL, DEFAULT false | Exposed as a direct raw MCP tool when true |
| source | VARCHAR(10) | NOT NULL | `imported` \| `manual` |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes**: UNIQUE(`api_server_id`, `operation_id`); INDEX(`api_server_id`, `enabled`); INDEX(`api_server_id`, `published`).

**Lifecycle / state**:
- `imported` endpoints start `enabled=false` (curation); `manual` start `enabled=true`.
- `refresh_api_endpoints` matches by `operation_id`: existing rows keep `enabled`/`published`; new rows added disabled; rows absent from the new spec are marked removed (reported, then their primitives/tools fail with a clear error on next call).
- Safety ceiling: at most 1000 endpoints imported per server; overflow truncated with a warning.

---

## New Entity: ApiProxyCall

Per-call telemetry. Mirrors `mcp_proxy_call` (008/010).

Table: `api_proxy_calls`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | |
| namespace_id | UUID | FK → namespaces.id, ON DELETE CASCADE | |
| api_server | VARCHAR(63) | NOT NULL | Server name |
| operation_id | VARCHAR(128) | NOT NULL | Endpoint handle |
| method | VARCHAR(10) | NOT NULL | HTTP method |
| status_code | INTEGER | NULLABLE | Upstream HTTP status (null on transport failure) |
| latency_ms | INTEGER | NOT NULL | Upstream round-trip latency |
| response_bytes | INTEGER | NOT NULL, DEFAULT 0 | Pre-truncation size |
| truncated | BOOLEAN | NOT NULL, DEFAULT false | Response exceeded response_limit_bytes |
| error_type | VARCHAR(100) | NULLABLE | e.g. `ssrf_blocked`, `timeout`, `missing_credential`, `upstream_error` |
| called_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Never stored**: credential values, request/response bodies, query/path argument values.
**Indexes**: INDEX(`namespace_id`, `called_at`); INDEX(`namespace_id`, `api_server`).

---

## Modified Entity: Agent

Table: `agents` — add one column (mirrors existing `mcp_server_names`, `core/...agent.py:84`).

| Field | Change | Description |
|-------|--------|-------------|
| api_server_names | NEW, ARRAY(String), NULLABLE | NamespaceApiServer names this agent may access. Orchestrator resolves names → configs at run time. |

No migration of existing data needed (new, additive, nullable).

---

## Entity Relationship

```
Namespace (1) ─── (0..N) NamespaceApiServer
    │                       │  auth (defs)         credentials_encrypted (secrets)
    │                       │  settings (JSONB)    default_headers_encrypted
    │                       └─── (0..N) ApiEndpoint
    │                                    ├── enabled  (curation → sandbox primitive)
    │                                    ├── published (raw MCP tool)
    │                                    ├── param_schema {path, query, header}
    │                                    └── request_body_schema
    │
    ├─── (0..N) NamespaceService ─── (0..N) Function ─── (0..N) FunctionVersion
    ├─── (0..N) NamespaceMcpServer (008)
    └─── (0..N) Agent
                  ├── mcp_server_names: [...]   (008)
                  └── api_server_names: [...]   (THIS SPEC)

Namespace (1) ─── (0..N) ApiProxyCall   (telemetry, write-only from proxy)
```

---

## Reuse (no new structures)

- **ExecutionContext** (`core/exec_token_registry.py`) — bridge-key → namespace resolution for the proxy; reused as-is. Passthrough env values are read via this context server-side (research R5).
- **Encryption** (`core/encryption.py`) — `encrypt_value`/`decrypt_value` for `credentials_encrypted` and `default_headers_encrypted`.
- **009 injection rules** (`core/mcp_rules.py`) — applied to upstream responses; `output_trust` semantics carry over.

# API → MCP (Ad-Hoc MCP from REST APIs) - Specification

**Version:** 0.1.0 (Draft)
**Created:** 2026-05-29
**Status:** Draft
**Spec Author:** Simon Carr
**Feature Branch:** `019-api-to-mcp`

---

## Clarifications

### Session 2026-05-29

- Q: How should endpoints be defined when registering an API? → A: OpenAPI/Swagger import (URL or uploaded file) **and** manual endpoint definition. Both can be mixed on a single server. `refresh_api_endpoints` re-fetches the OpenAPI spec and diffs added/removed/changed endpoints while preserving the `published` flag by `operation_id`.
- Q: How should raw endpoint tools and function-wrapped tools be surfaced? → A: **Functions-only by default.** Discovered endpoints become callable primitives *inside the sandbox*, not MCP tools. Users/Claude author functions that compose endpoints into clean tools. An opt-in `publish_endpoint` escape hatch can expose a single raw endpoint as a direct MCP tool when explicitly requested.
- Q: Which upstream API auth schemes should v1 support? → A: A flexible credential-injection model spanning two sources: **stored** (encrypted at rest, injected server-side, end-user never sees it) and **passthrough** (supplied at runtime, never persisted — ties into 002 env-passthrough). Locations: header, query, bearer, basic, each with a value `format` template. OAuth2 client-credentials is **deferred to v2**.
- Q: How should the platform defend against user-supplied base URLs? → A: A **global SSRF denylist** of private/link-local/loopback IP ranges with DNS-rebinding re-resolution at call time. This is the largest new attack surface vs 008 (base URLs are user-controlled).
- Q: Where should call telemetry live? → A: A **separate `api_proxy_call` table** parallel to `mcp_proxy_call` (008/010), recording namespace, server, endpoint/operation, method, latency, response bytes, and status.
- Q: Where can passthrough credential values come from (per-call arg conflicted with the no-credentials-in-sandbox guarantee)? → A: **Execution env only.** Passthrough values are resolved exclusively from the execution's transient env (002 env-passthrough); the per-call-argument path is removed. Sandbox code never handles credential values of any kind.
- Q: How are encrypted stored credential values persisted relative to the `auth` JSONB? → A: **Separate encrypted blob.** The `auth` JSONB holds only injection *definitions* (name, location, key, format, source, env_var); stored secret values live in a separate encrypted column (DEK/KEK) keyed by injection `name`. Mirrors 008's `headers_encrypted` pattern; redaction is structural (secrets are never in the JSONB).
- Q: Should automatic retries apply to non-idempotent methods? → A: **Idempotent methods only.** Auto-retry applies only to GET/HEAD/PUT/DELETE. POST/PATCH are never auto-retried (avoids double-create/double-charge), regardless of `retry_on_failure`.
- Q: Should there be a hard cap on endpoints per API server? → A: **No hard cap — LLM-curated selective import at onboarding.** `add_api_server` / `refresh_api_endpoints` return the discovered endpoint inventory; the LLM selects which endpoints to enable (`enabled_endpoints`). Unselected endpoints are cataloged but not generated as sandbox primitives, keeping the catalog token cost bounded by curation rather than a fixed number. A high safety ceiling guards against pathological specs.

---

## 1. Overview

### 1.1 Purpose

Allow an MCPWorks namespace to register any plain REST/HTTP API and synthesize an ad-hoc MCP from it. The platform discovers the API's endpoints (via OpenAPI import or manual definition), exposes each endpoint as a callable primitive inside the code execution sandbox, and lets users/Claude author functions that compose those endpoints into token-efficient MCP tools.

This is the **inverse mirror of feature 008 (MCP Server Plugins)**: where 008 bolts a third-party *MCP server* onto a namespace, 019 points at a plain *REST API* and builds the MCP layer itself.

| Dimension | 008 (MCP plugin) | 019 (API → MCP) |
|-----------|------------------|------------------|
| Wraps | A remote **MCP server** | A plain **REST API** |
| Discovery | `tools/list` over MCP | OpenAPI import **or** manual definition |
| Exposure | Raw tools **and** code-mode | Code-mode **only** (raw exposure opt-in) |
| Sandbox prefix | `mcp__{server}__{tool}` | `api__{server}__{operation_id}` |
| Proxy route | `/v1/internal/mcp-proxy` | `/v1/internal/api-proxy` |
| Telemetry | `mcp_proxy_call` | `api_proxy_call` |

### 1.2 User Value

Most of the world's automation surface is plain REST APIs, not MCP servers. Today, connecting an AI assistant to a REST API means either (a) finding a pre-built MCP server for it, or (b) dumping raw API responses through the AI's context window. A typical list endpoint can return 50KB of JSON when the agent needs three fields.

With API → MCP, the AI writes code that calls the endpoint as a primitive — `from functions import api__acme__list_orders; orders = api__acme__list_orders(query={"status":"open"})` — the full response is processed inside the sandbox and only the extracted result returns. This applies MCPWorks' 70–98% token-savings story to **arbitrary REST APIs**, no pre-built MCP server required.

It also unlocks two credential models from a single feature: a namespace owner can register an API with **stored** credentials (managed centrally, never seen by callers), or with **passthrough** credentials so each end-user/agent brings their own key at runtime.

### 1.3 Namespace Hierarchy

API servers are a parallel concept to Services and RemoteMCP within a namespace — not a type of Service:

```
Namespace
├── Services (native)           ← your code, runs in sandbox
│   └── {service}
│       └── {function}          ← Function model in DB, code_sandbox backend
├── RemoteMCP (external)        ← third-party MCP servers, proxied (008)
│   └── {mcp-server}
│       └── {tool}              ← cached tool schema (mcp__ prefix)
└── ApiServer (external)        ← REST APIs, proxied (THIS SPEC)
    └── {api-server}
        └── {endpoint}          ← cached endpoint schema (api__ prefix)
```

From the sandbox's perspective, endpoints are callable primitives alongside native functions and MCP tools. The `api__` prefix distinguishes API endpoints.

### 1.4 Success Criteria

**This spec is successful when:**
- [ ] A user can register a REST API on their namespace by importing an OpenAPI spec or defining endpoints manually, with a single MCP tool call.
- [ ] All enabled endpoints are callable as primitives from the code execution sandbox via `api__{server}__{operation_id}`.
- [ ] A user/Claude can author a function that composes one or more endpoints and exposes a single clean, token-efficient MCP tool.
- [ ] Stored credentials are encrypted at rest and never exposed to sandbox code, tool output, or logs; passthrough credentials are injected at runtime and never persisted.
- [ ] User-supplied base URLs cannot be used to reach private/link-local/loopback addresses (SSRF protection), including via DNS rebinding.
- [ ] Per-call telemetry (namespace, server, operation, method, latency, bytes, status) is recorded in `api_proxy_calls`.

### 1.5 Scope

**In Scope:**
- Per-namespace API server registry (add, remove, list, describe, refresh).
- Endpoint discovery via OpenAPI/Swagger import (URL or uploaded file) and manual endpoint definition; mixed on one server.
- `refresh_api_endpoints` re-fetches OpenAPI and diffs added/removed/changed endpoints, preserving `published` by `operation_id`.
- Flexible credential model: stored (encrypted) and passthrough (runtime) injections at header/query/bearer/basic locations with value `format` templates.
- LLM-tunable per-server settings (response_limit_bytes, timeout_seconds, max_calls_per_execution, retry_on_failure, retry_count, enabled).
- Sandbox integration: generate callable endpoint wrappers in the `functions` package (`api__{server}__{operation_id}`), parallel to the MCP bridge.
- Internal proxy endpoint `/v1/internal/api-proxy` for sandbox → API → upstream routing, with credential injection, SSRF gate, and settings enforcement.
- Opt-in `publish_endpoint` / `unpublish_endpoint` to expose a single raw endpoint as a direct MCP tool.
- Agent integration: agents select which namespace API servers they can access by name (`api_server_names`, parallel to `mcp_server_names`).
- SSRF denylist of private/link-local/loopback ranges with DNS-rebinding re-resolution.
- Reuse of 009 prompt-injection rules on responses; `output_trust` semantics carry over.
- Separate `api_proxy_calls` telemetry table.

**Out of Scope:**
- OAuth2 client-credentials and other token-lifecycle auth flows (deferred to v2).
- Per-namespace egress *allowlists* of arbitrary hostnames (v1 uses a global denylist only; allowlist is a future extension).
- Hosting or mocking the upstream API (MCPWorks only calls it).
- GraphQL, gRPC, SOAP, or WebSocket upstreams (REST/HTTP-JSON only in v1).
- Streaming/long-poll upstream responses (single request/response per call in v1).
- Automatic endpoint schema updates (manual `refresh_api_endpoints` only).
- Billing/metering changes (uses existing execution metering).

---

## 2. User Scenarios

### 2.1 Primary Scenario: Register an API via OpenAPI and Compose a Function (Priority: P1)

**Actor:** Developer using Claude Code with MCPWorks
**Goal:** Turn an internal REST API into a clean, token-efficient MCP tool
**Context:** Developer has an "Acme Orders" API at `https://api.acme.example.com` with an OpenAPI spec at `/openapi.json` and a static API key.

**Why this priority:** This is the core loop — register, expose endpoints as primitives, compose into a tool. Without it the feature delivers nothing.

**Independent Test:** Register an API with an OpenAPI URL and stored credentials, author a function that calls one endpoint, invoke the function as an MCP tool, and confirm only the extracted result enters context.

**Workflow:**
1. Developer: "Register the Acme Orders API from `https://api.acme.example.com/openapi.json`, auth with header `X-API-Key` = `sk_live_...` (store it)."
2. AI calls `add_api_server` with name `acme`, `openapi_url`, and an `auth` injection `{name:"api_key", location:"header", key:"X-API-Key", format:"{value}", source:"stored", value:"sk_live_..."}`.
3. MCPWorks fetches the spec, discovers 12 endpoints, encrypts the key, stores config + endpoint schemas. Returns: "Added API server 'acme' with 12 endpoints: list_orders, get_order, create_order, …".
4. Developer: "Make a tool that returns just the open order IDs and totals."
5. AI authors a function:
   ```python
   from functions import api__acme__list_orders
   resp = api__acme__list_orders(query={"status": "open", "limit": 200})
   result = [{"id": o["id"], "total": o["total"]} for o in resp["json"]["data"]]
   ```
6. The function is callable as a single MCP tool. The 200-order payload stays in the sandbox; only `id`/`total` pairs return.

**Success:** A REST API becomes a token-efficient MCP tool with no pre-built MCP server. Stored key never enters the sandbox or context.
**Failure:** OpenAPI fetch fails → clear error, server not added. Bad credentials surface on first call with an actionable message.

---

### 2.2 Secondary Scenario: Passthrough Credentials (End-User Brings Their Own Key) (Priority: P1)

**Actor:** Namespace owner publishing a shared API integration for multiple end-users/agents
**Goal:** Each consumer authenticates to the upstream API with their own credential, which MCPWorks never stores
**Context:** A SaaS API where every user has a personal token.

**Why this priority:** The passthrough model is half of the credential value proposition and the only way to support multi-tenant per-user keys safely.

**Independent Test:** Register an API with a `passthrough` auth injection bound to env var `ACME_TOKEN`, run a function in an execution that supplies `ACME_TOKEN`, and confirm the upstream call carries the token and nothing is persisted.

**Workflow:**
1. Owner: "Register Acme with a passthrough bearer token sourced from env var `ACME_TOKEN`."
2. AI calls `add_api_server` with `auth` injection `{name:"token", location:"bearer", format:"Bearer {value}", source:"passthrough", env_var:"ACME_TOKEN"}` (no value stored).
3. An agent/execution provides `ACME_TOKEN` via the existing env-passthrough mechanism (002).
4. At call time, the proxy reads `ACME_TOKEN` from the execution's transient env and injects `Authorization: Bearer <token>` into the upstream request.
5. The token is never written to the database, never logged, and never returned to the sandbox.

**Success:** Per-user credentials flow through MCPWorks to the upstream API without ever being stored.
**Failure:** Missing passthrough value → `{"error":"missing_credential","name":"token","action":"set ACME_TOKEN in execution env"}`.

---

### 2.3 Tertiary Scenario: Manual Endpoint Definition (No OpenAPI) (Priority: P2)

**Actor:** Developer integrating an API with no machine-readable spec
**Goal:** Define one endpoint by hand and call it
**Context:** A legacy API documented only in a README.

**Why this priority:** Many real APIs lack an OpenAPI spec; manual definition makes the feature universal, but the OpenAPI path covers the most common case first.

**Independent Test:** `add_api_server` with `spec_source=manual`, `add_manual_endpoint` for one `GET`, then call it from the sandbox.

**Workflow:**
1. Developer: "Register `https://legacy.example.com` manually. Add `GET /v2/widgets/{id}` returning a widget."
2. AI calls `add_api_server` (manual), then `add_manual_endpoint` with `operation_id="get_widget"`, `method="GET"`, `path="/v2/widgets/{id}"`, and a `param_schema` describing the path param `id`.
3. The endpoint becomes `api__legacy__get_widget(path={"id":"w_123"})` in the sandbox.

**Success:** APIs without specs are fully supported. Manual and imported endpoints coexist on one server.

---

### 2.4 Scenario: Publish a Raw Endpoint as a Direct MCP Tool (Priority: P3)

**Actor:** Developer who wants a simple endpoint exposed directly, no function wrapper
**Goal:** Expose `get_order` as an MCP tool without authoring a function
**Context:** The endpoint's response is already small and clean.

**Why this priority:** Convenience escape hatch; the functions-only default is the recommended path, so this is lowest priority.

**Independent Test:** `publish_endpoint` for one operation, confirm it appears as a direct MCP tool; `unpublish_endpoint` removes it.

**Workflow:**
1. Developer: "Publish acme's `get_order` directly."
2. AI calls `publish_endpoint(server="acme", operation_id="get_order")`.
3. `get_order` appears as a direct MCP tool (raw response, no sandbox extraction). A note warns the response is unfiltered and counts against context.

**Success:** A single endpoint can be exposed raw on demand without abandoning the functions-only default for everything else.

---

### Edge Cases

- **OpenAPI fetch fails / non-OpenAPI document** at add time → server not added, clear error.
- **OpenAPI with no `operationId`** → derive a stable handle as `{method}_{slugified_path}`; collisions get a numeric suffix.
- **`refresh_api_endpoints` removes an endpoint that is `published` or referenced by a function** → endpoint marked removed; refresh reports it; the function/tool fails at next call with a clear "endpoint no longer exists" error rather than silently disappearing.
- **Base URL or redirect resolves to a private IP** → blocked by SSRF gate (including DNS rebinding between registration and call).
- **Upstream redirect (3xx) to a denied host** → not followed across the SSRF boundary.
- **Path param missing at call time** → validation error naming the missing param.
- **Response exceeds `response_limit_bytes`** → truncated with a marker; sandbox code sees the truncation flag.
- **Endpoint name collides with a native function or MCP tool** → no collision; `api__` prefix guarantees uniqueness.
- **Server `enabled=false`** → endpoints not generated in the sandbox; calls rejected.
- **Endpoint `enabled=false`** → cataloged but not generated as a sandbox primitive; the LLM must enable it (FR-006a) before use.
- **Very large OpenAPI spec (e.g. 1000+ operations)** → all are discovered up to the safety ceiling (default 1000), cataloged as disabled, and returned as an inventory for the LLM to curate; beyond the ceiling, discovery truncates with a warning naming the count dropped.
- **Upstream returns non-JSON (HTML/binary)** → returned as text up to the size cap with a `content_type` field; binary flagged, not decoded.

---

## 3. Functional Requirements

### 3.1 API Server Registry

- **FR-001 (Add API Server, Must):** MCP tool `add_api_server` registers a REST API on the namespace. Parameters: `name` (unique per namespace, DNS-safe), `base_url`, `spec_source` (`openapi_url` | `openapi_file` | `manual`), `openapi_url` (for `openapi_url`) or `openapi_file` — the spec document passed inline as a JSON or YAML string (for `openapi_file`; MCP tools accept no file handles), `auth` (list of credential injection definitions), optional `default_headers`, optional `settings`, optional `enabled_endpoints` (list of `operation_id`s to enable). Behavior: validate base URL against SSRF denylist; if OpenAPI, fetch and parse into endpoints; encrypt stored credentials; persist config + endpoint schemas; return server name and the **discovered endpoint inventory** (operation_id, method, path, summary). Authorization: namespace owner.
- **FR-001a (Curated Endpoint Selection, Must):** Endpoint exposure is **LLM-curated, not capped by a fixed number.** Discovered endpoints are cataloged but default to **disabled**. Only endpoints the LLM/user enables (via `enabled_endpoints` at add time, or `enable_endpoint`/`disable_endpoint` after) are generated as sandbox primitives and counted toward the catalog token cost. For a large spec, `add_api_server` returns the full inventory and prompts the LLM to choose which endpoints to enable. A high safety ceiling (default 1000 discovered endpoints) guards against pathological specs; beyond it, discovery truncates with a warning.
- **FR-002 (Refresh Endpoints, Should):** MCP tool `refresh_api_endpoints` re-fetches the OpenAPI spec and diffs endpoints (added/removed/changed). Both the `enabled` and `published` flags are preserved by `operation_id` across refresh. Newly discovered endpoints default to disabled. Manual endpoints are untouched. Reports the diff. If fetch fails, cached endpoints are preserved. Authorization: namespace owner.
- **FR-003 (List API Servers, Must):** MCP tool `list_api_servers` returns all configured API servers: name, base_url, spec_source, endpoint_count, enabled, last_refreshed_at. Credentials are never returned. Authorization: read.
- **FR-004 (Describe API Server, Must):** MCP tool `describe_api_server` returns full detail: name, base_url, spec_source, settings, the `auth` injection definitions **with credential values redacted**, endpoint list (with published flags), enabled status, last_refreshed_at. Authorization: read.
- **FR-005 (List Endpoints, Must):** MCP tool `list_endpoints` returns endpoints for a server: operation_id, method, path, summary, enabled, published. Supports filtering by enabled/published so the LLM can review the full inventory or just the active set. Authorization: read.
- **FR-006 (Add Manual Endpoint, Must):** MCP tool `add_manual_endpoint` defines a single endpoint: `operation_id`, `method`, `path` (with `{param}` templating), `summary`, `param_schema`, `request_body_schema`, optional `response_schema`. A manually added endpoint is enabled by default (the user defined it deliberately). Coexists with imported endpoints. Authorization: namespace owner.
- **FR-006a (Enable / Disable Endpoints, Must):** MCP tools `enable_endpoint` and `disable_endpoint` toggle an endpoint's `enabled` flag (accepting one or more `operation_id`s). Enabling generates the sandbox primitive; disabling removes it from the catalog without deleting the cached schema. This is the curation mechanism referenced in FR-001a. Authorization: namespace owner.
- **FR-007 (Remove API Server, Must):** MCP tool `remove_api_server` deletes the server, its endpoints, and connection/credential material. Functions/agents referencing it fail clearly on next call. Authorization: namespace owner.
- **FR-008 (Update Settings, Must):** MCP tool `update_api_settings` updates LLM-tunable settings (`response_limit_bytes`, `timeout_seconds`, `max_calls_per_execution`, `retry_on_failure`, `retry_count`, `enabled`). Validates key/type. Returns full current settings. Authorization: namespace owner.

### 3.2 Credentials

- **FR-010 (Credential Injection Model, Must):** Each API server has an `auth` list of credential injections. Each injection has: `name` (logical), `location` (`header` | `query` | `bearer` | `basic`), `key` (header/param name; n/a for bearer/basic), `format` (value template, e.g. `"{value}"`, `"Bearer {value}"`, `"Token {value}"`), and `source` (`stored` | `passthrough`). A single server may mix sources.
- **FR-011 (Stored Credentials, Must):** `set_api_credentials` stores/updates a `stored` injection's secret value. The `auth` JSONB holds only the injection *definition*; secret values are persisted in a **separate encrypted column** (envelope encryption, KEK/DEK) as a map keyed by injection `name`. Stored values are injected server-side at call time and are never returned by any tool, never written to logs, and never visible to sandbox code. Because secrets never live in the `auth` JSONB, redaction of list/describe output is structural rather than a filtering step.
- **FR-012 (Passthrough Credentials, Must):** A `passthrough` injection carries no stored value and declares an `env_var`. At call time the proxy resolves the value **exclusively** from the execution's transient env (per 002 env-passthrough) by `env_var`. Sandbox code never supplies, sees, or handles passthrough values — there is no per-call-argument credential path. Passthrough values are never persisted and never logged. If the `env_var` is absent at call time, the proxy returns `{"error":"missing_credential","name":<injection>,"action":"set <env_var> in execution env"}`.
- **FR-013 (Credential Redaction, Must):** Any surface that lists or describes a server redacts credential values (stored and passthrough alike). Only injection *definitions* (name, location, key, format, source, env_var) are visible.
- **FR-014 (OAuth2 Deferred, Won't (v1)):** OAuth2 client-credentials and token-refresh flows are explicitly out of scope for v1; the `source` enum is designed to accept an `oauth2` value in a future spec without schema migration.

### 3.3 Sandbox Integration

- **FR-020 (Endpoint Wrappers, Must):** When a namespace has enabled API servers, `generate_functions_package()` generates a callable wrapper per **enabled** endpoint: `api__{server}__{operation_id}(path=..., query=..., body=..., headers=...)`. There is no credential parameter — credentials are injected server-side by the proxy. Wrappers post to the internal API proxy via the bridge key (same pattern as the MCP bridge).
- **FR-021 (Endpoint Catalog, Must):** The `functions/__init__.py` docstring gains an `[API: {server}]` section listing each **enabled** endpoint's signature and one-line summary (≤ ~20 tokens each) for discovery. Disabled endpoints are excluded from the catalog. Full schemas are available on demand, not loaded eagerly.
- **FR-022 (Functions-Only Default, Must):** Endpoints are **not** exposed as MCP tools by default. They are callable only from sandbox code unless explicitly published (FR-030).
- **FR-023 (Composition, Must):** A sandbox function may call multiple endpoints (and other primitives) and return a single result; raw upstream responses stay in the sandbox.

### 3.4 Internal API Proxy

- **FR-025 (Proxy Endpoint, Must):** `POST /v1/internal/api-proxy` proxies endpoint calls from the sandbox to the upstream API. Authenticated by the bridge key. The proxy resolves the namespace from the active execution record (no namespace parameter). Request body: `{"server": "...", "operation_id": "...", "path": {...}, "query": {...}, "body": ..., "headers": {...}}` (no credential field — the proxy injects credentials server-side).
- **FR-026 (Request Construction, Must):** The proxy builds the request as `base_url` + templated `path`, applying query params and request body, plus `default_headers`. It injects each `auth` injection per its location/format (decrypting stored values; resolving passthrough values).
- **FR-027 (SSRF Gate, Must):** Before every upstream call the proxy re-resolves the target host and rejects any request whose resolved address falls in a denied range (private, link-local, loopback, unique-local, metadata `169.254.169.254`). Redirects are not followed across the SSRF boundary.
- **FR-028 (Settings Enforcement, Must):** The proxy enforces `timeout_seconds`, `max_calls_per_execution` (counted against the execution context), and truncates responses larger than `response_limit_bytes` (with a truncation flag). Automatic retries (`retry_on_failure`/`retry_count`) apply **only to idempotent methods** (GET, HEAD, PUT, DELETE). POST and PATCH are never auto-retried — even when `retry_on_failure` is true — to avoid duplicating side effects (double-create/double-charge); their failures surface to sandbox code for explicit handling.
- **FR-029 (Response Handling, Must):** JSON responses are parsed and returned; non-JSON returned as text up to the size cap with `content_type`; the upstream status code is surfaced. Errors return a structured `{error, reason, action}` shape (≤ ~50 tokens).

### 3.5 Raw Endpoint Publishing (Opt-In)

- **FR-030 (Publish/Unpublish, Should):** MCP tools `publish_endpoint` and `unpublish_endpoint` toggle an endpoint's `published` flag. A published endpoint is exposed as a direct MCP tool (`api__{server}__{operation_id}`) whose raw response returns to the AI context. Publishing carries a warning that the response is unfiltered.

### 3.6 Agent Integration

- **FR-035 (Agent API Access, Must):** Agents specify which namespace API servers they may access by name via `agent.api_server_names` (ARRAY of VARCHAR), parallel to `mcp_server_names`. MCP tool `configure_agent_api_access` sets the list. The orchestrator resolves names to configs at run time.

### 3.7 Security

- **FR-040 (No Credentials in Sandbox, Must):** Neither stored nor passthrough credential values are accessible to sandbox code. The sandbox holds only the bridge key; the proxy injects credentials server-side.
- **FR-041 (Proxy Authorization, Must):** The proxy resolves the namespace from the bridge key's execution record and only permits API servers configured on that namespace; cross-namespace requests return 403.
- **FR-042 (Injection Defense, Should):** Upstream responses pass through the existing 009 prompt-injection rule engine; `output_trust` semantics carry over so untrusted responses can be wrapped/flagged before reaching the AI.
- **FR-043 (Rate / Volume Caps, Should):** Per-server `max_calls_per_execution` and `response_limit_bytes` bound abuse within a single execution.

### 3.8 Telemetry

- **FR-045 (api_proxy_calls, Must):** Every proxied call records a row in the `api_proxy_calls` table: namespace_id, api_server, operation_id, method, status_code, latency_ms, response_bytes, truncated, error_type (nullable), called_at. Credential values and request/response bodies are never recorded.

---

## 4. Key Entities

- **NamespaceApiServer:** A REST API registered on a namespace. Attributes: `namespace_id` (FK, CASCADE), `name` (unique per namespace, DNS-safe), `description`, `base_url`, `spec_source` (`openapi_url` | `openapi_file` | `manual`), `openapi_url` (nullable), `auth` (JSONB — credential-injection **definitions only**: name, location, key, format, source, env_var; never secret values), `credentials_encrypted` + `credentials_dek_encrypted` (separate encrypted column holding a name→secret map for `stored` injections, DEK/KEK), `default_headers_encrypted` + DEK, `settings` (JSONB), `enabled` (bool, LLM-tunable), `endpoint_count`, `last_refreshed_at`, timestamps. Unique(`namespace_id`, `name`).
- **ApiEndpoint:** One endpoint of an API server. Attributes: `api_server_id` (FK, CASCADE), `operation_id` (stable handle → `api__{server}__{operation_id}`), `method`, `path` (with `{param}` templating), `summary`, `param_schema` (JSON Schema: path/query/header params), `request_body_schema` (nullable), `response_schema` (nullable), `enabled` (bool — generated as a sandbox primitive when true; default false for imported, true for manual), `published` (bool, default false — direct raw MCP tool exposure), `source` (imported | manual), timestamps. Unique(`api_server_id`, `operation_id`).
- **api_proxy_calls:** Telemetry for each proxied call. Attributes: `namespace_id`, `api_server`, `operation_id`, `method`, `status_code`, `latency_ms`, `response_bytes`, `truncated`, `error_type` (nullable), `called_at`.
- **Agent (modified):** Adds `api_server_names` (ARRAY of VARCHAR) referencing NamespaceApiServer by name, parallel to existing `mcp_server_names`.

---

## 5. Success Criteria

### Measurable Outcomes

- **SC-001:** A developer can register an API from an OpenAPI URL and make their first successful sandbox call to one of its endpoints in under 5 minutes.
- **SC-002:** For a list-style endpoint returning ≥ 50 records, a composed function reduces tokens entering AI context by ≥ 90% versus returning the raw response.
- **SC-003:** 100% of attempts to register or call an API whose host resolves to a private/link-local/loopback/metadata address are blocked, including DNS-rebinding attempts evaluated at call time.
- **SC-004:** Stored and passthrough credential values appear in zero tool responses and zero log lines across the full test suite.
- **SC-005:** Endpoint discovery (fetch + parse + persist) for a spec with ≤ 100 operations completes in under 10 seconds.
- **SC-006:** Added proxy latency (excluding upstream response time) is under 50 ms per call at the median.
- **SC-007:** After `refresh_api_endpoints`, previously `published` endpoints that still exist remain published with no manual re-publish.

---

## 6. Constraints & Assumptions

### 6.1 Constraints

- REST/HTTP-JSON upstreams only in v1 (no GraphQL/gRPC/SOAP/WebSocket/streaming).
- The proxy runs in the API server process (no sidecar), consistent with the MCP proxy.
- v1 SSRF protection is a **global denylist** of private ranges; per-namespace hostname allowlists are deferred.
- OpenAPI 3.x and Swagger 2.0 import; obscure/invalid specs may require manual definition.
- Single request/response per call; large responses are size-capped, not streamed.

### 6.2 Assumptions

- The upstream API is reachable from the MCPWorks API server over HTTPS.
- Users understand that registering an API makes its endpoints available to all functions and (by name selection) agents in the namespace — namespace-scoped, not function-scoped.
- Passthrough credentials are delivered exclusively via the existing 002 env-passthrough mechanism (execution transient env); sandbox code never supplies them.
- **Risk if wrong:** If users expect per-function endpoint access control, v1 does not provide it (parallels the 008 limitation).

---

## 7. Dependencies

- **008 (MCP Server Plugins):** Proxy/bridge pattern, connection settings model, sandbox wrapper-generation pattern, agent name-reference pattern (`mcp_server_names`).
- **002 (Env Passthrough):** Source of passthrough credential values at runtime.
- **009 (Prompt Injection Defense):** Response rule engine and `output_trust` semantics reused for upstream responses.
- **010 (MCP Proxy Analytics):** Telemetry pattern that `api_proxy_call` mirrors.
- **Encryption core:** Envelope encryption (KEK/DEK) for stored credentials and default headers.

---

## 8. Future Considerations (v2+)

- OAuth2 client-credentials and refresh-token flows (`source: oauth2`).
- Per-namespace egress allowlists of hostnames in addition to the global denylist.
- Per-function endpoint access control.
- GraphQL and streaming upstream support.
- Pre-built API templates (one-click register for popular public APIs).
- Automatic spec drift detection / scheduled refresh.

---

## 9. Spec Completeness Checklist

- [x] Clear user value proposition stated
- [x] Success criteria defined and measurable
- [x] Functional requirements enumerated
- [x] Constraints and assumptions documented
- [x] Edge cases identified
- [x] Security requirements specified
- [x] Dependencies identified
- [x] Key entities defined
- [ ] Peer reviewed
- [ ] Constitution compliance reviewed

---

## 10. Approval

**Status:** Draft

**Approvals:**
- [ ] CTO (Simon Carr)

**Approved Date:** —
**Next Review:** —

---

## Changelog

**v0.1.0 (2026-05-29):**
- Initial draft.

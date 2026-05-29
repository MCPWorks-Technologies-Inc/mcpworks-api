# Implementation Plan: API → MCP (Ad-Hoc MCP from REST APIs)

**Branch**: `019-api-to-mcp` | **Date**: 2026-05-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/019-api-to-mcp/spec.md`

## Summary

Register a plain REST/HTTP API on a namespace and synthesize an ad-hoc MCP from it — the inverse of feature 008 (which wraps third-party MCP servers). Endpoints are discovered via OpenAPI import or manual definition, cataloged, and (when LLM-curated to `enabled`) generated as callable primitives inside the code sandbox under the `api__{server}__{operation_id}` prefix. Users/Claude author functions that compose endpoints into token-efficient MCP tools (functions-only by default; raw exposure is opt-in via `publish_endpoint`). Credentials are injected server-side by an internal proxy (`/v1/internal/api-proxy`) — either `stored` (encrypted at rest) or `passthrough` (resolved from the execution's transient env). A new SSRF gate guards user-supplied base URLs, and a separate `api_proxy_call` table records telemetry.

The design deliberately reuses 008's proven machinery (bridge-key proxy, encryption, code-mode wrapper generation, agent name-references) and diverges from it in two grounded ways, both justified in Complexity Tracking:
1. **Endpoints live in their own table** (`api_endpoints`), not a JSONB blob on the server row, because each endpoint carries queryable per-row state (`enabled`, `published`) that 008's stateless `tool_schemas` cache did not need.
2. **Stored secrets live in a dedicated encrypted column** keyed by injection name, while the `auth` JSONB holds only injection *definitions* — making redaction structural.

## Technical Context

**Language/Version**: Python 3.11+ (existing codebase)
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0 async, Pydantic v2, httpx (existing), structlog (existing), PyYAML (existing — OpenAPI YAML), jsonschema (existing — param-schema validation). New: a minimal in-house OpenAPI extractor (no new heavy dependency — see research.md).
**Storage**: PostgreSQL (existing) — new tables `namespace_api_servers`, `api_endpoints`, `api_proxy_calls`. No Redis dependency (proxy is stateless per call; reuses in-memory `exec_token_registry`).
**Testing**: pytest (existing)
**Target Platform**: Linux server (Docker container), `server0.pop11`
**Project Type**: Single backend project (extends existing mcpworks-api)
**Performance Goals**: Added proxy latency < 50 ms median (excl. upstream); OpenAPI discovery < 10 s for ≤ 100 operations
**Constraints**: Proxy runs in API server process (no sidecar); REST/HTTP-JSON only (no streaming); SSRF denylist enforced at call time with DNS-rebinding re-resolution; POST/PATCH never auto-retried
**Scale/Scope**: Up to 20 API servers per namespace; endpoints LLM-curated (default disabled), safety ceiling 1000 discovered endpoints per server

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec complete; 5 specify-clarifications + 4 clarify-clarifications resolved, zero open markers |
| II. Token Efficiency & Streaming | PASS | Functions-only default keeps raw responses in the sandbox; only enabled endpoints enter the catalog (~15-20 tokens each); curated import bounds catalog cost. No streaming needed (single request/response). |
| III. Transaction Safety & Security | PASS | Stored creds use existing KEK/DEK envelope encryption in a dedicated column; passthrough never persisted; proxy validates the execution is active and namespace-scoped; SSRF gate added. No multi-step credit operation introduced. |
| IV. Provider Abstraction & Observability | PASS | The upstream is the user's own API — no MCPWorks provider coupling. New `api_proxy_call` telemetry mirrors `mcp_proxy_call`; structured logs never include credentials or bodies. |
| V. API Contracts & Tests | PASS | New MCP management tools with defined JSON schemas (contracts/api-tools.md); unit + integration + E2E plan below. |

| Quality Standard | Status | Notes |
|-----------------|--------|-------|
| Code Quality | PASS | Mirrors existing patterns; type hints, ruff/black, complexity ≤ 10 |
| Documentation | PASS | quickstart.md + `describe_api_server` tool + catalog docstring discovery |
| Performance | PASS | < 50 ms proxy overhead target; httpx reused; no per-call DB N+1 (server + endpoints loaded together) |
| Security | PASS | New SSRF module (no existing helper); creds never in sandbox/logs; 009 injection rules reused on responses |

**Gate: PASSED** — divergences from 008 are documented in Complexity Tracking, not violations.

## Project Structure

### Documentation (this feature)

```text
specs/019-api-to-mcp/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api-tools.md     # MCP management tool contracts + internal proxy contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit.specify)
└── tasks.md             # Phase 2 output (via /speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── models/
│   ├── namespace_api_server.py     # New: NamespaceApiServer (config + auth defs + encrypted secrets)
│   ├── api_endpoint.py             # New: ApiEndpoint (per-endpoint enabled/published state)
│   ├── api_proxy_call.py           # New: ApiProxyCall telemetry (mirrors mcp_proxy_call.py)
│   ├── agent.py                    # Modified: add api_server_names ARRAY(String)
│   └── __init__.py                 # Modified: register 3 new models
├── services/
│   └── api_server.py               # New: registry CRUD, OpenAPI discovery/refresh, enable/disable,
│                                   #      credentials, publish/unpublish, agent access config
├── schemas/
│   └── api_server.py               # New: Pydantic schemas (requests + redacted responses)
├── core/
│   ├── ssrf.py                     # New: host resolution + private/link-local/loopback denylist
│   ├── openapi_import.py           # New: minimal OpenAPI 3.x / Swagger 2.0 → endpoint extractor
│   └── api_proxy.py                # New: proxy_api_call() — build request, inject creds, SSRF, httpx
├── mcp/
│   ├── tool_registry.py            # Modified: add API_SERVER_TOOLS dict (tool defs + schemas)
│   ├── create_handler.py           # Modified: TOOL_SCOPES entries + _add_api_server etc. handlers
│   └── code_mode.py                # Modified: _API_BRIDGE_TEMPLATE, _generate_api_* , extend
│                                   #           generate_functions_package(api_servers=...) + catalog
├── api/v1/
│   └── api_proxy.py                # New: POST /v1/internal/api-proxy endpoint (mirrors mcp_proxy.py)
└── main.py                         # Modified: include api_proxy router

alembic/versions/
└── 20260529_000001_add_api_to_mcp.py   # New: 3 tables + agent.api_server_names (down_revision 20260401_000001)

tests/
├── unit/
│   ├── test_ssrf.py                # Denylist coverage, DNS-rebinding, redirect-target checks
│   ├── test_openapi_import.py      # Spec parsing, operationId derivation, $ref deref, ceiling
│   ├── test_api_server_service.py  # CRUD, enable/disable, credential redaction, publish
│   └── test_api_proxy.py           # Request construction, cred injection, retry idempotency, truncation
├── integration/
│   └── test_api_to_mcp_e2e.py      # Register → curate → call from sandbox → result; passthrough path
└── fixtures/
    └── openapi_samples/            # Sample OpenAPI 3.x + Swagger 2.0 specs
```

**Structure Decision**: Extends the existing single-backend layout, mirroring 008's separation (model / service / schema / core-logic / mcp-handlers / api-endpoint). New cross-cutting concerns get their own `core/` modules: `ssrf.py` (reusable beyond this feature) and `openapi_import.py` (isolated, testable parsing). The proxy follows the established `api/v1/<x>_proxy.py` (HTTP) → `core/<x>_proxy.py` (logic) split.

## Phase 0: Research (→ research.md)

Unknowns / decisions to resolve:
1. **OpenAPI extraction approach** — add a dependency (`prance`/`openapi-spec-validator`) vs. in-house minimal extractor over `json`/`PyYAML` + `jsonschema`. (Lean: in-house, deps already present.)
2. **SSRF enforcement mechanism in httpx** — resolve-then-validate-then-pin vs. custom transport vs. validate-and-disable-redirects. Must defeat DNS rebinding and redirect-based bypass.
3. **OpenAPI `$ref` dereferencing scope** — local component refs only (v1) vs. remote refs (rejected: SSRF + complexity).
4. **operation_id derivation & collision strategy** when `operationId` is absent.
5. **Passthrough env resolution** — exact hook into 002 env-passthrough to read the transient env at proxy time without the value crossing the sandbox.
6. **Per-endpoint `param_schema` shape** — how path/query/header params + request body coexist in one JSON-Schema-ish structure the wrapper and proxy both understand.

## Phase 1: Design & Contracts (→ data-model.md, contracts/, quickstart.md)

1. **data-model.md** — `NamespaceApiServer`, `ApiEndpoint`, `ApiProxyCall`, `Agent` modification; field types, constraints, indexes, JSONB shapes (`auth`, `settings`, `param_schema`), and the encrypted-secret column layout.
2. **contracts/api-tools.md** — MCP management tool contracts (`add_api_server`, `refresh_api_endpoints`, `list_api_servers`, `describe_api_server`, `list_endpoints`, `add_manual_endpoint`, `enable_endpoint`, `disable_endpoint`, `remove_api_server`, `update_api_settings`, `set_api_credentials`, `publish_endpoint`, `unpublish_endpoint`, `configure_agent_api_access`) with input schemas + redacted response shapes; plus the internal `/v1/internal/api-proxy` request/response contract.
3. **quickstart.md** — end-to-end walkthrough: register via OpenAPI → curate endpoints → author a composing function → call it; plus the passthrough-credential recipe.
4. **Agent context update** — run `.specify/scripts/bash/update-agent-context.sh claude`.

## Phase 2: Tasks (via /speckit.tasks — not produced here)

Anticipated task groups (dependency-ordered): migration+models → SSRF module (+tests) → OpenAPI importer (+tests) → service layer → schemas → tool registry + create-handler dispatch → internal proxy endpoint + core proxy logic → code-mode bridge/wrappers/catalog → agent integration → E2E → docs. SSRF and OpenAPI importer are independent and parallelizable early.

## Complexity Tracking

| Divergence from 008 | Why Needed | Simpler Alternative Rejected Because |
|---------------------|------------|--------------------------------------|
| Separate `api_endpoints` table (vs. 008's `tool_schemas` JSONB) | Endpoints carry per-row, individually-queryable state: `enabled` (curation) and `published` (raw exposure). Refresh diffs and enable/disable operate per endpoint. | A JSONB array would require read-modify-write of the whole blob for every enable/disable and can't be indexed/filtered (`list_endpoints` filtering, FR-005). |
| Dedicated `credentials_encrypted` column keyed by injection name (vs. inline-in-JSONB) | Lets the `auth` JSONB hold only non-secret definitions, so list/describe redaction is structural — secrets are never serialized into a field that gets returned. | Inline-encrypted values in the JSONB mix secrets with definitions, risking accidental exposure in serialization and complicating redaction (resolved in clarify session). |
| New `core/ssrf.py` module | No SSRF/IP-denylist helper exists anywhere in the codebase; user-supplied base URLs are a new, high-severity attack surface absent in 008 (where URLs point at known MCP servers). | Reusing nothing exists to reuse; skipping it would violate Constitution III (Security by Default). |

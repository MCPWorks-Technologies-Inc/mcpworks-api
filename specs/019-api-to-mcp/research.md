# Research: API → MCP (Ad-Hoc MCP from REST APIs)

**Feature**: 019-api-to-mcp
**Date**: 2026-05-29
**Phase**: 0 (resolves NEEDS CLARIFICATION from plan Technical Context)

---

## R1. OpenAPI extraction approach

**Decision**: In-house minimal extractor (`core/openapi_import.py`) over the standard library + already-present `PyYAML` and `jsonschema`. No new dependency.

**Rationale**:
- The codebase already ships `pyyaml>=6.0.0` (YAML specs) and `jsonschema>=4.0.0` (validate the param schemas we derive). Adding `prance`/`openapi-core`/`openapi-spec-validator` pulls a large transitive tree for what is, for our needs, a focused extraction: walk `paths` → per-method `operation` objects → collect `operationId`, `parameters` (path/query/header), and `requestBody` schema.
- We do **not** need full spec validation or a runtime request validator — we only need enough structure to (a) list endpoints for curation and (b) build an upstream request. Over-validating would reject usable real-world specs that are slightly non-conformant.
- Keeps the dependency surface minimal (Constitution: production-readiness, supply-chain caution) and keeps parsing fully testable with local fixtures.

**Supports**: OpenAPI 3.0/3.1 (`paths`, `components.schemas`, `requestBody.content.<mime>.schema`) and Swagger 2.0 (`paths`, `definitions`, `parameters` with `in: body`). Both reduce to the same internal `ApiEndpoint` shape.

**Alternatives considered**:
- `prance` (resolves $refs, validates) — heavy, brings `openapi-spec-validator` + `jsonschema-specifications`; remote-$ref resolution is an SSRF risk we'd have to disable anyway.
- `openapi-core` — aimed at request/response validation at runtime; more than we need.

---

## R2. SSRF enforcement mechanism

**Decision**: **Resolve-then-validate-then-pin.** Before each upstream call, `core/ssrf.py` resolves the target hostname to all A/AAAA addresses, rejects if *any* resolved address is in a denied range, then issues the httpx request **pinned to a validated IP** (connect to the vetted address with the original `Host` header / SNI), with **redirects disabled** at the proxy boundary. If the upstream returns a 3xx, the proxy surfaces it rather than transparently following it; following requires re-running the full SSRF gate on the new location.

**Rationale**:
- **DNS rebinding** is defeated by validating the *resolved* addresses at call time and connecting to that exact vetted address — not by validating the hostname string at registration and trusting DNS later. Validation at registration alone is insufficient (attacker flips DNS after add).
- Rejecting if *any* resolved address is private blocks "split-horizon" tricks where one record is public and another is `10.x`.
- Disabling auto-redirect closes the most common bypass (public URL 302→`http://169.254.169.254/...`).

**Denied ranges** (IPv4 + IPv6, via stdlib `ipaddress`): loopback (`127.0.0.0/8`, `::1`), private (`10/8`, `172.16/12`, `192.168/16`, `fc00::/7`), link-local (`169.254/16` incl. cloud metadata `169.254.169.254`, `fe80::/10`), unspecified (`0.0.0.0`, `::`), and IPv4-mapped IPv6 forms of the above. Scheme restricted to `http`/`https`; non-standard ports allowed but logged.

**Implementation note**: httpx supports pinning by building the request to the literal IP while setting `headers["Host"]` and (for TLS) `extensions`/SNI to the original hostname; alternatively resolve and validate, then make the normal request immediately (small TOCTOU window) — v1 takes the pinned approach for GET/idempotent and the resolve-then-immediately-request approach is the documented fallback. Final mechanism settled in the proxy task; the security contract (no private targets, no silent redirects) is fixed here.

**Alternatives considered**:
- Validate hostname only at registration — rejected (DNS rebinding).
- Custom httpx transport that re-validates every socket connect — strongest, but more code; revisit in v2 if the pinning approach proves brittle.
- Egress proxy/allowlist — deferred to v2 per spec scope.

---

## R3. OpenAPI `$ref` dereferencing scope

**Decision**: Resolve **local component refs only** (`#/components/schemas/...`, `#/definitions/...`). Remote/URL `$ref`s are **not** fetched.

**Rationale**: Remote ref fetching is itself an SSRF vector and a reliability hazard (fetching arbitrary URLs during registration). Local deref covers the overwhelming majority of real specs. Unresolvable refs degrade gracefully: the endpoint is still imported; its `param_schema`/`request_body_schema` falls back to a permissive `{"type":"object"}` with a note, and the user can refine via `add_manual_endpoint` semantics later.

**Alternatives considered**: Full recursive remote deref (rejected — SSRF, latency, failure modes).

---

## R4. operation_id derivation & collision strategy

**Decision**: Use the spec's `operationId` when present, normalized to a DNS/identifier-safe slug (`[a-z0-9_]`, lowercased, non-conforming chars → `_`). When absent, derive `{method}_{slugified_path}` (e.g. `GET /v2/widgets/{id}` → `get_v2_widgets_id`). On collision within a server, append `_2`, `_3`, … deterministically by document order.

**Rationale**: `operation_id` is the stable handle that forms `api__{server}__{operation_id}` (Python-callable, must be a valid identifier) and the `(api_server_id, operation_id)` unique key used to preserve `enabled`/`published` across refresh. Determinism by document order keeps refresh diffs stable.

**Alternatives considered**: Hashing the path (rejected — opaque, unfriendly to LLM authoring). Failing on missing operationId (rejected — many real specs omit it).

---

## R5. Passthrough env resolution (tie-in to 002 env-passthrough)

**Decision**: The proxy resolves passthrough credential values from the **execution's transient env**, the same source 002 makes available to a running sandbox, read **server-side at proxy time** via the execution context — never from the sandbox request body. The `ExecutionContext` (keyed by bridge key in `exec_token_registry`) is the join point; the proxy looks up the declared `env_var` for each `passthrough` injection and formats it into the request.

**Rationale**: Preserves the clarified guarantee (FR-012/FR-040): sandbox code never supplies or sees credential values. Because 002 already scopes the transient env to the execution, the value lives only for the execution lifetime and is never persisted. If the `env_var` is absent, the proxy returns a structured `missing_credential` error.

**Open implementation detail for Phase 2**: confirm whether the transient env is reachable from the proxy via the `ExecutionContext` directly or must be threaded through the registry at sandbox creation (002 integration point). Either way the value does not transit the sandbox→proxy request body. This is a wiring detail, not a design fork.

**Alternatives considered**: Per-call argument from sandbox (rejected in clarify session — breaks the no-credentials-in-sandbox guarantee).

---

## R6. Unified `param_schema` shape

**Decision**: One JSON object per endpoint capturing parameter location explicitly:

```json
{
  "path":   { "type": "object", "properties": { "id": {"type": "string"} }, "required": ["id"] },
  "query":  { "type": "object", "properties": { "status": {"type": "string"}, "limit": {"type": "integer"} } },
  "header": { "type": "object", "properties": {} }
}
```

`request_body_schema` is stored separately (the body's JSON Schema). The sandbox wrapper signature `api__{server}__{op}(path=..., query=..., body=..., headers=...)` maps 1:1 to these buckets, and the proxy uses the same buckets to template the path, attach query params, set headers, and serialize the body.

**Rationale**: Keeping location explicit (rather than a flat param list with `in` tags) makes both wrapper generation and proxy request construction trivial and unambiguous, and matches how the wrapper exposes arguments. Validation (optional, v1-best-effort) reuses the present `jsonschema` library.

**Alternatives considered**: Flat OpenAPI-style parameter array with `in` field (rejected — forces both wrapper and proxy to re-bucket on every call).

---

## Summary of Decisions

| # | Decision |
|---|----------|
| R1 | In-house OpenAPI extractor; no new dependency (reuse PyYAML + jsonschema) |
| R2 | Resolve-then-validate-then-pin SSRF gate; redirects not auto-followed; deny private/link-local/loopback/metadata |
| R3 | Local `$ref` deref only; graceful fallback on unresolved refs |
| R4 | `operationId` slug, else `{method}_{slug(path)}`; deterministic collision suffixes |
| R5 | Passthrough resolved server-side from execution transient env (002); never via sandbox body |
| R6 | Location-bucketed `param_schema` (path/query/header) + separate `request_body_schema` |

All plan-level NEEDS CLARIFICATION resolved. Ready for Phase 1.

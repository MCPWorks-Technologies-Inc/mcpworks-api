---
description: "Task list for 019-api-to-mcp implementation"
---

# Tasks: API → MCP (Ad-Hoc MCP from REST APIs)

**Input**: Design documents from `/specs/019-api-to-mcp/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-tools.md

**Tests**: INCLUDED — the Constitution mandates ≥80% coverage (95% for credential/proxy paths) and this feature carries security-sensitive surfaces (SSRF, credential injection). Test tasks accompany each story.

**Organization**: Grouped by user story. The shared end-to-end backbone (models, SSRF, server CRUD, internal proxy, code-mode bridge) lives in Foundational because all four stories require it to make an endpoint callable from the sandbox. Each story then adds an independently-testable capability slice.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: US1–US4 for user-story phases only
- All paths are relative to repo root `/mnt/c/Users/simon/dev/mcpworks.io/mcpworks-api/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Test fixtures and dependency confirmation. No new runtime dependency (research R1).

- [x] T001 [P] Create `tests/fixtures/openapi_samples/` with three specs: an OpenAPI 3.0 spec (with `operationId`s, path+query params, a POST body), an OpenAPI 3.1 spec (with local `$ref` components), and a Swagger 2.0 spec (with `in: body` parameter and a missing `operationId`)
- [x] T002 [P] Confirm `pyyaml`, `jsonschema`, `httpx` are present in `pyproject.toml` and that no new runtime dependency is required (record in `research.md` if any gap found)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared backbone that makes a manually-defined, stored-credential endpoint callable from the sandbox and composable into a function. **No user story can begin until this phase is complete.**

**⚠️ CRITICAL**: Blocks all of Phase 3+.

### Data layer

- [x] T003 Create Alembic migration `alembic/versions/20260529_000001_add_api_to_mcp.py` (down_revision `20260401_000001`): tables `namespace_api_servers`, `api_endpoints`, `api_proxy_calls`, plus `agents.api_server_names` column and all indexes per data-model.md
- [x] T004 [P] Create `NamespaceApiServer` model in `src/mcpworks_api/models/namespace_api_server.py` (auth JSONB, `credentials_encrypted`/`credentials_dek_encrypted`, `default_headers_encrypted`/dek, settings, enabled, endpoint_count, last_refreshed_at)
- [x] T005 [P] Create `ApiEndpoint` model in `src/mcpworks_api/models/api_endpoint.py` (operation_id, method, path, param_schema, request_body_schema, response_schema, enabled, published, source)
- [x] T006 [P] Create `ApiProxyCall` model in `src/mcpworks_api/models/api_proxy_call.py` (namespace_id, api_server, operation_id, method, status_code, latency_ms, response_bytes, truncated, error_type, called_at)
- [x] T007 Add `api_server_names: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)` to `src/mcpworks_api/models/agent.py`
- [x] T008 Register the three new models in `src/mcpworks_api/models/__init__.py`

### Security primitive

- [x] T009 [P] Implement SSRF gate in `src/mcpworks_api/core/ssrf.py`: resolve hostname to A/AAAA, reject if ANY address is private/link-local/loopback/unspecified/metadata (`169.254.169.254`) for IPv4 + IPv6 (incl. IPv4-mapped), scheme restricted to http/https, plus a pinned-request / no-auto-redirect helper for httpx (research R2)
- [x] T010 [P] Unit tests for SSRF in `tests/unit/test_ssrf.py`: each denied range, DNS-rebinding (resolved-IP validation), redirect-target rejection, IPv4-mapped IPv6, public host passes

### Shared service + tools + proxy + sandbox

- [x] T011 [P] Create Pydantic schemas in `src/mcpworks_api/schemas/api_server.py` (add/describe/list requests + **credential-redacted** response models, endpoint summary, settings)
- [x] T012 Implement `src/mcpworks_api/services/api_server.py` backbone: server CRUD (`add` manual path, `list`, `describe` with redaction, `remove`, `update_settings`), `list_endpoints` (with enabled/published filtering), encrypted stored-credential helpers (`set_api_credentials` via `core/encryption.encrypt_value`), `add_manual_endpoint`, `enable_endpoint`/`disable_endpoint` (depends T004–T008, T011)
- [x] T013 Register `API_SERVER_TOOLS` (tool defs + JSON input schemas per contracts/api-tools.md) in `src/mcpworks_api/mcp/tool_registry.py`
- [x] T014 Add `TOOL_SCOPES` entries and dispatch handlers (`_add_api_server`, `_list_api_servers`, `_describe_api_server`, `_remove_api_server`, `_update_api_settings`, `_set_api_credentials`, `_add_manual_endpoint`, `_list_endpoints`, `_enable_endpoint`, `_disable_endpoint`, `_configure_agent_api_access`) in `src/mcpworks_api/mcp/create_handler.py` (depends T012, T013)
- [x] T015 Implement `src/mcpworks_api/core/api_proxy.py` `proxy_api_call(ctx, server, operation_id, path, query, body, headers, db)`: resolve+namespace-scope server/endpoint, build `base_url`+templated path/query/body/default-headers, inject **stored** creds (decrypt), SSRF gate, httpx call with `timeout_seconds` and idempotent-only retry (never POST/PATCH), truncate at `response_limit_bytes`, record `ApiProxyCall` (depends T004–T006, T009)
- [x] T016 Create `POST /v1/internal/api-proxy` in `src/mcpworks_api/api/v1/api_proxy.py` (bridge key → `resolve_execution` → `proxy_api_call`, 403 on invalid/cross-namespace) and include the router in `src/mcpworks_api/main.py` (depends T015)
- [x] T017 Extend `src/mcpworks_api/mcp/code_mode.py`: add `_API_BRIDGE_TEMPLATE` (`functions/_api_bridge.py` → `_call_api_endpoint`), `_generate_api_wrapper`, `_generate_api_server_module`, extend `generate_functions_package(..., api_servers=None)` to emit `functions/_api/{server}.py`, and add an `[API: {server}]` section listing **enabled** endpoints to the catalog docstring (depends T016)
- [x] T018 Wire enabled API-server endpoints into every `generate_functions_package(...)` call site (sandbox package assembly) so primitives appear in executions (depends T017, T012)

**Checkpoint**: A manually-defined endpoint with a stored credential is callable from the sandbox as `api__{server}__{op}` and composable into a function; SSRF and telemetry active.

---

## Phase 3: User Story 1 — Register via OpenAPI & Compose a Function (Priority: P1) 🎯 MVP

**Goal**: Import an OpenAPI spec, curate which endpoints to enable, and compose enabled endpoints into a token-efficient function/tool.

**Independent Test**: Register the `acme` OpenAPI fixture (mocked upstream), enable two endpoints, author a function that calls one and returns only extracted fields, invoke it, and assert the raw payload never leaves the sandbox.

- [x] T019 [P] [US1] Implement `src/mcpworks_api/core/openapi_import.py`: parse OpenAPI 3.0/3.1 + Swagger 2.0, local `$ref` deref only, `operationId` slug else `{method}_{slug(path)}` with deterministic collision suffixes, location-bucketed `param_schema` (path/query/header) + `request_body_schema`, 1000-endpoint safety ceiling (research R1/R3/R4/R6)
- [x] T020 [P] [US1] Unit tests in `tests/unit/test_openapi_import.py` against the three fixtures: operationId derivation, `$ref` resolution + fallback, Swagger 2.0 body param, ceiling truncation warning
- [x] T021 [US1] Extend `add_api_server` in `src/mcpworks_api/services/api_server.py` for `spec_source` `openapi_url`/`openapi_file`: fetch spec via SSRF-checked httpx, import endpoints as disabled, apply optional `enabled_endpoints`, set `endpoint_count`/`last_refreshed_at` (depends T012, T019)
- [x] T022 [US1] Implement `refresh_api_endpoints` in the service + its dispatch handler in `create_handler.py`: diff added/removed/changed, preserve `enabled`/`published` by `operation_id`, mark removed (depends T021, T014)
- [ ] T023 [US1] Integration test in `tests/integration/test_api_to_mcp_e2e.py`: register OpenAPI fixture → `enable_endpoint` → author composing function → call → assert only extracted fields returned and raw response absent from AI-visible output; refresh preserves enabled set (depends T021, T022, Phase 2)

**Checkpoint**: The headline flow works end-to-end — this is the MVP.

---

## Phase 4: User Story 2 — Passthrough Credentials (Priority: P1)

**Goal**: End-user/agent supplies their own credential at runtime via the execution env; MCPWorks injects it server-side and never persists or logs it.

**Independent Test**: Register a server with a `passthrough` bearer injection bound to `ACME_TOKEN`; run a call in an execution that supplies `ACME_TOKEN`; assert the upstream request carried `Authorization: Bearer <token>`, the value is absent from DB and logs, and a missing var yields the structured `missing_credential` error.

- [x] T024 [US2] Add passthrough resolution to `src/mcpworks_api/core/api_proxy.py`: for each `passthrough` injection read its `env_var` from the execution's transient env server-side, format per template, inject; structured `missing_credential` error when absent (depends T015, research R5)
- [x] T025 [US2] Add `passthrough_env: dict[str, str]` to `ExecutionContext` (`src/mcpworks_api/core/exec_token_registry.py`); populate it at sandbox creation with only the declared passthrough `env_var`s from the same 002 source used to build the sandbox env; clear on sandbox exit. Proxy reads `ctx.passthrough_env[env_var]` server-side (never via the sandbox→proxy body) (depends T024)
- [x] T026 [P] [US2] Tests in `tests/unit/test_api_proxy.py` + `tests/integration/test_api_to_mcp_e2e.py`: passthrough injected from env, value never persisted/logged (assert against DB row + captured logs), missing var → structured error (depends T024, T025)

**Checkpoint**: Both stored and passthrough credential models work; the no-credentials-in-sandbox guarantee holds.

---

## Phase 5: User Story 3 — Manual Endpoint Definition (Priority: P2)

**Goal**: Register an API with no OpenAPI spec and define endpoints by hand.

**Independent Test**: `add_api_server` with `spec_source=manual`, `add_manual_endpoint` for `GET /v2/widgets/{id}`, then call `api__legacy__get_widget(path={"id":"w_123"})` from the sandbox.

- [x] T027 [US3] Harden the `spec_source=manual` flow and `add_manual_endpoint` validation in `src/mcpworks_api/services/api_server.py`: identifier-safe `operation_id`, valid method, location-bucketed `param_schema` validation (jsonschema), manual endpoints default `enabled=true`, mixed manual+imported coexistence (depends T012)
- [ ] T028 [US3] Integration test in `tests/integration/test_api_to_mcp_e2e.py`: manual server → `add_manual_endpoint` GET with path param → call from sandbox returns upstream JSON; reject invalid operation_id/method (depends T027, Phase 2)

**Checkpoint**: APIs without specs are fully supported alongside imported ones.

---

## Phase 6: User Story 4 — Publish a Raw Endpoint as a Direct MCP Tool (Priority: P3)

**Goal**: Opt-in exposure of a single endpoint as a direct MCP tool returning the raw response.

**Independent Test**: `publish_endpoint` for `get_order` → it appears as a direct MCP tool returning the raw response with the unfiltered-warning; `unpublish_endpoint` removes it.

- [x] T029 [US4] Implement `publish_endpoint`/`unpublish_endpoint` in the service + dispatch handlers in `src/mcpworks_api/mcp/create_handler.py` (toggle `ApiEndpoint.published`) (depends T012, T014)
- [ ] T030 [US4] Expose published endpoints as direct MCP tools in `src/mcpworks_api/mcp/run_handler.py` (and any code-mode catalog note) — raw response returned, unfiltered-warning surfaced (depends T017, T029)
- [ ] T031 [US4] Integration test in `tests/integration/test_api_to_mcp_e2e.py`: publish → tool listed + returns raw response → unpublish → tool gone (depends T029, T030)

**Checkpoint**: All four stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T032 [P] Tests for credential redaction (`describe_api_server`/`list_api_servers` never echo values) and `api_proxy_call` telemetry correctness in `tests/unit/test_api_server_service.py`
- [ ] T033 Orchestrator integration: resolve `agent.api_server_names` so an agent's runs expose its API servers' enabled endpoints (parallel to `mcp_server_names` resolution) in the agent orchestrator (depends T007, T014)
- [ ] T034 [P] Apply 009 prompt-injection rules + `output_trust` wrapping to upstream responses in `src/mcpworks_api/core/api_proxy.py` (depends T015)
- [x] T035 [P] Enforce max 20 API servers per namespace in `add_api_server` and surface the 1000-endpoint safety-ceiling warning in responses (depends T012, T021)
- [ ] T036 [P] Update `quickstart.md` validation pass + add a short API→MCP section to `SPEC.md`/docs; verify catalog token cost per endpoint ≤ ~20 tokens
- [ ] T037 Run `ruff format`, `ruff check --fix`, `mypy src/`; ensure coverage ≥ 80% overall and ≥ 95% on `core/api_proxy.py`, `core/ssrf.py`, and credential paths

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (P1)**: no dependencies.
- **Foundational (P2)**: depends on Setup; **blocks all stories**. Internal order: T003 → (T004–T008) → T012; T009 → T015; T013 → T014; T015 → T016 → T017 → T018. T009/T010/T011 parallelizable early.
- **US1 (P3)**: depends on Foundational. T019 → T021 → T022 → T023.
- **US2 (P4)**: depends on Foundational (T015). Independent of US1.
- **US3 (P5)**: depends on Foundational (T012). Independent of US1/US2.
- **US4 (P6)**: depends on Foundational (T017) + its own T029.
- **Polish (P7)**: after the targeted stories.

### Story independence

- US1, US2, US3 are independently testable once Foundational is done. US4 layers on the code-mode/run-handler backbone (T017) but is testable on its own slice.

### Parallel opportunities

- Setup: T001, T002 together.
- Foundational: T004/T005/T006 (models) together; T009+T010 (SSRF) and T011 (schemas) alongside models.
- US1: T019 + T020 together (impl + its unit tests against fixtures).
- Across teams after Foundational: one dev on US1, one on US2, one on US3 in parallel.

---

## Parallel Example: Foundational models + SSRF + schemas

```bash
Task: "Create NamespaceApiServer model in src/mcpworks_api/models/namespace_api_server.py"   # T004
Task: "Create ApiEndpoint model in src/mcpworks_api/models/api_endpoint.py"                    # T005
Task: "Create ApiProxyCall model in src/mcpworks_api/models/api_proxy_call.py"                 # T006
Task: "Implement SSRF gate in src/mcpworks_api/core/ssrf.py"                                   # T009
Task: "Create Pydantic schemas in src/mcpworks_api/schemas/api_server.py"                      # T011
```

---

## Implementation Strategy

### MVP (Foundational + US1)

1. Phase 1 Setup → Phase 2 Foundational (the backbone).
2. Phase 3 US1 (OpenAPI register → curate → compose → call).
3. **STOP and validate** US1 independently (T023). This is the demoable MVP.

### Incremental delivery

1. Foundational → backbone callable (manual endpoint + stored cred).
2. + US1 → OpenAPI import & composition (MVP).
3. + US2 → passthrough credentials (multi-tenant BYO-key).
4. + US3 → manual-only APIs.
5. + US4 → raw endpoint publishing.
6. Polish → agent integration, injection rules, limits, lint/type/coverage.

---

## Notes

- `[P]` = different files, no incomplete dependency.
- Credential values must never appear in tool output, logs, or `api_proxy_call` rows — assert this explicitly in tests (T026, T032).
- POST/PATCH are never auto-retried (T015) — verify in proxy tests.
- SSRF is validated at call time, not just registration (T009/T010) — verify DNS-rebinding case.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.

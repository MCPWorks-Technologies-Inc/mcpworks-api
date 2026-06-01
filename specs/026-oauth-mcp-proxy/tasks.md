# Tasks: OAuth for MCP Server Proxy

**Input**: Design documents from `/specs/026-oauth-mcp-proxy/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Included — security-critical feature requires unit test coverage for token lifecycle, device flow polling, and proxy integration.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

---

## Phase 1: Setup

**Purpose**: Database migration and model changes

- [ ] T001 Add `auth_type`, `oauth_config_encrypted`, `oauth_config_dek`, `oauth_tokens_encrypted`, `oauth_tokens_dek`, `oauth_tokens_expires_at` columns to NamespaceMcpServer model in src/mcpworks_api/models/namespace_mcp_server.py
- [ ] T002 Add `auth_type` validator (must be "bearer", "oauth2", or "none") and defaults (auth_type="bearer") in src/mcpworks_api/models/namespace_mcp_server.py
- [ ] T003 Create Alembic migration for OAuth columns in alembic/versions/20260413_000001_add_mcp_oauth.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core OAuth service that all user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Create `services/mcp_oauth.py` with `McpOAuthService` class — constructor takes `db: AsyncSession`, holds reference to encryption helpers in src/mcpworks_api/services/mcp_oauth.py
- [ ] T005 Implement `_encrypt_oauth_config(config: dict) -> tuple[bytes, bytes]` and `_decrypt_oauth_config(server) -> dict` using existing `encrypt_value`/`decrypt_value` from core/encryption.py in src/mcpworks_api/services/mcp_oauth.py
- [ ] T006 Implement `_encrypt_oauth_tokens(tokens: dict) -> tuple[bytes, bytes]` and `_decrypt_oauth_tokens(server) -> dict` using same encryption pattern in src/mcpworks_api/services/mcp_oauth.py
- [ ] T007 Implement `get_oauth_status(server) -> str` — returns "not_configured", "pending_authorization", "authorized", or "expired" based on auth_type, token presence, and expires_at in src/mcpworks_api/services/mcp_oauth.py
- [ ] T008 [P] Create unit tests for encryption round-trip and status logic in tests/unit/test_mcp_oauth_service.py

**Checkpoint**: OAuth service foundation exists — encryption, decryption, status checking

---

## Phase 3: User Story 1 — First-Time OAuth Setup via Device Flow (Priority: P0)

**Goal**: User registers an OAuth MCP server and completes authorization via RFC 8628 device flow

**Independent Test**: Call `add_mcp_server` with `auth_type="oauth2"`, trigger a tool call, verify AUTH_REQUIRED response with user_code and verification_uri, mock provider approval, verify tokens stored

### Tests for User Story 1

- [ ] T009 [P] [US1] Unit test: `initiate_device_flow()` requests device code from provider, stores in Redis, returns AUTH_REQUIRED response in tests/unit/test_mcp_oauth_service.py
- [ ] T010 [P] [US1] Unit test: `exchange_device_code()` exchanges code for tokens, encrypts, stores in DB in tests/unit/test_mcp_oauth_service.py
- [ ] T011 [P] [US1] Unit test: device flow poller handles `authorization_pending`, `slow_down`, `expired_token`, and success responses in tests/unit/test_device_flow_poller.py

### Implementation for User Story 1

- [ ] T012 [US1] Implement `initiate_device_flow(server, db) -> dict` — POST to device_authorization_endpoint with client_id + scope, store device_code/user_code/interval in Redis (`mcp_oauth_device:{ns_id}:{server_name}`, TTL from provider), return AUTH_REQUIRED response dict in src/mcpworks_api/services/mcp_oauth.py
- [ ] T013 [US1] Implement `exchange_device_code(server, device_code, db)` — POST to token_endpoint with `grant_type=urn:ietf:params:oauth:grant-type:device_code`, encrypt tokens, store in DB, update `oauth_tokens_expires_at`, delete Redis device state in src/mcpworks_api/services/mcp_oauth.py
- [ ] T014 [US1] Implement `get_active_device_code(server) -> dict | None` — check Redis for active device code, return existing user_code/verification_uri if poller is already running (prevent duplicate generation) in src/mcpworks_api/services/mcp_oauth.py
- [ ] T015 [US1] Create `tasks/device_flow_poller.py` with `poll_device_code(namespace_id, server_name)` — async task that polls token_endpoint every `interval` seconds, handles RFC 8628 error responses, calls `exchange_device_code` on success, exits on expiry in src/mcpworks_api/tasks/device_flow_poller.py
- [ ] T016 [US1] Integrate device flow into proxy: in `proxy_mcp_call()`, if `server.auth_type == "oauth2"` and no tokens, check for active device code (return existing AUTH_REQUIRED) or call `initiate_device_flow()` + spawn poller via `asyncio.create_task()`, return AUTH_REQUIRED as ProxyResult in src/mcpworks_api/core/mcp_proxy.py

**Checkpoint**: Device flow end-to-end works — AUTH_REQUIRED returned, poller runs, tokens stored on approval

---

## Phase 4: User Story 2 — Silent Token Refresh (Priority: P0)

**Goal**: Expired access tokens are refreshed transparently using the stored refresh token

**Independent Test**: Store tokens with expired `oauth_tokens_expires_at`, trigger tool call, verify refresh happens before proxy call, verify new tokens stored

### Tests for User Story 2

- [ ] T017 [P] [US2] Unit test: `refresh_token_if_needed()` refreshes when expires_at < now + 5min in tests/unit/test_mcp_oauth_service.py
- [ ] T018 [P] [US2] Unit test: `refresh_token_if_needed()` returns existing tokens when still fresh in tests/unit/test_mcp_oauth_service.py
- [ ] T019 [P] [US2] Unit test: refresh failure with `invalid_grant` triggers re-auth (returns AUTH_REQUIRED) in tests/unit/test_mcp_oauth_service.py
- [ ] T020 [P] [US2] Unit test: concurrent refresh requests use Redis lock, only one refresh executes in tests/unit/test_mcp_oauth_service.py

### Implementation for User Story 2

- [ ] T021 [US2] Implement `refresh_token_if_needed(server, db) -> dict` — check `oauth_tokens_expires_at`, if within 5 min of expiry: acquire Redis lock (`mcp_oauth_refresh:{ns_id}:{server}`, 30s TTL), POST to token_endpoint with `grant_type=refresh_token`, encrypt + store new tokens, update expires_at, release lock. Return decrypted headers dict in src/mcpworks_api/services/mcp_oauth.py
- [ ] T022 [US2] Implement `get_oauth_headers(server, db) -> dict` — if tokens fresh, decrypt and return `{"Authorization": "Bearer {access_token}"}`. If stale, call `refresh_token_if_needed`. If refresh fails with invalid_grant, return None (caller handles as AUTH_REQUIRED) in src/mcpworks_api/services/mcp_oauth.py
- [ ] T023 [US2] Integrate refresh into proxy: in `proxy_mcp_call()`, replace static header decryption with `get_oauth_headers()` for oauth2 servers. On None return, initiate device/auth code flow. On 401 from external server, attempt one refresh + retry before returning AUTH_REQUIRED in src/mcpworks_api/core/mcp_proxy.py
- [ ] T024 [US2] Evict MCP pool connection after token refresh — call `mcp_pool.evict()` when tokens change so new connection uses fresh headers in src/mcpworks_api/core/mcp_proxy.py

**Checkpoint**: Token lifecycle is fully automated — proactive refresh, reactive 401 handling, concurrent-safe

---

## Phase 5: User Story 3 — HITL Auth Surfacing Through LLM (Priority: P0)

**Goal**: AUTH_REQUIRED responses are structured for AI agents to present naturally in conversation

**Independent Test**: Trigger tool call on unauthorized server, verify response structure, verify AI can extract user_code and verification_uri, verify retry after approval succeeds

### Implementation for User Story 3

- [ ] T025 [US3] Ensure AUTH_REQUIRED ProxyResult in `proxy_mcp_call()` uses the structured format from spec (auth_required, provider, verification_uri, user_code, message, expires_in, flow) — not a generic error in src/mcpworks_api/core/mcp_proxy.py
- [ ] T026 [US3] In code-mode execution: verify sandbox code calling an unauthorized MCP tool gets the AUTH_REQUIRED dict as a function return value (not an exception/crash) — trace through `_execute_namespace_function` → `mcp_pool.call_tool()` → ProxyResult flow in src/mcpworks_api/mcp/code_mode.py and src/mcpworks_api/tasks/orchestrator.py
- [ ] T027 [US3] On retry while poller is active: return same user_code and verification_uri from Redis (via `get_active_device_code()`) with message "Authorization still pending — polling for approval" in src/mcpworks_api/core/mcp_proxy.py

**Checkpoint**: AI agents can present device flow authorization naturally in any MCP client

---

## Phase 6: User Story 4 — OAuth Config via MCP Tools (Priority: P1)

**Goal**: Namespace owners configure OAuth through existing add/update/describe/remove MCP tools

**Independent Test**: Call `add_mcp_server` with `auth_type="oauth2"` and `oauth_config`, verify encrypted storage, call `describe_mcp_server` to see oauth_status

### Implementation for User Story 4

- [ ] T028 [US4] Update `add_mcp_server` tool handler to accept `auth_type` and `oauth_config` parameters — validate config structure, encrypt and store in src/mcpworks_api/services/mcp_server.py and src/mcpworks_api/mcp/tool_registry.py
- [ ] T029 [US4] Update `update_mcp_server` tool handler — if scopes change, clear stored tokens (require re-auth) in src/mcpworks_api/services/mcp_server.py
- [ ] T030 [US4] Update `describe_mcp_server` response to include `oauth_status`, `oauth_scopes`, `oauth_expires_at` (never expose tokens or client_secret) in src/mcpworks_api/services/mcp_server.py
- [ ] T031 [US4] Update `remove_mcp_server` to clean up OAuth tokens, Redis device state, and cancel any active poller in src/mcpworks_api/services/mcp_server.py
- [ ] T032 [P] [US4] Unit test: add_mcp_server with oauth2 config stores encrypted config, describe returns status in tests/unit/test_mcp_server_service.py

**Checkpoint**: Full CRUD lifecycle for OAuth MCP servers via existing MCP tools

---

## Phase 7: User Story 5 — Multiple OAuth Providers per Namespace (Priority: P2)

**Goal**: Multiple OAuth MCP servers coexist independently per namespace

**Independent Test**: Register google_workspace and slack, authorize google only, verify slack returns AUTH_REQUIRED while google works

### Implementation for User Story 5

- [ ] T033 [US5] Verify all Redis keys are scoped by `{namespace_id}:{server_name}` — no cross-server state leakage in src/mcpworks_api/services/mcp_oauth.py
- [ ] T034 [US5] Verify proxy correctly routes to per-server OAuth tokens — test with two oauth2 servers where one is authorized and one is not in src/mcpworks_api/core/mcp_proxy.py
- [ ] T035 [P] [US5] Integration test: register two OAuth servers, authorize one, verify independent token lifecycle in tests/unit/test_mcp_oauth_multi.py

**Checkpoint**: Namespace with N OAuth servers, each with independent auth state

---

## Phase 8: Authorization Code Fallback (Cross-Cutting)

**Purpose**: Support providers that don't implement RFC 8628 device flow

- [ ] T036 Implement `initiate_auth_code_flow(server, db) -> dict` — generate state token (Redis, 600s TTL), build auth_url with client_id, redirect_uri, scope, state, return AUTH_REQUIRED response with `flow: "authorization_code"` in src/mcpworks_api/services/mcp_oauth.py
- [ ] T037 Implement `exchange_auth_code(server, code, state, db)` — validate state from Redis, POST to token_endpoint with `grant_type=authorization_code`, encrypt + store tokens in src/mcpworks_api/services/mcp_oauth.py
- [ ] T038 Create callback endpoint `GET /v1/oauth/mcp-callback` — parse state, validate CSRF, call `exchange_auth_code()`, return HTML success page with informed consent disclosure in src/mcpworks_api/api/v1/mcp_oauth.py
- [ ] T039 Register callback router in src/mcpworks_api/main.py
- [ ] T040 Update proxy integration: if `oauth_config.flow == "authorization_code"` and no tokens, call `initiate_auth_code_flow()` instead of device flow in src/mcpworks_api/core/mcp_proxy.py
- [ ] T041 [P] Unit test: auth code exchange, state validation, callback rendering in tests/unit/test_mcp_oauth_authcode.py

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Observability, documentation, security hardening

- [ ] T042 [P] Add Prometheus metrics: `mcpworks_oauth_token_refreshes_total` [namespace, server, status], `mcpworks_oauth_device_flows_total` [namespace, server, status], `mcpworks_oauth_auth_required_total` [namespace, server, flow] in src/mcpworks_api/middleware/observability.py
- [ ] T043 [P] Instrument all OAuth operations with Prometheus counters in src/mcpworks_api/services/mcp_oauth.py
- [ ] T044 [P] Add structlog events for OAuth lifecycle: device_flow_initiated, token_refreshed, token_refresh_failed, auth_code_exchanged in src/mcpworks_api/services/mcp_oauth.py
- [ ] T045 [P] Add OAuth configuration section to docs/SELF-HOSTING.md — provider setup, device flow vs auth code, scopes reference
- [ ] T046 [P] Add OAuth metrics to Prometheus metrics table in docs/SELF-HOSTING.md
- [ ] T047 Security review: verify no tokens in logs (structlog scrubbing), no client_secret in describe output, encrypted storage for all secrets
- [ ] T048 Run `ruff check` + `ruff format` + `pytest tests/unit/ -q` — full quality gate
- [ ] T049 Run quickstart.md validation — manually test device flow and auth code scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — device flow initiation + polling
- **US2 (Phase 4)**: Depends on Phase 2 — can run parallel to US1
- **US3 (Phase 5)**: Depends on US1 (needs AUTH_REQUIRED response format)
- **US4 (Phase 6)**: Depends on Phase 2 — can run parallel to US1/US2
- **US5 (Phase 7)**: Depends on US1 + US2 (needs working single-server flow)
- **Auth Code Fallback (Phase 8)**: Depends on Phase 2 — can run parallel to US1-US5
- **Polish (Phase 9)**: Depends on all above

### User Story Dependencies

```
Phase 1 → Phase 2 (blocks all)
                ├── US1 (device flow) ──┐
                ├── US2 (refresh) ──────┤── US5 (multi-provider)
                ├── US3 (HITL UX) ◄─ US1│
                ├── US4 (MCP tools) ────┘
                └── Auth Code (fallback) ── independent
                                    ↓
                              Phase 9 (polish)
```

### Parallel Opportunities

- US1 + US2 + US4 + Auth Code Fallback can all proceed in parallel after Phase 2
- All test tasks marked [P] can run in parallel within their phase
- T042-T046 (polish) are all independent and parallelizable

---

## Implementation Strategy

### MVP First (US1 + US2 Only)

1. Complete Phase 1: Setup (migration, model)
2. Complete Phase 2: Foundational (OAuth service core)
3. Complete Phase 3: US1 — Device flow works end-to-end
4. Complete Phase 4: US2 — Token refresh automated
5. **STOP and VALIDATE**: Test with real Google OAuth device flow
6. Deploy — OAuth-protected MCP servers are usable

### Incremental Delivery

1. Setup + Foundational → Service exists
2. US1 (device flow) → Users can authorize for the first time
3. US2 (refresh) → Tokens stay valid without re-auth
4. US3 (HITL UX) → AI agents present auth naturally
5. US4 (MCP tools) → Self-service configuration
6. US5 (multi-provider) → Multiple OAuth servers per namespace
7. Auth Code Fallback → Slack, Linear, and other non-device-flow providers
8. Polish → Metrics, docs, security review

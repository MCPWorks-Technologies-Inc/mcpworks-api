# Tasks: Namespace Telemetry Webhook

**Input**: Design documents from `/specs/023-telemetry-webhook/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — spec FR-011 and SC-006 explicitly require unit tests.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

---

## Phase 1: Setup

**Purpose**: Database migration and model changes

- [x] T001 Add telemetry webhook columns (`telemetry_webhook_url`, `telemetry_webhook_secret_encrypted`, `telemetry_webhook_secret_dek`, `telemetry_config` JSONB) to Namespace model in src/mcpworks_api/models/namespace.py
- [x] T002 Create Alembic migration for telemetry webhook columns in alembic/versions/20260408_000002_add_telemetry_webhook_columns.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core telemetry service that all stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Create telemetry service with `emit_telemetry_event()` function — builds JSON payload from execution metadata, sends async HTTP POST via httpx, fire-and-forget via `asyncio.create_task()` in src/mcpworks_api/services/telemetry.py
- [x] T004 Implement `sign_payload()` function — HMAC-SHA256 of raw JSON bytes, returns `sha256=<hex>` string in src/mcpworks_api/services/telemetry.py
- [x] T005 Implement `validate_webhook_url()` function — HTTPS required, HTTP allowed only for localhost/127.0.0.1, reject private IPs (10.x, 172.16-31.x, 192.168.x) in src/mcpworks_api/services/telemetry.py

**Checkpoint**: Telemetry service exists with delivery, signing, and URL validation

---

## Phase 3: User Story 1 — Webhook Delivery on Every Execution (Priority: P1)

**Goal**: Every function execution sends metadata to the configured webhook endpoint

**Independent Test**: Configure a webhook URL, execute a function, verify the endpoint receives the POST

### Implementation for User Story 1

- [x] T006 [US1] Wire `emit_telemetry_event()` into tools-mode execution path (`dispatch_tool`) in src/mcpworks_api/mcp/run_handler.py — call after `_persist_execution_record`, pass execution metadata (function name, execution_id, execution_time_ms, success, backend, version, timestamp)
- [x] T007 [US1] Wire `emit_telemetry_event()` into code-mode execution path (`_execute_code_mode`) in src/mcpworks_api/mcp/run_handler.py — call after analytics recording, pass code-mode execution metadata
- [x] T008 [US1] Load webhook config (URL + decrypted secret) from namespace in `emit_telemetry_event()` — skip entirely if `telemetry_webhook_url` is NULL (zero overhead) in src/mcpworks_api/services/telemetry.py

**Checkpoint**: Functions with a webhook configured send metadata to the endpoint; functions without webhook have zero overhead

---

## Phase 4: User Story 2 — HMAC Signature Verification (Priority: P1)

**Goal**: Webhook payloads are signed with HMAC-SHA256 when a secret is configured

**Independent Test**: Configure URL + secret, trigger execution, verify `X-MCPWorks-Signature` header matches HMAC of payload body

### Implementation for User Story 2

- [x] T009 [US2] Add `X-MCPWorks-Signature` header to webhook HTTP POST when secret is configured — compute `sha256=<hex>` from raw JSON bytes using the decrypted secret in src/mcpworks_api/services/telemetry.py
- [x] T010 [US2] Skip signature header when no secret is configured in src/mcpworks_api/services/telemetry.py

**Checkpoint**: Signed payloads are verifiable; unsigned payloads have no signature header

---

## Phase 5: User Story 3 — Configuration via MCP and REST API (Priority: P2)

**Goal**: Namespace owners can set, update, and remove webhook configuration

**Independent Test**: Set webhook URL + secret via REST/MCP, verify config persists, remove and verify webhooks stop

### Implementation for User Story 3

- [x] T011 [US3] Add `configure_telemetry_webhook` MCP tool to create handler — accepts url, secret (optional), batch_enabled, batch_interval_seconds; validates URL; encrypts secret via `encrypt_value()` in src/mcpworks_api/mcp/create_handler.py
- [x] T012 [US3] Add `configure_telemetry_webhook` tool definition to tool registry in src/mcpworks_api/mcp/tool_registry.py
- [x] T013 [US3] Add REST endpoints PUT/GET/DELETE `/v1/namespaces/{namespace}/telemetry-webhook` in src/mcpworks_api/api/v1/namespaces.py — GET returns url + has_secret (never the secret itself) + batch config; PUT validates and stores; DELETE clears all webhook columns

**Checkpoint**: Webhook can be configured, inspected, and removed via both MCP and REST

---

## Phase 6: User Story 4 — Event Batching (Priority: P3)

**Goal**: High-volume namespaces can buffer events and deliver in batches

**Independent Test**: Enable batching, trigger rapid executions, verify batched delivery at flush interval

### Implementation for User Story 4

- [x] T014 [US4] Implement `buffer_telemetry_event()` — LPUSH event JSON to Redis list keyed by namespace ID in src/mcpworks_api/services/telemetry.py
- [x] T015 [US4] Implement `flush_telemetry_batches()` — periodic task that LRANGE+LTRIM each namespace's buffer, delivers array payload to webhook in src/mcpworks_api/services/telemetry.py
- [x] T016 [US4] Register batch flush as periodic background task in src/mcpworks_api/main.py lifespan
- [x] T017 [US4] Update `emit_telemetry_event()` to check `telemetry_config.batch_enabled` — if true, buffer to Redis; if false or Redis unavailable, deliver individually in src/mcpworks_api/services/telemetry.py

**Checkpoint**: Batched events delivered at configured interval; falls back to individual delivery when Redis unavailable

---

## Phase 7: User Story 5 — Unit Tests (Priority: P3)

**Goal**: Comprehensive test coverage for telemetry service

**Independent Test**: `pytest tests/unit/test_telemetry.py -v` passes

### Implementation for User Story 5

- [x] T018 [P] [US5] Write unit tests for `emit_telemetry_event()` — mock httpx, verify POST with correct payload, verify fire-and-forget error handling (endpoint down), verify skip when no URL configured in tests/unit/test_telemetry.py
- [x] T019 [P] [US5] Write unit tests for `sign_payload()` — verify HMAC-SHA256 output matches known test vectors, verify no signature when secret is None in tests/unit/test_telemetry.py
- [x] T020 [P] [US5] Write unit tests for `validate_webhook_url()` — test HTTPS accepted, HTTP rejected (except localhost), private IPs rejected, malformed URLs rejected in tests/unit/test_telemetry.py
- [x] T021 [P] [US5] Write unit tests for batching — mock Redis, verify buffer/flush cycle, verify fallback to individual delivery when Redis unavailable in tests/unit/test_telemetry.py
- [x] T022 [US5] Run full test suite `pytest tests/unit/ -q` and verify no regressions

**Checkpoint**: All telemetry tests pass, no regressions

---

## Phase 8: Polish & Cross-Cutting Concerns

- [x] T023 Run `ruff format` and `ruff check --fix` on all modified files
- [x] T024 Run full unit test suite `pytest tests/unit/ -q` — all tests pass
- [ ] T025 Commit all changes and push branch

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all stories
- **US1 (Phase 3)**: Depends on Foundational — wires delivery into execution paths
- **US2 (Phase 4)**: Depends on US1 — signing is applied during delivery
- **US3 (Phase 5)**: Depends on Foundational — config endpoints use model columns
- **US4 (Phase 6)**: Depends on US1 + US3 — batching wraps the delivery path + reads config
- **US5 (Phase 7)**: Depends on all implementation stories
- **Polish (Phase 8)**: Depends on all phases

### User Story Dependencies

- **US1 (Delivery)**: Foundational only
- **US2 (Signing)**: US1 (signing happens during delivery)
- **US3 (Configuration)**: Foundational only — can start in parallel with US1
- **US4 (Batching)**: US1 + US3 (batching wraps delivery + reads config)
- **US5 (Tests)**: All implementation complete

### Parallel Opportunities

- T001 and T002 in parallel (model vs migration, different files)
- T003, T004, T005 in parallel (different functions in same new file — can be written together)
- US1 and US3 can start in parallel after Foundational (different files)
- T018, T019, T020, T021 all parallel (test functions)

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Phase 1: Setup (migration + model)
2. Phase 2: Foundational (telemetry service)
3. Phase 3: US1 (wire delivery into execution paths)
4. Phase 4: US2 (HMAC signing)
5. **STOP and VALIDATE**: Webhook fires on every execution with signature

### Incremental Delivery

1. Setup + Foundational → Service exists
2. US1 + US2 → Webhook delivery with signing → Core value
3. US3 → Configuration endpoints → Users can self-serve
4. US4 → Batching → Enterprise high-volume support
5. US5 → Tests → Quality gate

---

## Notes

- [P] tasks = different files, no dependencies
- Fire-and-forget: telemetry failures must NEVER crash function execution
- Never include user data (input/output/errors) in webhook payload — metadata only
- Secret encryption uses existing `core/encryption.py` envelope encryption (same as MCP server credentials)
- URL validation prevents SSRF: reject private IPs except localhost

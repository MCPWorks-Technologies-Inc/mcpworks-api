# Tasks: MCP Server Cards (.well-known Discovery)

**Input**: Design documents from `/specs/028-mcp-server-cards/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/rest-api.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Database migration and shared schema/service foundation

- [x] T001 Alembic migration to add `discoverable` boolean column (default false) to `namespaces` table in alembic/versions/20260415_000001_add_namespace_discoverable.py
- [x] T002 [P] Add `discoverable` mapped column to Namespace model in src/mcpworks_api/models/namespace.py
- [x] T003 [P] Create Pydantic response schemas (NamespaceServerCard, PlatformServerCard, ToolSummary) in src/mcpworks_api/schemas/discovery.py

---

## Phase 2: Foundational

**Purpose**: Discovery service with server card generation logic — MUST complete before endpoint tasks

- [x] T004 Create DiscoveryService with `get_namespace_card(namespace_name)` and `get_platform_card()` methods in src/mcpworks_api/services/discovery.py
- [x] T005 [P] Unit tests for DiscoveryService server card generation (namespace card with mixed public/private functions, empty namespace, platform card with discoverable filter) in tests/unit/test_discovery.py

**Checkpoint**: Service layer ready — endpoint implementation can begin

---

## Phase 3: User Story 1 — Per-Namespace Server Card (Priority: P1) MVP

**Goal**: Any MCP client can GET `/.well-known/mcp.json` on a namespace's `.create` subdomain and receive a JSON server card with tools, endpoints, and metadata.

**Independent Test**: `curl https://busybox.create.mcpworks.io/.well-known/mcp.json` returns valid JSON with namespace name, tools, and connection endpoints.

### Implementation for User Story 1

- [x] T006 [US1] Create discovery router with namespace server card handler in src/mcpworks_api/api/v1/discovery.py — handler reads Host header, extracts namespace name, calls DiscoveryService, returns JSON with Cache-Control header
- [x] T007 [US1] Mount `/.well-known/mcp.json` route on the main FastAPI app in src/mcpworks_api/main.py — route must bypass subdomain middleware (already skips .well-known paths)
- [x] T008 [US1] Handle 404 for non-existent namespaces and 503 for database errors in src/mcpworks_api/api/v1/discovery.py
- [x] T009 [US1] Add CORS header (`Access-Control-Allow-Origin: *`) to server card responses in src/mcpworks_api/api/v1/discovery.py

**Checkpoint**: Per-namespace discovery fully functional and testable independently

---

## Phase 4: User Story 2 — Platform-Level Discovery (Priority: P2)

**Goal**: A crawler can GET `/.well-known/mcp.json` on `api.mcpworks.io` and receive a list of all discoverable namespaces with links to their individual server cards.

**Independent Test**: `curl https://api.mcpworks.io/.well-known/mcp.json` returns JSON listing discoverable namespaces.

### Implementation for User Story 2

- [x] T010 [US2] Add platform card handler to the discovery router — dispatches based on Host header (api.mcpworks.io → platform card, {ns}.create → namespace card) in src/mcpworks_api/api/v1/discovery.py
- [x] T011 [US2] Add `discoverable` to MCP create handler so namespace owners can toggle it via `configure_namespace` tool in src/mcpworks_api/mcp/create_handler.py
- [x] T012 [US2] Register `discoverable` parameter in the configure_namespace tool definition in src/mcpworks_api/mcp/tool_registry.py

**Checkpoint**: Platform discovery works alongside per-namespace cards

---

## Phase 5: User Story 3 — Cache-Friendly Responses (Priority: P3)

**Goal**: Server card responses include Cache-Control headers so crawlers can cache efficiently.

**Independent Test**: Response headers include `Cache-Control: public, max-age=300`.

### Implementation for User Story 3

- [x] T013 [US3] Ensure all server card responses set `Cache-Control: public, max-age=300` header in src/mcpworks_api/api/v1/discovery.py

**Checkpoint**: All user stories complete — cache headers verified

---

## Phase 6: Polish & Cross-Cutting

**Purpose**: Validation and quality gates

- [x] T014 Run ruff format and ruff check on all modified files
- [x] T015 Run full unit test suite (`pytest tests/unit/ -q`) and verify no regressions

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T002 and T003 can run in parallel
- **Foundational (Phase 2)**: Depends on T002 (model) and T003 (schemas) — T004 and T005 can run in parallel
- **US1 (Phase 3)**: Depends on T004 (service) — T006→T007→T008→T009 sequential
- **US2 (Phase 4)**: Depends on T004 (service) and T002 (model) — can start after Phase 2; T011 and T012 parallel
- **US3 (Phase 5)**: Depends on T006 (router exists) — minimal, mostly verification
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Independent after Foundational — no dependencies on other stories
- **US2 (P2)**: Independent after Foundational — adds to the same router file but no functional dependency on US1
- **US3 (P3)**: Depends on the router existing (T006) — can be folded into US1 implementation

### Parallel Opportunities

- T002 and T003 can run in parallel (different files)
- T004 and T005 can run in parallel (service + tests)
- T011 and T012 can run in parallel (different files)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Migration + model + schemas
2. Complete Phase 2: Service layer
3. Complete Phase 3: Mount endpoint, test with curl
4. **STOP and VALIDATE**: `curl -H "Host: busybox.create.mcpworks.io" https://api.mcpworks.io/.well-known/mcp.json`
5. Deploy if ready — per-namespace discovery is live

### Incremental Delivery

1. Setup + Foundational → Service ready
2. Add US1 → Per-namespace cards live (MVP)
3. Add US2 → Platform listing live
4. Add US3 → Cache headers (likely already done in US1)
5. Each story adds value without breaking previous

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- US3 (cache headers) is trivial and will likely be implemented as part of US1
- Total tasks: 15
- US1: 4 tasks, US2: 3 tasks, US3: 1 task, Setup: 3, Foundation: 2, Polish: 2

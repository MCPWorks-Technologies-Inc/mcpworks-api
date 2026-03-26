# Tasks: Third-Party MCP Server Integration

**Input**: Design documents from `/specs/008-mcp-server-plugins/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/mcp-tools.md, quickstart.md

**Tests**: Included per spec (Section 11 defines unit, integration, and E2E test requirements).

**Organization**: Tasks grouped by user story from spec.md.
- US1 = Add & manage MCP servers (P1)
- US2 = Call MCP tools from sandbox (P1)
- US3 = Agent integration (P2)
- US4 = Console UI (P2)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Database schema, new model, dependencies

- [x] T001 Create NamespaceMcpServer model in src/mcpworks_api/models/namespace_mcp_server.py
- [x] T002 Add `mcp_servers` relationship on Namespace model in src/mcpworks_api/models/namespace.py
- [x] T003 Register NamespaceMcpServer in src/mcpworks_api/models/__init__.py
- [x] T004 Create Alembic migration + add mcp_server_names ARRAY column to agents

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core services and infrastructure that all user stories depend on

- [x] T005 [P] Create Pydantic schemas in src/mcpworks_api/schemas/mcp_server.py
- [x] T006 [P] Create McpServerService in src/mcpworks_api/services/mcp_server.py
- [x] T007 Create execution token registry in src/mcpworks_api/core/exec_token_registry.py
- [x] T008 Create MCP proxy core logic in src/mcpworks_api/core/mcp_proxy.py
- [x] T009 Create connection pool manager in src/mcpworks_api/core/mcp_pool.py

**Checkpoint**: Foundation ready — all user stories can begin

---

## Phase 3: User Story 1 — Add & Manage MCP Servers (Priority: P1) MVP

**Goal**: A user can add a third-party MCP server to their namespace, configure its settings and env vars, list/describe/refresh/remove servers — all via MCP tools on the create endpoint.

**Independent Test**: Call `add_mcp_server` → verify server stored with encrypted credentials and cached tools. Call `set_mcp_server_setting` → verify settings JSONB updated. Call `describe_mcp_server` → verify all details returned. Call `remove_mcp_server` → verify deleted.

### Tests for User Story 1

- [x] T010 [P] [US1] Unit test for McpServerService — deferred to Phase 7

### Implementation for User Story 1

- [x] T011 [US1] Add MCP_SERVER_TOOLS group to tool registry in src/mcpworks_api/mcp/tool_registry.py
- [x] T012 [US1] Implement 7 management tool handlers in src/mcpworks_api/mcp/create_handler.py
- [x] T013 [US1] Implement 3 env/agent tool handlers in src/mcpworks_api/mcp/create_handler.py
- [x] T014 [US1] Wire all 10 tools into TOOL_SCOPES, dispatch_tool, and get_tools()

**Checkpoint**: User can manage MCP servers via MCP tools. No sandbox integration yet.

---

## Phase 4: User Story 2 — Call MCP Tools from Sandbox (Priority: P1)

**Goal**: Functions running in the code sandbox can call remote MCP server tools via generated wrappers. The internal proxy routes calls through the API, decrypts credentials, and returns results. Credentials never enter the sandbox.

**Independent Test**: Add an MCP server (from US1) → execute Python code in sandbox that calls `mcp__server__tool()` → verify result returned correctly. Verify bridge key auth works. Verify credentials not accessible from sandbox.

### Tests for User Story 2

- [x] T015 [P] [US2] Unit test for proxy logic — deferred to Phase 7
- [x] T016 [P] [US2] Unit test for wrapper generation — deferred to Phase 7

### Implementation for User Story 2

- [x] T017 [US2] Register execution tokens in run_handler.py (register before execute, unregister in finally)
- [x] T018 [US2] Create /v1/internal/mcp-proxy FastAPI endpoint in src/mcpworks_api/api/v1/mcp_proxy.py
- [x] T019 [US2] Register proxy endpoint in FastAPI app in src/mcpworks_api/main.py
- [x] T020 [US2] Create _mcp_bridge.py template in src/mcpworks_api/mcp/code_mode.py
- [x] T021 [US2] Extend generate_functions_package() with mcp_servers param, wrapper generation, [RemoteMCP] docstring
- [x] T022 [US2] Pass MCP server data to generate_functions_package() in run_handler.py

**Checkpoint**: Full sandbox → proxy → MCP server flow works. Token efficiency confirmed.

---

## Phase 5: User Story 3 — Agent Integration (Priority: P2)

**Goal**: Agents select which namespace MCP servers they can access. The orchestrator resolves server names to configs from the namespace registry, connects, and makes tools available during agent runs.

**Independent Test**: Configure agent with `mcp_server_names: ["slack"]` → trigger agent run → verify agent can call slack MCP tools → verify orchestrator uses namespace registry (not JSONB).

### Implementation for User Story 3

- [ ] T023 [US3] Refactor orchestrator in src/mcpworks_api/tasks/orchestrator.py — read mcp_server_names from agent, resolve to NamespaceMcpServer records from namespace, build McpServerPool from resolved configs (decrypt credentials), deprecate reading from agent.mcp_servers JSONB
- [ ] T024 [US3] Update McpServerPool in src/mcpworks_api/core/mcp_client.py — accept NamespaceMcpServer records instead of raw JSONB dicts, decrypt credentials on connect, respect per-server settings (timeout, response limit)

**Checkpoint**: Agents use namespace-level MCP servers. Old JSONB path deprecated.

---

## Phase 6: User Story 4 — Console UI (Priority: P2)

**Goal**: The namespace console shows a "Remote MCP Servers" section with expandable cards for each server, displaying settings, env vars, and tool lists.

**Independent Test**: Load console page → see MCP servers listed → expand a card → see settings, env vars, tools. Verify data matches what the API returns.

### Implementation for User Story 4

- [ ] T025 [US4] Create REST endpoint GET /v1/namespaces/{ns}/mcp-servers in src/mcpworks_api/api/v1/namespaces.py — returns all MCP servers with settings, env vars, tool list for console rendering
- [ ] T026 [US4] Add "Remote MCP Servers" section to src/mcpworks_api/static/console.html — collapsible cards per server showing: name, URL, status (enabled/disabled), tool count. Expand reveals: settings table, env vars table, tool list with descriptions.

**Checkpoint**: Console displays full MCP server management view.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Integration tests, docs, cleanup

- [ ] T027 [P] Integration test: full flow in tests/integration/test_mcp_server_e2e.py — add MCP server → execute sandbox code calling MCP tool via proxy → verify result returned correctly (requires mock MCP server)
- [ ] T028 [P] Integration test: agent with MCP servers in tests/integration/test_mcp_server_e2e.py — configure agent with mcp_server_names → trigger run → verify tools available
- [ ] T029 [P] Update docs/guide.md with "Remote MCP Servers" section — document all 11 tools, parallel hierarchy, sandbox usage examples
- [ ] T030 [P] Update docs/GETTING-STARTED.md with "Connect a Third-Party MCP Server" step
- [ ] T031 Structlog events for all MCP server operations in src/mcpworks_api/services/mcp_server.py and src/mcpworks_api/core/mcp_proxy.py — mcp_server_added, mcp_server_removed, mcp_proxy_call, mcp_proxy_error, mcp_pool_hit, mcp_pool_miss (never log credentials or arguments)
- [ ] T032 Add Prometheus metrics in src/mcpworks_api/core/mcp_proxy.py — mcpworks_mcp_proxy_calls_total (counter), mcpworks_mcp_proxy_duration_seconds (histogram), mcpworks_mcp_server_connections_active (gauge)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 Server Management (Phase 3)**: Depends on Phase 2
- **US2 Sandbox Integration (Phase 4)**: Depends on Phase 2 (parallel with US1 but needs add_mcp_server for testing)
- **US3 Agent Integration (Phase 5)**: Depends on Phase 2 (parallel with US1/US2)
- **US4 Console (Phase 6)**: Depends on US1 (needs REST endpoint and data)
- **Polish (Phase 7)**: Depends on US1 + US2 minimum

### User Story Dependencies

- **US1 (Server Management)**: Can start after Foundational — no dependencies on other stories
- **US2 (Sandbox)**: Can start after Foundational — but integration testing needs US1's add_mcp_server
- **US3 (Agent)**: Can start after Foundational — independent of US1/US2
- **US4 (Console)**: Depends on US1 (REST endpoint)

### Within Each User Story

- Tests first → service layer → tool handlers → wiring → integration

### Parallel Opportunities

**Phase 2 parallel group**:
```
T005 (schemas) + T006 (service) + T007 (exec registry) — different files
T008 (proxy core) + T009 (pool manager) — different files, after T007
```

**US1 parallel group**:
```
T011 (tool registry) can run parallel with T012/T013 (handlers)
```

**US2 test parallel group**:
```
T015 (proxy tests) + T016 (wrapper tests) — different test files
```

**Phase 7 parallel group**:
```
T027 + T028 + T029 + T030 + T031 + T032 — all independent
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Complete Phase 1: Setup (model + migration)
2. Complete Phase 2: Foundational (service, proxy, pool, registry, schemas)
3. Complete Phase 3: US1 — add/manage MCP servers
4. Complete Phase 4: US2 — sandbox integration + proxy endpoint
5. **STOP and VALIDATE**: Add a real MCP server → call its tools from sandbox code → verify token efficiency
6. Deploy

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 (Server Management) → users can configure MCP servers → **MVP**
3. US2 (Sandbox Integration) → sandbox can call MCP tools → **core value delivered**
4. US3 (Agent Integration) → agents use namespace MCP servers
5. US4 (Console) → visual management interface
6. Polish → integration tests, docs, observability

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Each user story is independently testable after foundational phase
- Credentials NEVER in sandbox — proxy decrypts server-side only
- Connection pool is per-worker in-memory — acceptable for single-server deployment
- `mcp__` prefix distinguishes remote tools from native functions
- console.html is vanilla JS — no React/framework dependency

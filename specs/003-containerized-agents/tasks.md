# Tasks: MCPWorks Containerized Agents

**Input**: Design documents from `/specs/003-containerized-agents/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add new dependencies and create foundational modules needed by all agent features

- [x] T001 Add `docker>=7.0.0`, `apscheduler>=3.10.0`, `discord.py>=2.3.0` to `pyproject.toml` dependencies
- [x] T002 [P] Create envelope encryption module with AES-256-GCM (KEK/DEK pattern) in `src/mcpworks_api/core/encryption.py` — functions: `generate_dek()`, `encrypt_dek()`, `decrypt_dek()`, `encrypt_value()`, `decrypt_value()`; KEK loaded from `ENCRYPTION_KEK_B64` env var
- [x] T003 [P] Add `ENCRYPTION_KEK_B64` to `src/mcpworks_api/config.py` Settings model and document in `.env.example`
- [x] T004 [P] Extend `SubscriptionTier` enum in `src/mcpworks_api/models/subscription.py` with `BUILDER_AGENT = "builder-agent"`, `PRO_AGENT = "pro-agent"`, `ENTERPRISE_AGENT = "enterprise-agent"`
- [x] T005 [P] Extend `UserTier` enum in `src/mcpworks_api/models/user.py` with matching agent tiers
- [x] T006 Add agent tier → functions tier mapping and agent tier limits (slots, RAM, CPU, min schedule, state size, run retention, webhook size) as a `AGENT_TIER_CONFIG` dict in `src/mcpworks_api/models/subscription.py` (depends on T004 — same file)
- [x] T007 Update `TIER_LIMITS` in `src/mcpworks_api/middleware/billing.py` to map agent tiers to their functions tier execution limits (builder-agent → 25000, pro-agent → 250000, enterprise-agent → 1000000)

**Checkpoint**: Dependencies installed, encryption module ready, tier enums extended

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Agent data model, schemas, and core service — MUST be complete before any user story

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T008 Create Agent SQLAlchemy model in `src/mcpworks_api/models/agent.py` — fields: id, account_id, namespace_id, name, display_name, container_id, status, ai_engine, ai_model, ai_api_key_encrypted, ai_api_key_dek_encrypted, memory_limit_mb, cpu_limit, system_prompt, enabled, cloned_from_id, created_at, updated_at; unique constraint on (account_id, name)
- [x] T009 [P] Create AgentRun SQLAlchemy model in `src/mcpworks_api/models/agent.py` — fields: id, agent_id (FK CASCADE), trigger_type, trigger_detail, function_name, status, started_at, completed_at, duration_ms, result_summary, error, created_at; indexes on (agent_id, created_at DESC) and (created_at)
- [x] T010 Register Agent and AgentRun models in `src/mcpworks_api/models/__init__.py`
- [x] T011 [P] Add `locked` (BOOLEAN DEFAULT false), `locked_by` (UUID FK users.id), `locked_at` (TIMESTAMPTZ) columns to Function model in `src/mcpworks_api/models/function.py`
- [x] T012 Create Alembic migration for Phase A: agents table, agent_runs table, SubscriptionTier enum extension, locked columns on functions table — in `alembic/versions/YYYYMMDD_000001_add_agents_phase_a.py`
- [x] T013 [P] Create Pydantic schemas in `src/mcpworks_api/schemas/agent.py` — CreateAgentRequest, AgentResponse, AgentListResponse, AgentSlotsResponse, StartStopResponse, DestroyResponse
- [x] T014 Create `AgentService` class in `src/mcpworks_api/services/agent_service.py` with methods: `create_agent()`, `get_agent()`, `list_agents()`, `start_agent()`, `stop_agent()`, `destroy_agent()`, `get_agent_slots()` — use Docker SDK `docker.from_env()` for container lifecycle; create `mcpworks-agents` bridge network if not exists; rollback DB insert if container creation fails; set agent status to 'error' with capacity info on resource exhaustion
- [x] T015 [P] Add `functions_tier` property to SubscriptionTier in `src/mcpworks_api/models/subscription.py` that maps agent tiers to their base functions tier

**Checkpoint**: Foundation ready — agent model exists, service can manage containers, schemas validate requests

---

## Phase 3: User Story 1 — Create and Manage an Agent (Priority: P1) MVP

**Goal**: Users on agent tiers can create, start, stop, and destroy agents via MCP and REST API

**Independent Test**: Create an agent via MCP, confirm container is running, stop/start/destroy it

### Implementation for User Story 1

- [x] T016 [US1] Create agent REST router in `src/mcpworks_api/api/v1/agents.py` — endpoints: `POST /api/v1/agents` (create), `GET /api/v1/agents` (list), `GET /api/v1/agents/{agent_id}` (detail), `POST /api/v1/agents/{agent_id}/start`, `POST /api/v1/agents/{agent_id}/stop`, `DELETE /api/v1/agents/{agent_id}` (destroy); validate tier is agent-enabled, check slot limits
- [x] T017 [US1] Register agent router in `src/mcpworks_api/api/v1/__init__.py`
- [x] T018 [P] [US1] Add 6 agent MCP tools to `src/mcpworks_api/mcp/create_handler.py` — `make_agent`, `list_agents`, `describe_agent`, `start_agent`, `stop_agent`, `destroy_agent`; add to `TOOL_SCOPES`; filter from `get_tools()` when user tier is not agent-enabled
- [x] T019 [US1] Add agent tier upgrade admin endpoint `POST /api/v1/admin/accounts/{account_id}/upgrade` in `src/mcpworks_api/api/v1/admin.py` — validate tier value, update user tier, create audit log; block downgrade if agents exist (FR-021)
- [x] T020 [US1] Update `docker-compose.prod.yml` to mount Docker socket (`/var/run/docker.sock`) into API container and add `mcpworks-agents` network

**Checkpoint**: Can create an agent via MCP, see its container running, stop/start/destroy it

---

## Phase 4: User Story 8 — Admin Fleet Management (Priority: P2)

**Goal**: Admins can view all agents, monitor health, force-restart/destroy, and upgrade tiers

**Independent Test**: Admin lists all agents, views fleet health, force-restarts an agent

### Implementation for User Story 8

- [x] T021 [US8] Add admin agent endpoints to `src/mcpworks_api/api/v1/admin.py` — `GET /admin/agents` (list all, paginated), `GET /admin/agents/{agent_id}` (detail with container stats), `POST /admin/agents/{agent_id}/restart` (force restart), `DELETE /admin/agents/{agent_id}` (force destroy)
- [x] T022 [US8] Add fleet health endpoint `GET /admin/agents/health` in `src/mcpworks_api/api/v1/admin.py` — query Docker for all agent containers, report total/running/stopped/error counts, memory/CPU usage, available capacity
- [x] T023 [US8] Add `get_container_stats()` and `force_restart_agent()` methods to `AgentService` in `src/mcpworks_api/services/agent_service.py`

**Checkpoint**: Admin can manage the agent fleet, monitor health, and intervene

---

## Phase 5: User Story 2 — Schedule Functions on an Agent (Priority: P2)

**Goal**: Agents can execute functions on cron schedules with configurable failure policies

**Independent Test**: Add a schedule, wait for scheduled time, confirm function executed and run recorded

### Implementation for User Story 2

- [x] T024 [US2] Add AgentSchedule SQLAlchemy model to `src/mcpworks_api/models/agent.py` — fields: id, agent_id (FK CASCADE), function_name, cron_expression, timezone, failure_policy (JSONB), enabled, consecutive_failures, last_run_at, next_run_at, created_at
- [x] T025 [US2] Create Alembic migration for Phase B: agent_schedules table only — in `alembic/versions/YYYYMMDD_000001_add_agents_phase_b.py`
- [x] T026 [P] [US2] Add schedule Pydantic schemas to `src/mcpworks_api/schemas/agent.py` — CreateScheduleRequest (with failure_policy validation), ScheduleResponse, ScheduleListResponse; validate cron expression and minimum interval per tier
- [x] T027 [US2] Add schedule methods to `AgentService` in `src/mcpworks_api/services/agent_service.py` — `add_schedule()` (validate cron, enforce min interval, validate failure_policy required), `remove_schedule()`, `list_schedules()`
- [x] T028 [US2] Add schedule REST endpoints to `src/mcpworks_api/api/v1/agents.py` — `POST /api/v1/agents/{agent_id}/schedules`, `GET /api/v1/agents/{agent_id}/schedules`, `DELETE /api/v1/agents/{agent_id}/schedules/{schedule_id}`
- [x] T029 [US2] Add MCP tools `add_schedule` and `remove_schedule` to `src/mcpworks_api/mcp/create_handler.py`
- [x] T030 [US2] Create agent runtime scheduler module in `agent-runtime/mcpworks_agent/scheduler.py` — load schedules from API at startup, configure APScheduler with CronTrigger, poll for schedule changes every 60 seconds, apply failure policy (continue/auto_disable/backoff), record AgentRun on completion
- [x] T031 [US2] Add runs listing endpoint `GET /api/v1/agents/{agent_id}/runs` to `src/mcpworks_api/api/v1/agents.py` with pagination

**Checkpoint**: Agent executes functions on schedule, failure policies enforced, runs recorded

---

## Phase 6: User Story 3 — Receive Webhooks on an Agent (Priority: P2)

**Goal**: External systems can trigger agent functions via `{name}.agent.mcpworks.io/webhook/{path}`

**Independent Test**: Register webhook, POST to URL, confirm handler executed and run recorded

### Implementation for User Story 3

- [x] T032 [US3] Add AgentWebhook SQLAlchemy model to `src/mcpworks_api/models/agent.py` — fields: id, agent_id (FK CASCADE), path, handler_function_name, secret_hash, enabled, created_at; unique constraint on (agent_id, path)
- [x] T033 [US3] Create Alembic migration for Phase B2: agent_webhooks table — in `alembic/versions/YYYYMMDD_000002_add_agent_webhooks.py`
- [x] T034 [P] [US3] Add webhook Pydantic schemas to `src/mcpworks_api/schemas/agent.py` — CreateWebhookRequest, WebhookResponse, WebhookListResponse
- [x] T035 [US3] Add webhook methods to `AgentService` in `src/mcpworks_api/services/agent_service.py` — `add_webhook()` (hash secret with Argon2id if provided), `remove_webhook()`, `list_webhooks()`, `resolve_webhook()` (lookup by agent name + path)
- [x] T036 [US3] Create webhook ingress endpoint in `src/mcpworks_api/api/v1/agents.py` — route: `POST /webhook/{path:path}` (matched via `*.agent.mcpworks.io` Host header); extract agent name from subdomain, resolve webhook, verify secret if configured, enforce tier-based payload size limit, forward to agent container, record AgentRun
- [x] T037 [US3] Add MCP tools `add_webhook` and `remove_webhook` to `src/mcpworks_api/mcp/create_handler.py`
- [x] T038 [US3] Update Caddy configuration to route `*.agent.mcpworks.io` traffic to API server — add to `Caddyfile` or `caddy/Caddyfile` with TLS via Cloudflare DNS challenge
- [x] T039 [US3] Create webhook listener in agent runtime `agent-runtime/mcpworks_agent/webhook_listener.py` — FastAPI app on internal port, receives forwarded webhooks from API, executes handler function via MCPWorks run API

**Checkpoint**: External webhook triggers function execution, runs recorded, secrets verified

---

## Phase 7: User Story 4 — Persist State Across Runs (Priority: P3)

**Goal**: Agent functions can store and retrieve encrypted key-value state between runs

**Independent Test**: Function writes state value, subsequent function reads it back

### Implementation for User Story 4

- [x] T040 [US4] Add AgentState SQLAlchemy model to `src/mcpworks_api/models/agent.py` — fields: id, agent_id (FK CASCADE), key, value_encrypted, value_dek_encrypted, size_bytes, updated_at; unique constraint on (agent_id, key)
- [x] T041 [US4] Create Alembic migration for Phase C: agent_state table — in `alembic/versions/YYYYMMDD_000001_add_agents_phase_c.py`
- [x] T042 [P] [US4] Add state Pydantic schemas to `src/mcpworks_api/schemas/agent.py` — SetStateRequest, StateResponse, StateKeyListResponse
- [x] T043 [US4] Add state methods to `AgentService` in `src/mcpworks_api/services/agent_service.py` — `set_state()` (encrypt value with agent DEK, check tier size limit, return 413 if exceeded), `get_state()` (decrypt), `delete_state()`, `list_state_keys()`
- [x] T044 [US4] Add state REST endpoints to `src/mcpworks_api/api/v1/agents.py` — `PUT /api/v1/agents/{agent_id}/state/{key}`, `GET /api/v1/agents/{agent_id}/state/{key}`, `DELETE /api/v1/agents/{agent_id}/state/{key}`, `GET /api/v1/agents/{agent_id}/state`; accept both JWT and agent API key auth
- [x] T045 [US4] Add MCP tools `set_agent_state` and `get_agent_state` to `src/mcpworks_api/mcp/create_handler.py`

**Checkpoint**: State persists between runs, encryption verified, size limits enforced

---

## Phase 8: User Story 5 — Lock Functions Against Modification (Priority: P3)

**Goal**: Admin can lock functions so agent API keys cannot modify them

**Independent Test**: Lock a function, attempt modify with agent key (fail), modify with admin key (succeed)

### Implementation for User Story 5

- [x] T046 [US5] Add lock check to function update and delete handlers — in the existing function modification endpoints, check `if function.locked and request scope != 'admin': raise 403` (model columns already added in T011, migration in T012)
- [x] T047 [US5] Add lock/unlock REST endpoints to `src/mcpworks_api/api/v1/agents.py` — `POST /api/v1/namespaces/{ns}/functions/{fn}/lock` (admin only), `DELETE /api/v1/namespaces/{ns}/functions/{fn}/lock` (admin only)
- [x] T048 [US5] Add MCP tools `lock_function` and `unlock_function` to `src/mcpworks_api/mcp/create_handler.py`

**Checkpoint**: Locked functions protected from non-admin modification, execution unaffected

---

## Phase 9: User Story 6 — Clone an Agent (Priority: P3)

**Goal**: Users can clone an existing agent to a new independent copy

**Independent Test**: Clone agent, verify new agent has all functions/state/schedules, modify clone without affecting original

### Implementation for User Story 6

- [x] T049 [US6] Add `clone_agent()` method to `AgentService` in `src/mcpworks_api/services/agent_service.py` — validate slot availability, create new agent + namespace, copy functions (all versions), copy state (re-encrypt with new DEK), copy schedules (disabled), copy channel configs, copy AI config, do NOT copy webhook secrets or container_id, start new container
- [x] T050 [US6] Add clone REST endpoint `POST /api/v1/agents/{agent_id}/clone` to `src/mcpworks_api/api/v1/agents.py` — accepts `new_name`, returns new agent with copy counts
- [x] T051 [US6] Add MCP tool `clone_agent` to `src/mcpworks_api/mcp/create_handler.py`

**Checkpoint**: Agent cloned with all data, clone is independent, schedules start disabled

---

## Phase 10: User Story 7 — Configure AI Engine and Communication Channels (Priority: P4)

**Goal**: Users can configure BYOAI and communication channels on agents

**Independent Test**: Configure AI + Discord, trigger via webhook, agent reasons and sends Discord message

### Implementation for User Story 7

- [x] T052 [US7] Add AgentChannel SQLAlchemy model to `src/mcpworks_api/models/agent.py` — fields: id, agent_id (FK CASCADE), channel_type, config_encrypted, config_dek_encrypted, enabled, created_at; unique constraint on (agent_id, channel_type)
- [x] T053 [US7] Create Alembic migration for Phase D: agent_channels table — in `alembic/versions/YYYYMMDD_000001_add_agents_phase_d.py`
- [x] T054 [P] [US7] Add AI and channel Pydantic schemas to `src/mcpworks_api/schemas/agent.py` — ConfigureAIRequest, AIResponse, CreateChannelRequest, ChannelResponse
- [x] T055 [US7] Add AI config methods to `AgentService` in `src/mcpworks_api/services/agent_service.py` — `configure_ai()` (encrypt API key with agent DEK), `remove_ai()`, `add_channel()` (encrypt config), `remove_channel()`
- [x] T056 [US7] Add AI and channel REST endpoints to `src/mcpworks_api/api/v1/agents.py` — `PUT /api/v1/agents/{agent_id}/ai`, `DELETE /api/v1/agents/{agent_id}/ai`, `POST /api/v1/agents/{agent_id}/channels`, `DELETE /api/v1/agents/{agent_id}/channels/{channel_id}`
- [x] T057 [US7] Add MCP tools `configure_agent_ai`, `add_channel`, `remove_channel` to `src/mcpworks_api/mcp/create_handler.py`
- [x] T058 [US7] Create AI engine module in `agent-runtime/mcpworks_agent/ai_engine.py` — initialize LLM client based on engine config, reasoning loop that receives trigger context and decides which functions to call
- [x] T059 [US7] Create Discord channel connector in `agent-runtime/mcpworks_agent/channels/discord.py` — connect to Discord via bot token, send messages to configured channel, handle bidirectional messaging

**Checkpoint**: Agent with AI can reason about triggers and send results via Discord

---

## Phase 11: Tests (Constitution Principle V — 80% coverage target)

**Purpose**: Unit tests for core business logic per Constitution requirement

- [x] T060 [P] Create encryption round-trip tests in `tests/unit/test_encryption.py` — test generate_dek, encrypt/decrypt_dek, encrypt/decrypt_value, verify KEK rotation path, verify invalid KEK rejection (target: 95% coverage of core/encryption.py)
- [x] T061 [P] Create agent service unit tests in `tests/unit/test_agent_service.py` — mock Docker SDK; test create_agent (success + rollback on Docker failure + resource exhaustion → error status), start/stop/destroy lifecycle, slot limit enforcement, tier validation (target: 80% coverage of services/agent_service.py)
- [x] T062 [P] Create agent schema validation tests in `tests/unit/test_agent_schemas.py` — test CreateAgentRequest name validation, CreateScheduleRequest failure_policy required, cron expression validation, tier-based min interval rejection
- [x] T063 [P] Create tier mapping tests in `tests/unit/test_agent_tier.py` — test functions_tier property for all 3 agent tiers, AGENT_TIER_CONFIG completeness, billing middleware TIER_LIMITS mapping

---

## Phase 12: Polish & Cross-Cutting Concerns

**Purpose**: Agent runtime image, run retention, observability, and hardening

- [x] T064 Create agent runtime Dockerfile in `agent-runtime/Dockerfile` — Python 3.11 slim base, install httpx, apscheduler, fastapi, uvicorn, anthropic, openai, discord.py; copy entrypoint and agent modules; run as non-root user, read-only filesystem, tmpfs for /tmp
- [x] T065 Create agent runtime entrypoint in `agent-runtime/entrypoint.py` — start FastAPI webhook listener, load schedules from API, connect channels, initialize AI engine if configured, enter event loop
- [x] T066 [P] Create `agent-runtime/requirements.txt` with pinned versions for all agent runtime dependencies
- [x] T067 [P] Create daily AgentRun retention purge task in `src/mcpworks_api/tasks/run_retention.py` — delete runs older than tier retention (7/30/90 days); register as APScheduler job in API server startup (`main.py` lifespan) running once daily at 03:00 UTC
- [x] T068 [P] Add agent tier price mappings to `src/mcpworks_api/services/stripe.py` — extend `TIER_PRICE_MAP` and `TIER_EXECUTIONS` with agent tier entries (placeholder price IDs until commercialization)
- [x] T069 Add structured logging for all agent operations in `AgentService` — use structlog with agent_id, account_id, operation context for create/start/stop/destroy/schedule/webhook events
- [x] T070 [P] Add agent container security hardening to `AgentService.create_agent()` — `--read-only` root filesystem, drop all capabilities except `NET_BIND_SERVICE`, `--security-opt no-new-privileges`, non-root user inside container
- [x] T071 Validate quickstart.md end-to-end — walk through all 8 steps from `specs/003-containerized-agents/quickstart.md` against running system

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational — MVP, must complete first
- **US8 (Phase 4)**: Depends on US1 (needs agents to exist to manage them)
- **US2 (Phase 5)**: Depends on US1 (needs running agent to add schedules)
- **US3 (Phase 6)**: Depends on US1 (needs running agent to register webhooks)
- **US4 (Phase 7)**: Depends on US1 (needs agent for state storage)
- **US5 (Phase 8)**: Depends on Phase 2 (model columns added there) + US1 (needs functions in agent namespace)
- **US6 (Phase 9)**: Depends on US1 + US4 (cloning copies state)
- **US7 (Phase 10)**: Depends on US1 (needs agent to configure AI/channels)
- **Tests (Phase 11)**: Can start after Phase 2; run incrementally as each story completes
- **Polish (Phase 12)**: Can start partially after US1; full completion after all stories

### User Story Dependencies

```
         ┌── US8 (Admin)
         │
US1 ─────┼── US2 (Schedules) ───┐
(P1)     │                      │
         ├── US3 (Webhooks) ────┤
         │                      │
         ├── US4 (State) ───────┼── US6 (Clone)
         │                      │
         ├── US5 (Locking) ─────┘
         │
         └── US7 (AI + Channels)
```

### Parallel Opportunities

After US1 completes, these can run in parallel:
- **Track A**: US2 (Schedules) + US3 (Webhooks) — different models, different endpoints
- **Track B**: US4 (State) + US5 (Locking) — different models, different endpoints
- **Track C**: US8 (Admin) — only touches admin.py
- **Track D**: Tests (Phase 11) — all 4 test files are independent [P]
- US6 (Clone) waits for US4; US7 waits for nothing but is lowest priority

### Within Each User Story

- Models before services
- Services before endpoints
- Endpoints before MCP tools
- Agent runtime modules can be parallel with API-side work

---

## Parallel Example: Phase 1 Setup

```
# These 4 tasks touch different files — run in parallel:
T002: core/encryption.py
T003: config.py
T004: models/subscription.py
T005: models/user.py

# Then sequentially (same file as T004):
T006: models/subscription.py (AGENT_TIER_CONFIG)
```

## Parallel Example: User Story 1

```
# After foundational phase, these touch different files:
T016: api/v1/agents.py (new file)
T018: mcp/create_handler.py
T019: api/v1/admin.py

# T016 and T018 are parallel (different files)
# T019 is parallel with both (different file)
# T017 depends on T016 (registering the router T016 creates)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T007)
2. Complete Phase 2: Foundational (T008-T015)
3. Complete Phase 3: US1 — Create and Manage Agent (T016-T020)
4. **STOP and VALIDATE**: Create agent via MCP, verify container runs, stop/start/destroy
5. This alone proves the core concept works

### Incremental Delivery (Recommended)

1. Setup + Foundational → Foundation ready
2. US1 (Agent Shell) → **MVP — deploy and validate**
3. US8 (Admin) → Fleet visibility for operations
4. US2 + US3 in parallel (Schedules + Webhooks) → Agents become autonomous
5. US4 + US5 in parallel (State + Locking) → Agents become stateful and safe
6. US6 (Cloning) → Rapid agent scaling
7. US7 (AI + Channels) → Full autonomy
8. Tests + Polish → Constitution compliance, hardening

### Task Count Summary

| Phase | Story | Tasks | Parallel |
|-------|-------|-------|----------|
| Setup | — | 7 | 4 |
| Foundational | — | 8 | 3 |
| US1 (P1) | Create/Manage | 5 | 1 |
| US8 (P2) | Admin Fleet | 3 | 0 |
| US2 (P2) | Schedules | 8 | 1 |
| US3 (P2) | Webhooks | 8 | 1 |
| US4 (P3) | State | 6 | 1 |
| US5 (P3) | Locking | 3 | 0 |
| US6 (P3) | Cloning | 3 | 0 |
| US7 (P4) | AI + Channels | 8 | 1 |
| Tests | — | 4 | 4 |
| Polish | — | 8 | 3 |
| **Total** | | **71** | **19** |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable after US1
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Agent runtime (`agent-runtime/`) is a separate Docker image build — can be developed in parallel with API-side work
- All encryption uses the `core/encryption.py` module (T002) — never raw cryptography calls elsewhere
- Function locking model columns (T011) are in Foundational phase alongside their migration (T012) — implementation logic is in US5

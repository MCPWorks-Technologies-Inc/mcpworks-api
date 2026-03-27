# Tasks: Agent Clusters

**Input**: Design documents from `/specs/012-agent-clusters/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: New module and name generator — no dependencies on existing code changes.

- [x] T001 [P] Create verb-animal name generator with ~50 verbs and ~50 animals, collision-retry logic, and uniqueness-within-cluster check in src/mcpworks_api/core/replica_names.py
- [x] T002 [P] Create unit tests for name generator (uniqueness, collision retry, pool size >= 2500) in tests/unit/test_replica_names.py

**Checkpoint**: Name generator ready. No existing code modified yet.

---

## Phase 2: Foundational (Data Model + Migration)

**Purpose**: Database schema changes that all user stories depend on. MUST complete before any story work.

- [x] T003 Add `AgentReplica` model (id, agent_id FK, replica_name, container_id, status, last_heartbeat, created_at) with indexes and unique constraint on (agent_id, replica_name) in src/mcpworks_api/models/agent.py
- [x] T004 Add `ScheduledJob` model (id, agent_id FK, schedule_id FK, replica_id FK nullable, fire_time, status, claimed_by FK nullable, claimed_at, completed_at, error, created_at) with partial index on pending status in src/mcpworks_api/models/agent.py
- [x] T005 Add `target_replicas` column (Integer, default 1) to `Agent` model and `mode` column (String, default 'single') to `AgentSchedule` model in src/mcpworks_api/models/agent.py
- [x] T006 Add `AgentReplicaResponse` schema and update `AgentResponse` to include `target_replicas` and `replicas` list in src/mcpworks_api/schemas/agent.py
- [x] T007 Create Alembic migration: add `agent_replicas` and `scheduled_jobs` tables, add columns to `agents` and `agent_schedules`, data-migrate existing agents with `container_id` into `agent_replicas` rows in alembic/versions/
- [x] T008 Add `Agent.replicas` relationship (one-to-many, cascade delete) and `AgentReplica.agent` back-reference in src/mcpworks_api/models/agent.py

**Checkpoint**: Foundation ready — all new tables exist, existing agents have replica rows, user story implementation can begin.

---

## Phase 3: User Story 1 — Scale an Agent to Multiple Replicas (Priority: P1) MVP

**Goal**: Operators can scale agents up/down. Each replica gets a verb-animal name and full tier resources. Tier slot limits enforced. LIFO scale-down.

**Independent Test**: Create an agent, scale to 3, verify 3 containers running with distinct names. Scale to 1, verify LIFO removal. Hit tier limit, verify rejection.

- [x] T009 [US1] Refactor `AgentService.create_agent()` to create an `AgentReplica` row (with generated verb-animal name) instead of storing `container_id` on the `Agent` row. Container name becomes `agent-{name}-{replica_name}`. Backward compatible — single replica created by default in src/mcpworks_api/services/agent_service.py
- [x] T010 [US1] Implement `AgentService.scale_agent(account_id, agent_name, target_replicas)` — creates/removes replicas to match target. Scale-up: generate names, create containers with full tier resources. Scale-down: LIFO order, graceful shutdown (wait for in-progress jobs). Enforce tier slot limits (count all replicas across all agents) in src/mcpworks_api/services/agent_service.py
- [x] T011 [US1] Update `AgentService.start_agent()` and `stop_agent()` to accept optional `replica_name` parameter — target single replica or entire cluster in src/mcpworks_api/services/agent_service.py
- [x] T012 [US1] Update `AgentService.destroy_agent()` to stop and remove all replica containers before deleting the agent row in src/mcpworks_api/services/agent_service.py
- [x] T013 [US1] Derive agent-level status from replica statuses (all running → "running", any error → "degraded", all stopped → "stopped") in `AgentService.get_agent()` or as a property on the `Agent` model in src/mcpworks_api/services/agent_service.py
- [x] T014 [US1] Update `describe_agent` response to include `target_replicas` and `replicas` list (name, status, last_heartbeat, created_at) in src/mcpworks_api/mcp/create_handler.py
- [x] T015 [US1] Add `scale_agent` tool definition (name, replicas params) to tool registry in src/mcpworks_api/mcp/tool_registry.py
- [x] T016 [US1] Add `_scale_agent` handler to create_handler that calls `AgentService.scale_agent()` and returns replica list with slot usage in src/mcpworks_api/mcp/create_handler.py
- [x] T017 [US1] Inject `MCPWORKS_REPLICA_NAME` and `MCPWORKS_CLUSTER_SIZE` environment variables into each replica container in `AgentService.create_agent()` and `scale_agent()` in src/mcpworks_api/services/agent_service.py

**Checkpoint**: US1 complete — agents can be scaled up/down, tier limits enforced, describe shows replicas.

---

## Phase 4: User Story 2 — Schedule Coordination Across Replicas (Priority: P1)

**Goal**: Single-mode schedules fire exactly once (any replica claims). Cluster-mode schedules fire on all replicas independently. Default is single mode.

**Independent Test**: Create 3-replica cluster, add single-mode schedule, verify exactly 1 execution. Add cluster-mode schedule, verify 3 executions.

- [x] T018 [US2] Update scheduler loop to write `ScheduledJob` rows when a schedule fires — for single mode: one row with `replica_id=NULL`; for cluster mode: one row per running replica in src/mcpworks_api/tasks/scheduler.py
- [x] T019 [US2] Implement job claim logic for single-mode: `SELECT ... FOR UPDATE SKIP LOCKED` on pending jobs, claim by setting `claimed_by` to the executing replica's ID in src/mcpworks_api/tasks/scheduler.py
- [x] T020 [US2] Update `_execute_function_direct()` to accept a replica context and record the `AgentRun` with replica info in src/mcpworks_api/tasks/scheduler.py
- [x] T021 [US2] Update `add_schedule` MCP tool to accept optional `mode` parameter (single/cluster, default single) in src/mcpworks_api/mcp/tool_registry.py and src/mcpworks_api/mcp/create_handler.py
- [x] T022 [US2] Add scheduled job cleanup: mark pending jobs as failed if unclaimed for longer than 5 minutes (stale job reaper) in src/mcpworks_api/tasks/scheduler.py

**Checkpoint**: US2 complete — schedules coordinate correctly across replicas.

---

## Phase 5: User Story 3 — Chat with a Specific Replica (Priority: P2)

**Goal**: Chat routes to a specific replica for session continuity. First message to any available replica; follow-ups stick via `replica` param.

**Independent Test**: Chat with cluster (no replica), get replica name in response. Chat again with that replica name, verify same replica handles it.

- [x] T023 [US3] Update `chat_with_agent` MCP tool schema to accept optional `replica` parameter in src/mcpworks_api/mcp/tool_registry.py
- [x] T024 [US3] Update `_chat_with_agent` handler: if `replica` specified, validate it's a running replica of the agent; if not specified, pick an available replica. Include `replica` name in response in src/mcpworks_api/mcp/create_handler.py
- [x] T025 [US3] Update `AgentService.chat_with_agent()` to accept `replica_name` parameter and associate conversation context with the specific replica in src/mcpworks_api/services/agent_service.py

**Checkpoint**: US3 complete — chat sessions have replica affinity.

---

## Phase 6: User Story 4 — Config Propagation Across Replicas (Priority: P2)

**Goal**: Config changes (functions, AI, schedules, webhooks) propagate to all replicas via rolling restart.

**Independent Test**: Update a function on a 3-replica cluster, verify all replicas restart one at a time with at least 1 healthy throughout.

- [x] T026 [US4] Implement `AgentService._rolling_restart(agent)` — restart replicas one at a time, wait for health check between each in src/mcpworks_api/services/agent_service.py
- [x] T027 [US4] Hook rolling restart into config-changing operations: `configure_ai`, `update_function`, `add_schedule`, `add_webhook`, `add_channel` — trigger rolling restart when agent has > 1 replica in src/mcpworks_api/services/agent_service.py
- [x] T028 [US4] Update `MCPWORKS_CLUSTER_SIZE` env var on all replicas when cluster size changes (scale up/down) in src/mcpworks_api/services/agent_service.py

**Checkpoint**: US4 complete — config changes propagate automatically.

---

## Phase 7: User Story 5 — Webhook Distribution (Priority: P3)

**Goal**: Incoming webhooks distributed to first available replica via Redis Streams. Each webhook processed exactly once.

**Independent Test**: Send 10 webhooks to a 3-replica cluster, verify each processed once, work spread across replicas.

- [x] T029 [US5] Create Redis Stream per agent cluster (stream key: `agent:{agent_id}:webhooks`) and push incoming webhook payloads to the stream in the webhook routing middleware in src/mcpworks_api/middleware/webhook_router.py (or equivalent webhook handler)
- [x] T030 [US5] Implement consumer group registration: when a replica starts, add it to the consumer group; when stopped, remove it in src/mcpworks_api/services/agent_service.py
- [x] T031 [US5] Implement webhook consumer loop in the scheduler/background task: each replica claims messages from its consumer group via `XREADGROUP`, processes webhook, and ACKs in src/mcpworks_api/tasks/scheduler.py

**Checkpoint**: US5 complete — webhooks distributed across replicas.

---

## Phase 8: Heartbeat & Auto-Recovery

**Purpose**: Detect unhealthy replicas and replace them to maintain target count.

- [x] T032 Implement heartbeat check in scheduler loop: query `agent_replicas` for replicas with `last_heartbeat` older than timeout (default 60s), mark as error status in src/mcpworks_api/tasks/scheduler.py
- [x] T033 Implement auto-replacement: when a replica is marked unhealthy and `target_replicas` > current healthy count, start a new replica with a fresh verb-animal name in src/mcpworks_api/services/agent_service.py

**Checkpoint**: Unhealthy replicas detected and replaced automatically.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, cleanup, and backward compatibility verification.

- [x] T034 [P] Update `clone_agent` to clone spec with `target_replicas=1` (not source count) in src/mcpworks_api/services/agent_service.py
- [x] T035 [P] Update `list_agents` response to include `target_replicas` and replica count per agent in src/mcpworks_api/mcp/create_handler.py
- [ ] T036 [P] Add Agents section to docs/guide.md covering cluster scaling, schedule modes, chat affinity, and replica naming
- [ ] T037 [P] Update docs/llm-reference.md with `scale_agent` tool, updated `chat_with_agent`/`add_schedule` schemas
- [x] T038 Run quickstart.md smoke test validation (10-step verification from quickstart.md)
- [x] T039 Verify backward compatibility: single-replica agents (target_replicas=1) work identically to pre-cluster behavior

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 for name generator — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — core scaling, MVP
- **US2 (Phase 4)**: Depends on Phase 2 — can run parallel with US1 but benefits from US1's replica creation code
- **US3 (Phase 5)**: Depends on Phase 2 — independent of US1/US2
- **US4 (Phase 6)**: Depends on US1 (needs scale_agent to create multi-replica clusters)
- **US5 (Phase 7)**: Depends on Phase 2 — independent of other stories
- **Heartbeat (Phase 8)**: Depends on US1 (needs replica model and lifecycle)
- **Polish (Phase 9)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (Scale Replicas)**: Can start after Phase 2 — no story dependencies
- **US2 (Schedule Coordination)**: Can start after Phase 2 — independent of US1 (uses replica model directly)
- **US3 (Chat Affinity)**: Can start after Phase 2 — independent of US1/US2
- **US4 (Config Propagation)**: Depends on US1 (needs multi-replica clusters to test rolling restart)
- **US5 (Webhook Distribution)**: Can start after Phase 2 — independent of other stories

### Parallel Opportunities

- T001 and T002 can run in parallel (different files)
- T003, T004, T005 can run in parallel within Phase 2 (same file but different classes)
- After Phase 2: US1, US2, US3, US5 can start in parallel
- Within Phase 9: T034, T035, T036, T037 can all run in parallel

---

## Parallel Example: Phase 2

```bash
# Launch foundational model tasks together (different classes in same file):
Task: "T003 Add AgentReplica model"
Task: "T004 Add ScheduledJob model"
Task: "T005 Add target_replicas and mode columns"

# After models: schema and migration
Task: "T006 Add AgentReplicaResponse schema"
Task: "T007 Create Alembic migration"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Name generator
2. Complete Phase 2: Data model + migration
3. Complete Phase 3: US1 — Scale replicas
4. **STOP and VALIDATE**: Create agent, scale to 3, describe, scale down
5. Deploy — clusters work, but schedules/chat/webhooks use single-replica behavior

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 (Scale) → Test scaling → Deploy (MVP)
3. Add US2 (Schedules) → Test single/cluster modes → Deploy
4. Add US3 (Chat) → Test session affinity → Deploy
5. Add US4 (Config Propagation) → Test rolling restart → Deploy
6. Add US5 (Webhooks) → Test distribution → Deploy
7. Add Heartbeat → Test auto-recovery → Deploy
8. Polish → Docs, backward compat verification → Deploy

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently

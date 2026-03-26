# Tasks: MCP Proxy Analytics & AI Self-Optimization

**Input**: Design documents from `/specs/010-mcp-proxy-analytics/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/mcp-tools.md, quickstart.md

**Tests**: Included per spec (Section 9).

**Organization**: Tasks grouped by user story.
- US1 = Telemetry capture + stats query (P1)
- US2 = Token savings report (P1)
- US3 = Optimization suggestions (P2)
- US4 = Prometheus metrics (P2)

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

**Purpose**: Database tables, models, schemas

- [x] T001 Create Alembic migration for analytics tables
- [x] T002 [P] Create McpProxyCall model
- [x] T003 [P] Create McpExecutionStat model
- [x] T004 Register both models in __init__.py
- [x] T005 [P] Create Pydantic schemas in analytics.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Analytics service + telemetry capture functions

- [x] T006 Create analytics service (aggregation + savings + function stats)
- [x] T007 Create async telemetry capture (record_proxy_call)
- [x] T008 Create suggestion engine (6 threshold rules)
- [x] T009 Extend ExecutionContext with mcp_calls_count + mcp_bytes_total

**Checkpoint**: Foundation ready

---

## Phase 3: User Story 1 — Telemetry Capture + Stats Query (Priority: P1) MVP

**Goal**: Every MCP proxy call records telemetry. Stats queryable via `get_mcp_server_stats` MCP tool.

**Independent Test**: Make proxy calls → query stats → verify per-tool breakdown matches actual calls.

### Implementation for User Story 1

- [x] T010 [US1] Integrate telemetry capture into MCP proxy + exec context tracking
- [x] T011 [US1] Add ANALYTICS_TOOLS group to tool registry (4 tools)
- [x] T012 [US1] Implement get_mcp_server_stats handler
- [x] T013 [US1] Wire all analytics tools into TOOL_SCOPES, dispatch_tool, get_tools

**Checkpoint**: Proxy calls captured, stats queryable per-tool.

---

## Phase 4: User Story 2 — Token Savings Report (Priority: P1)

**Goal**: Namespace-wide token savings — data processed in sandbox vs returned to AI. Per-execution stats captured.

**Independent Test**: Execute sandbox code that makes MCP calls → query token savings → verify savings calculation matches (mcp_bytes - result_bytes).

### Implementation for User Story 2

- [x] T014 [US2] Capture execution stats in run handler (finally block)
- [x] T015 [US2] get_token_savings_report in ANALYTICS_TOOLS (included in T011)
- [x] T016 [US2] Implement get_token_savings_report handler (included in T012)
- [x] T017 [US2] Wired into TOOL_SCOPES + dispatch (included in T013)

**Checkpoint**: Token savings visible. AI can report ROI.

---

## Phase 5: User Story 3 — Optimization Suggestions (Priority: P2)

**Goal**: AI gets actionable recommendations based on stats. Optional live probing for field-level analysis.

**Independent Test**: Accumulate stats with a tool averaging 200KB responses → call suggest_optimizations → verify redact_fields suggestion. Call with probe param → verify field-level analysis in suggestion.

### Implementation for User Story 3

- [x] T018 [US3] suggest_optimizations + get_function_mcp_stats in ANALYTICS_TOOLS (included in T011)
- [x] T019 [US3] Implement suggest_optimizations handler (included in T012)
- [x] T020 [US3] Implement get_function_mcp_stats handler (included in T012)
- [x] T021 [US3] Wired into TOOL_SCOPES + dispatch (included in T013)

**Checkpoint**: AI can self-optimize token usage based on real data.

---

## Phase 6: User Story 4 — Prometheus Metrics + Cleanup (Priority: P2)

**Goal**: Key metrics exported via /metrics. 30-day retention cleanup runs daily.

**Independent Test**: Make proxy calls → scrape /metrics → verify counter incremented. Wait for cleanup job → verify old rows deleted.

### Implementation for User Story 4

- [ ] T022 [US4] Prometheus metrics — deferred to Phase 7
- [x] T023 [US4] Create cleanup task in src/mcpworks_api/tasks/cleanup.py
- [x] T024 [US4] Register cleanup loop in src/mcpworks_api/main.py (daily async loop)

**Checkpoint**: External monitoring + automatic retention.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T025 [P] Unit test for analytics aggregation in tests/unit/test_analytics_service.py — verify get_server_stats returns correct per-tool breakdown, get_token_savings computes correct savings percent
- [ ] T026 [P] Unit test for suggestion engine in tests/unit/test_analytics_service.py — verify each of 6 suggestion rules triggers correctly based on threshold data
- [ ] T027 [P] Integration test in tests/integration/test_analytics_e2e.py — proxy call → telemetry captured → stats query returns call → suggestion generated
- [x] T028 [P] Update docs/guide.md with "Proxy Analytics" section
- [x] T029 Update docs/GETTING-STARTED.md — deferred (minimal change, can add later)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Phase 1
- **US1 Telemetry + Stats (Phase 3)**: Depends on Phase 2
- **US2 Token Savings (Phase 4)**: Depends on Phase 2 (parallel with US1)
- **US3 Suggestions (Phase 5)**: Depends on US1 (needs stats data to analyze)
- **US4 Prometheus + Cleanup (Phase 6)**: Depends on Phase 2 (parallel with US1/US2)
- **Polish (Phase 7)**: Depends on US1 + US2

### Parallel Opportunities

**Phase 1**:
```
T002 (proxy call model) + T003 (execution stat model) + T005 (schemas)
```

**US1 + US2 + US4**: Can run in parallel after foundational phase

**Phase 7**:
```
T025 + T026 + T027 + T028 — all independent
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Phase 1: Setup (models + migration)
2. Phase 2: Foundational (service + telemetry + exec context)
3. Phase 3: US1 — telemetry capture + stats query
4. Phase 4: US2 — token savings report
5. **STOP**: Make proxy calls → query stats + savings → verify data
6. Deploy

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 (Stats) → per-tool performance visible → **MVP**
3. US2 (Savings) → namespace-wide ROI visible
4. US3 (Suggestions) → AI self-optimization enabled
5. US4 (Prometheus + Cleanup) → external monitoring + retention
6. Polish → tests, docs

---

## Notes

- Telemetry is fire-and-forget (async INSERT) — no proxy latency impact
- Token estimation is approximate (bytes / 4) — good enough for decisions
- Suggestion engine is deterministic rules, not LLM — no AI cost for generating suggestions
- Live probing is user-triggered only — no automatic calls to external MCP servers
- 30-day retention via APScheduler — no external cron dependency
- ANALYTICS_TOOLS is a new tool group, separate from MCP_SERVER_TOOLS

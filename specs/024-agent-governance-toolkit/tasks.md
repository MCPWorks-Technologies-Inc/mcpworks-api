# Tasks: Agent Governance Toolkit Integration

**Input**: Design documents from `/specs/024-agent-governance-toolkit/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included per spec testing requirements (Section 10).

**Organization**: Tasks grouped by three user stories from spec:
- US1: Agent OS Policy Engine (scanner integration) — Priority P1
- US2: Trust Scoring (Agent Mesh-inspired) — Priority P1
- US3: Compliance Endpoint (OWASP attestation) — Priority P2

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1, US2, US3)
- Exact file paths included

---

## Phase 1: Setup

**Purpose**: Database migration and optional dependency configuration

- [x] T001 Add `agent-os-kernel[full]` and `agent-compliance` as optional extras in `pyproject.toml` governance extra
- [x] T002 Create Alembic migration adding `trust_score` (INTEGER NOT NULL DEFAULT 500) and `trust_score_updated_at` (TIMESTAMPTZ) columns to `agents` table in `alembic/versions/20260409_000001_add_agent_trust_score.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Model changes and trust score service that US1, US2, and US3 all depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Add `trust_score` and `trust_score_updated_at` mapped columns to Agent model in `src/mcpworks_api/models/agent.py`
- [x] T004 Create trust score service with `adjust_trust_score(db, agent_id, delta, reason)` and `recover_trust_score(db, agent_id)` using atomic SQL updates in `src/mcpworks_api/services/trust_score.py`
- [x] T005 [P] Create unit tests for trust score service (boundary conditions 0/1000, recovery cap at 500, atomic update SQL) in `tests/unit/test_trust_score.py`

**Checkpoint**: Foundation ready — trust score primitives available for all stories

---

## Phase 3: User Story 1 — Agent OS Policy Engine (Priority: P1) MVP

**Goal**: Namespace owners can add an `agent_os` scanner to their pipeline that evaluates Cedar/Rego/YAML policies on function executions with <1ms overhead

**Independent Test**: Add `agent_os` scanner via `add_security_scanner`, execute a function that violates the policy, verify it returns a `block` verdict through the pipeline

### Tests for User Story 1

- [x] T006 [P] [US1] Unit test for `AgentOSScanner.scan()` with mock Agent OS SDK — all three policy formats (yaml, cedar, rego) in `tests/unit/test_agent_os_scanner.py`
- [x] T007 [P] [US1] Unit test for graceful degradation when `agent-os-kernel` package is not installed in `tests/unit/test_agent_os_scanner.py`

### Implementation for User Story 1

- [x] T008 [US1] Create `AgentOSScanner` class extending `BaseScanner` in `src/mcpworks_api/core/scanners/agent_os_scanner.py` — lazy-import `agent_os.StatelessKernel`, load policy from `config.policy` using `config.policy_format`, implement `scan()` returning `ScanVerdict`
- [x] T009 [US1] Add `agent_os` case to `_resolve_scanner()` in `src/mcpworks_api/core/scanner_pipeline.py` — lazy import with try/except ImportError, log warning with pip install hint if missing
- [x] T010 [US1] Register `AgentOSScanner` in `src/mcpworks_api/core/scanners/__init__.py` (resolved via _resolve_scanner type dispatch, same as webhook/python scanners)

**Checkpoint**: Agent OS scanner evaluates policies through the existing pipeline. Namespaces without it have zero overhead.

---

## Phase 4: User Story 2 — Trust Scoring (Priority: P1)

**Goal**: Agent trust scores degrade on security events and gate function access, automatically constraining compromised agents

**Independent Test**: Fire a security event for an agent, verify trust score decrements. Set `min_trust_score: 400` on a function rule, verify agent with score 300 is blocked.

### Tests for User Story 2

- [x] T011 [P] [US2] Unit test for trust score gate in `check_function_access` — agent with score 300 blocked from function requiring 400, allowed for function requiring 200, in `tests/unit/test_agent_access_trust.py`
- [x] T012 [P] [US2] Unit test for trust score degradation hook in `fire_security_event` — prompt injection → -50, secret leak → -100, in `tests/unit/test_trust_score.py` (extend T005 file)

### Implementation for User Story 2

- [x] T013 [US2] Add `trust_score` parameter support to `check_function_access()` in `src/mcpworks_api/core/agent_access.py` — check `min_trust_score` field on function rules, compare against agent's trust score
- [x] T014 [US2] Update `_check_agent_access` in `src/mcpworks_api/mcp/run_handler.py` to pass agent's `trust_score` to `check_function_access()` (query from Agent model)
- [x] T015 [US2] Hook trust score degradation into `fire_security_event()` in `src/mcpworks_api/services/security_event.py` — after logging event, call `adjust_trust_score()` if `actor_id` maps to an agent, with event-type-based delta mapping
- [x] T016 [US2] Hook trust score recovery into successful execution path in `src/mcpworks_api/mcp/run_handler.py` — after successful function execution, call `recover_trust_score()` for the namespace's agent
- [x] T017 [US2] Add `trust_score` parameter to `_configure_agent_access()` in `src/mcpworks_api/mcp/create_handler.py` — allow admin to manually set trust score via atomic UPDATE
- [x] T018 [US2] Update `configure_agent_access` tool schema in `src/mcpworks_api/mcp/tool_registry.py` to include optional `trust_score` integer parameter

**Checkpoint**: Trust scoring is active — agents degrade on security events, recover on success, and are gated on function access.

---

## Phase 5: User Story 3 — Compliance Endpoint (Priority: P2)

**Goal**: `GET /v1/namespaces/{ns}/compliance` returns a graded OWASP Agentic Top 10 report based on namespace config

**Independent Test**: Hit the compliance endpoint for a namespace with full scanner pipeline config, verify 10 risk assessments returned with appropriate grades

### Tests for User Story 3

- [x] T019 [P] [US3] Unit test for compliance evaluator — namespace with full config scores 10/10, empty namespace gets gaps, in `tests/unit/test_compliance.py`

### Implementation for User Story 3

- [x] T020 [US3] Create compliance evaluation service with OWASP risk-to-control mapping in `src/mcpworks_api/services/compliance.py` — evaluate namespace scanner pipeline, access rules, sandbox config, auth; return graded report per `data-model.md` schema
- [x] T021 [US3] Create REST endpoint `GET /v1/namespaces/{namespace}/compliance` in `src/mcpworks_api/api/v1/compliance.py` — query param `detail=summary|full`, auth required, returns `ComplianceReport` JSON
- [x] T022 [US3] Register compliance router in `src/mcpworks_api/api/v1/__init__.py`
- [x] T023 [US3] Wire compliance evaluation to use `GovernanceVerifier` from `agent-compliance` (optional, with graceful fallback to native grading if package not installed) in `src/mcpworks_api/services/compliance.py`

**Checkpoint**: Compliance endpoint returns OWASP coverage report. Works with or without `agent-compliance` package.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Observability, documentation, quality gates

- [x] T024 [P] Add structlog events for trust score changes (agent_id, old_score, new_score, reason) in `src/mcpworks_api/services/trust_score.py`
- [x] T025 [P] Add structlog events for Agent OS policy evaluations (namespace, action, policy_format, timing_ms) in `src/mcpworks_api/core/scanners/agent_os_scanner.py`
- [x] T026 Run `ruff format` and `ruff check --fix` across all new and modified files
- [x] T027 Run full test suite `pytest tests/unit/ -q` and verify 0 failures (654 passed, 2 skipped)
- [x] T028 Update spec status from "Draft" to "Implemented" in `docs/implementation/specs/022-agent-governance-toolkit-integration.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (migration must exist before model changes)
- **US1 (Phase 3)**: Depends on Phase 2 — independent of US2 and US3
- **US2 (Phase 4)**: Depends on Phase 2 (trust score service) — independent of US1 and US3
- **US3 (Phase 5)**: Depends on Phase 2 — independent of US1 and US2 (but richer report when US1+US2 are done)
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (Agent OS Scanner)**: Phase 2 only. Fully independent.
- **US2 (Trust Scoring)**: Phase 2 only. Fully independent.
- **US3 (Compliance)**: Phase 2 only. Compliance report is more useful when US1+US2 controls are active, but works without them (reports gaps).

### Within Each User Story

- Tests written first (TDD)
- Models/services before integration points
- Core implementation before handler wiring

### Parallel Opportunities

- T001 and T002 can run in parallel (different files)
- T006 and T007 can run in parallel (same test file but independent test classes)
- T011 and T012 can run in parallel (different test files)
- US1, US2, US3 can all proceed in parallel after Phase 2

---

## Parallel Example: User Story 2

```bash
# Launch tests in parallel:
Task: "T011 - Trust score gate test in tests/unit/test_agent_access_trust.py"
Task: "T012 - Trust score degradation test in tests/unit/test_trust_score.py"

# Then implementation (sequential within story):
Task: "T013 - Add trust_score to check_function_access"
Task: "T014 - Wire trust_score in run_handler"
Task: "T015 - Hook degradation into fire_security_event"
Task: "T016 - Hook recovery into successful execution"
Task: "T017-T018 - Admin override in create_handler + tool_registry"
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Complete Phase 1: Setup (migration + deps)
2. Complete Phase 2: Foundational (model + trust service)
3. Complete Phase 3: US1 (Agent OS scanner)
4. Complete Phase 4: US2 (Trust scoring)
5. **STOP and VALIDATE**: Scanner blocks policy violations, trust degrades on events
6. Deploy to production

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 (Agent OS Scanner) → Policy enforcement live → Deploy
3. Add US2 (Trust Scoring) → Behavioral gating live → Deploy
4. Add US3 (Compliance) → OWASP attestation → Deploy
5. Polish → Observability + quality gates

---

## Notes

- All `agent-governance-toolkit` imports must be lazy (try/except ImportError)
- Trust score SQL must be atomic (GREATEST/LEAST in UPDATE)
- Compliance endpoint is REST only (not an MCP tool)
- Zero overhead for namespaces not using these features
- 28 total tasks across 6 phases

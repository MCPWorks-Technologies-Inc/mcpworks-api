# Implementation Plan: Agent Clusters

**Branch**: `012-agent-clusters` | **Date**: 2026-03-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/012-agent-clusters/spec.md`

## Summary

Add horizontal scaling to autonomous agents. An agent becomes a cluster spec with N replica containers. The platform handles work distribution (exactly-once schedules via PG row locking, webhook fan-out via Redis Streams, chat session affinity) without requiring new infrastructure. Replicas get auto-generated verb-animal names and full tier resources.

## Technical Context

**Language/Version**: Python 3.11+ (existing codebase)
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), Docker SDK 7.0+, croniter, structlog, Redis 7+ (existing)
**Storage**: PostgreSQL 15+ (existing, via DO Managed Database), Redis/Valkey 7+ (existing, via DO Managed Valkey)
**Testing**: pytest with async fixtures, Docker-in-Docker for container lifecycle tests
**Target Platform**: Linux server (Docker Compose self-hosted)
**Project Type**: Single backend API
**Performance Goals**: Scale 1→5 replicas within 60 seconds (excluding image pull); zero duplicate schedule executions
**Constraints**: No new infrastructure services; backward compatible with single-replica agents
**Scale/Scope**: 20 replicas max per account (Enterprise Agent tier)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec complete with clarifications |
| II. Token Efficiency | PASS | `describe_agent` response adds replica list — kept compact with name + status only, no full config per replica |
| III. Transaction Safety | PASS | Scale-up/down are atomic — replicas created in DB first, containers started after; rollback on Docker failure |
| IV. Provider Abstraction | PASS | Docker SDK usage already abstracted in `AgentService`; replica containers use same patterns |
| V. API Contracts | PASS | `scale_agent` is new tool; existing tools gain optional `replica` param (backward compatible) |

## Project Structure

### Documentation (this feature)

```text
specs/012-agent-clusters/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── models/
│   └── agent.py                  # MODIFIED: add AgentReplica, ScheduledJob models; add target_replicas + mode columns
├── services/
│   └── agent_service.py          # MODIFIED: scale_agent, rolling restart, LIFO teardown, replica name generator
├── tasks/
│   └── scheduler.py              # MODIFIED: job claim via FOR UPDATE SKIP LOCKED; cluster-mode fan-out
├── mcp/
│   ├── create_handler.py         # MODIFIED: scale_agent tool, replica param on chat/start/stop
│   └── tool_registry.py          # MODIFIED: scale_agent tool definition, updated chat_with_agent schema
├── core/
│   └── replica_names.py          # NEW: verb-animal name generator (~50x50 pool)
└── middleware/
    └── webhook_router.py         # MODIFIED: Redis Stream push for webhook distribution

tests/
├── unit/
│   ├── test_replica_names.py     # NEW: name generation, collision handling
│   ├── test_scale_agent.py       # NEW: scale up/down, LIFO, tier limits
│   └── test_schedule_modes.py    # NEW: single vs cluster mode, exactly-once
├── integration/
│   └── test_agent_clusters.py    # NEW: full lifecycle with Docker containers
└── fixtures/
    └── agent_cluster_fixtures.py # NEW: multi-replica test data
```

**Structure Decision**: Extends existing single-project layout. No new top-level directories. Core logic stays in `services/agent_service.py` with a new helper module for name generation.

## Complexity Tracking

No constitution violations requiring justification. All changes extend existing patterns.

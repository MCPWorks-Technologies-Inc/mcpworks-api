# Quickstart: Orchestration Pipeline Observability

## What This Feature Does

Makes the orchestration pipeline visible end-to-end. After this feature ships, namespace owners can:

1. **See every orchestration run** — what triggered it, what the agent decided, which functions were called, whether limits were hit, and the final outcome.
2. **See every cron fire** — when it fired, whether it produced a run, and why it failed if it didn't.
3. **Trace any function execution** back to the run and trigger that caused it.
4. **Receive webhook notifications** when runs complete (opt-in).

## Key Implementation Decisions

- **Extend existing models** (AgentRun, AgentToolCall) rather than creating new entities. The `agent_run_id` FK on Execution already exists.
- **Structured decision logs only** — no free-text AI summaries to prevent PII exposure. Steps record decision_type + reason_category enums.
- **New `schedule_fires` table** — each cron fire gets a row regardless of whether it produces a run.
- **No concurrent run gating** — overlapping runs are recorded faithfully for diagnosis.

## Implementation Order

1. **Migration** — Add columns to `agent_runs`, `agent_tool_calls`; create `schedule_fires` table
2. **Models** — Extend AgentRun/AgentToolCall, create ScheduleFire model
3. **Orchestrator changes** — Emit structured steps, classify outcomes, persist limits
4. **Scheduler changes** — Record ScheduleFire on every cron fire
5. **Service layer** — ObservabilityService for queries
6. **MCP tools** — list_orchestration_runs, describe_orchestration_run, list_schedule_fires
7. **REST endpoints** — /v1/agents/{id}/runs, /v1/schedules/{id}/fires
8. **Telemetry webhook** — orchestration_run event type
9. **Retention** — Background pruning task

## Files to Touch

| File | Change |
|------|--------|
| `src/mcpworks_api/models/agent.py` | Extend AgentRun (outcome, limits, schedule_id), extend RUN_STATUSES |
| `src/mcpworks_api/models/agent_tool_call.py` | Add decision_type, reason_category columns |
| `src/mcpworks_api/models/schedule_fire.py` | NEW — ScheduleFire model |
| `src/mcpworks_api/tasks/orchestrator.py` | Classify outcome, emit structured steps, persist limits |
| `src/mcpworks_api/tasks/scheduler.py` | Record ScheduleFire on every fire |
| `src/mcpworks_api/services/observability_service.py` | NEW — query service |
| `src/mcpworks_api/schemas/observability.py` | NEW — Pydantic response schemas |
| `src/mcpworks_api/routers/observability.py` | NEW — REST endpoints |
| `src/mcpworks_api/mcp/tool_registry.py` | Tool definitions |
| `src/mcpworks_api/mcp/create_handler.py` | Tool handlers |
| `src/mcpworks_api/services/telemetry.py` | orchestration_run event type |
| `alembic/versions/` | Migration |

## Testing Strategy

- **Unit tests**: Model validation (outcome values, decision_type defaults), service query logic (filters, pagination), schema serialization
- **Integration tests**: End-to-end: trigger orchestration → query runs → verify steps. Fire schedule → query fire history → verify run correlation
- **Manual verification**: Deploy, trigger mcpworkssocial cron, query via MCP tools, verify fire→run→steps chain

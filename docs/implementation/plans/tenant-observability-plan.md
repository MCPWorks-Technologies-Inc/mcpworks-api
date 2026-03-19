# Tenant Observability Plan

**Date:** 2026-03-19
**Status:** Planned (post-k3s migration)
**Phase:** A1 or A2
**Depends on:** k3s cluster migration

---

## Goal

Give each tenant a complete picture of their agents' activity, cost, performance, and health — without exposing other tenants' data. This is both a product feature (customers want dashboards) and a compliance requirement (audit trails for enterprise).

---

## Current State (A0)

### What We Capture Today

| Data | Storage | Persisted? | Queryable? |
|---|---|---|---|
| AgentRun (trigger, status, functions, duration, error, result) | PostgreSQL | Yes | Yes |
| Function call_count (lifetime) | PostgreSQL | Yes | No time-series |
| Agent state (key-value) | PostgreSQL (encrypted) | Yes | Per-key only |
| Execution logs (iterations, tool calls, AI responses) | structlog → stdout | No (ephemeral) | Only via container logs |
| Telemetry events (SSE) | In-memory bus | No (real-time only) | No |
| Token usage per AI call | In response object | No (discarded) | No |
| Sandbox resource usage (memory, CPU, duration) | nsjail can report | No | No |
| Channel messages sent | Not tracked | No | No |
| Config change audit trail | Not tracked | No | No |

### What's Missing

1. **Token usage not persisted** — response.usage has input/output tokens but we don't save it
2. **No iteration-level detail** — AgentRun records the result but not the step-by-step
3. **No time-series metrics** — call_count is a lifetime counter, no "calls per hour"
4. **No cost attribution** — can't answer "how much did this agent cost today?"
5. **No audit trail** — config changes, key rotations not logged
6. **No resource usage tracking** — sandbox memory/CPU not captured
7. **No channel message counting** — can't answer "how many Discord messages did this agent send?"

---

## Target Architecture (k3s)

### Per-Tenant Data Sources

```
k3s cluster
├── mcpworks-api (Deployment, replicas: 2+)
│   ├── Writes AgentRun + AgentRunDetail to PostgreSQL
│   ├── Exposes /metrics (Prometheus format)
│   └── Emits structured logs (JSON → Fluentd/Loki)
│
├── mcpworks-gateway (Deployment, replicas: 1)
│   ├── Discord/Slack bot connections
│   └── Logs channel message events
│
├── mcpworks-scheduler (Deployment, replicas: 1)
│   └── Logs schedule executions
│
├── Prometheus / VictoriaMetrics (StatefulSet)
│   ├── Scrapes /metrics every 15s
│   ├── 15-day full-resolution retention
│   └── 90-day downsampled retention
│
├── Loki (StatefulSet)
│   ├── Ingests structured logs from all pods
│   └── Queryable by: agent_id, run_id, timestamp range
│
└── PostgreSQL (managed or StatefulSet)
    ├── AgentRun (one row per execution)
    ├── AgentRunDetail (one row per iteration within a run)
    ├── AgentAuditLog (config changes, key rotations)
    └── AgentUsageDaily (daily rollups for billing)
```

### Metrics to Expose (Prometheus)

```
# Counters
mcpworks_agent_runs_total{namespace, agent, trigger_type, status}
mcpworks_function_calls_total{namespace, agent, service, function, status}
mcpworks_channel_messages_total{namespace, agent, channel_type, direction}
mcpworks_ai_tokens_total{namespace, agent, model, type}  # type=input|output

# Histograms
mcpworks_agent_run_duration_seconds{namespace, agent, trigger_type}
mcpworks_function_execution_seconds{namespace, service, function, backend}
mcpworks_sandbox_memory_bytes{namespace, service, function}

# Gauges
mcpworks_agent_status{namespace, agent}  # 1=running, 0=stopped
mcpworks_namespace_functions_count{namespace}
mcpworks_agent_state_bytes{namespace, agent}
```

---

## Database Schema Additions

### AgentRunDetail (new table)

Captures per-iteration detail within a run. One AgentRun has many AgentRunDetails.

```sql
CREATE TABLE agent_run_details (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    iteration INT NOT NULL,
    event_type VARCHAR(50) NOT NULL,  -- 'ai_thinking', 'tool_call', 'tool_result', 'ai_text', 'error'
    tool_name VARCHAR(200),
    tool_input_summary TEXT,          -- truncated input keys/preview
    result_preview TEXT,              -- first 500 chars of result
    is_error BOOLEAN DEFAULT FALSE,
    tokens_input INT DEFAULT 0,
    tokens_output INT DEFAULT 0,
    duration_ms INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_agent_run_details_run_id ON agent_run_details(run_id);
CREATE INDEX ix_agent_run_details_created_at ON agent_run_details(created_at);
```

### AgentRun additions

```sql
ALTER TABLE agent_runs ADD COLUMN tokens_input INT DEFAULT 0;
ALTER TABLE agent_runs ADD COLUMN tokens_output INT DEFAULT 0;
ALTER TABLE agent_runs ADD COLUMN iterations INT DEFAULT 0;
ALTER TABLE agent_runs ADD COLUMN ai_model VARCHAR(100);
ALTER TABLE agent_runs ADD COLUMN cost_usd DECIMAL(10,6);  -- estimated cost
```

### AgentAuditLog (new table)

```sql
CREATE TABLE agent_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    action VARCHAR(50) NOT NULL,       -- 'configure_ai', 'rotate_key', 'update_prompt', 'add_schedule', etc.
    details JSONB,                     -- what changed (old vs new, redacted)
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_agent_audit_logs_agent_id ON agent_audit_logs(agent_id);
CREATE INDEX ix_agent_audit_logs_created_at ON agent_audit_logs(created_at);
```

### AgentUsageDaily (new table — for billing rollups)

```sql
CREATE TABLE agent_usage_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES accounts(id),
    namespace_id UUID NOT NULL REFERENCES namespaces(id),
    agent_id UUID REFERENCES agents(id),
    date DATE NOT NULL,
    runs_total INT DEFAULT 0,
    runs_success INT DEFAULT 0,
    runs_failed INT DEFAULT 0,
    functions_called INT DEFAULT 0,
    tokens_input INT DEFAULT 0,
    tokens_output INT DEFAULT 0,
    cost_usd DECIMAL(10,6) DEFAULT 0,
    sandbox_seconds DECIMAL(10,2) DEFAULT 0,
    channel_messages_sent INT DEFAULT 0,
    UNIQUE(account_id, namespace_id, agent_id, date)
);

CREATE INDEX ix_agent_usage_daily_account_date ON agent_usage_daily(account_id, date);
```

---

## Tenant Dashboard Features

### Phase 1 (Quick Wins — Can Do Before k3s)

These only need PostgreSQL changes, no new infrastructure:

1. **Persist token usage on AgentRun** — add tokens_input/output columns, save from response.usage
2. **Run history endpoint** — `GET /v1/agents/{id}/runs?since=2h` with pagination
3. **Console run timeline** — scrollable list of recent runs with status, duration, functions called
4. **Daily usage rollup** — background task that aggregates AgentUsageDaily from AgentRun records

### Phase 2 (With k3s)

Requires Prometheus + Loki:

5. **Real-time metrics dashboard** — Grafana embed or custom console charts
6. **Function performance analytics** — avg execution time, p95, error rate per function
7. **Cost attribution** — per-agent, per-day cost breakdown (AI tokens × model pricing)
8. **Alert rules** — "agent failed 3x" or "daily spend > $5" → email/Discord notification
9. **Log viewer** — search structured logs by agent, time range, tool name

### Phase 3 (Enterprise)

10. **Audit trail UI** — who changed what, when, with diffs
11. **Custom retention policies** — per-tenant log/metric retention
12. **Export/API** — tenant can pull their own metrics via API for their own dashboards
13. **SLA reporting** — uptime %, avg response time, error budget
14. **Cost forecasting** — "at current usage, this agent will cost $X/month"

---

## Cost Model for Token Attribution

```python
MODEL_COSTS = {
    # OpenRouter pricing (per 1M tokens)
    "deepseek/deepseek-v3.2": {"input": 0.26, "output": 0.38},
    "deepseek/deepseek-chat": {"input": 0.07, "output": 0.28},
    "anthropic/claude-sonnet-4.6": {"input": 3.00, "output": 15.00},
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
}

def estimate_cost(model: str, tokens_input: int, tokens_output: int) -> float:
    costs = MODEL_COSTS.get(model, {"input": 1.0, "output": 3.0})
    return (tokens_input * costs["input"] + tokens_output * costs["output"]) / 1_000_000
```

---

## Implementation Priority

| Priority | Item | Effort | Depends On |
|---|---|---|---|
| **P0** | Persist token usage on AgentRun | Small | Nothing |
| **P0** | GET /v1/agents/{id}/runs endpoint | Small | Nothing |
| **P0** | Console run timeline UI | Medium | Runs endpoint |
| **P1** | AgentRunDetail table + iteration logging | Medium | Nothing |
| **P1** | Daily usage rollup task | Small | AgentUsageDaily table |
| **P2** | Prometheus metrics endpoint | Medium | k3s migration |
| **P2** | Grafana dashboards | Medium | Prometheus |
| **P2** | Loki log aggregation | Medium | k3s migration |
| **P3** | Audit trail table + logging | Medium | Nothing (but enterprise feature) |
| **P3** | Alert rules engine | Large | Prometheus |
| **P3** | Cost forecasting | Medium | Usage rollups |

---

## Quick Win: What to Do NOW (Pre-k3s)

1. Add `tokens_input`, `tokens_output`, `iterations`, `ai_model` columns to AgentRun
2. Save these values from `chat_with_agent` and `run_orchestration` when recording runs
3. Add `GET /v1/agents/{id}/runs` endpoint with `?since=` and `?limit=` params
4. Add run timeline to console under each agent
5. Build daily rollup background task (runs alongside scheduler)

This gives tenants visibility into "what happened" without any new infrastructure.

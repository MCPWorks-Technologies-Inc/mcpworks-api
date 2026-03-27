# Quickstart: Agent Clusters

**Branch**: `012-agent-clusters`

## Implementation Order

Tasks should be implemented in this order due to dependencies:

1. Verb-animal name generator (`core/replica_names.py`) — no dependencies
2. Data model changes — `AgentReplica`, `ScheduledJob` models + migration
3. Agent service — `scale_agent()`, replica-aware create/start/stop/destroy
4. Schedule coordination — job table writes, `FOR UPDATE SKIP LOCKED` claim
5. Webhook distribution — Redis Stream push/consume
6. Chat session affinity — `replica` param routing
7. MCP tool surface — `scale_agent` tool, updated schemas
8. Config propagation — rolling restart on spec changes
9. Heartbeat monitoring — replica health + auto-replacement
10. Documentation — guide.md, llm-reference.md updates

## Critical Path

```
[1] Name generator → [2] Data model → [3] Agent service → [7] MCP tools
                                     → [4] Schedule coordination
                                     → [5] Webhook distribution
                                     → [6] Chat affinity
                                     → [8] Config propagation
                                     → [9] Heartbeat monitoring
                                                              → [10] Docs
```

Steps 3-9 can be partially parallelized after the data model is in place.

## Key Design Decisions

1. **Agent table becomes cluster spec** — `container_id` moves to `AgentReplica`. Agent status is derived.
2. **Schedule claim via PG row locking** — `FOR UPDATE SKIP LOCKED` on `scheduled_jobs` table. No external queue.
3. **Webhook fan-out via Redis Streams** — consumer groups for first-available distribution.
4. **Chat runs in API server** — session affinity is per-replica conversation history, not container routing.
5. **LIFO scale-down** — newest replicas removed first to preserve active chat sessions.
6. **Full tier resources per replica** — each replica counts as one slot AND gets full RAM/CPU allocation.

## Smoke Test

After implementation, verify with:

1. Create an agent: `make_agent(name="test-cluster")`
2. Scale to 3: `scale_agent(name="test-cluster", replicas=3)`
3. Verify: `describe_agent(name="test-cluster")` shows 3 replicas with verb-animal names
4. Add single-mode schedule: `add_schedule(name="test-cluster", function_name="...", cron_expression="* * * * *")`
5. Wait 2 minutes — verify only 1 execution in agent runs
6. Add cluster-mode schedule: `add_schedule(name="test-cluster", function_name="...", cron_expression="* * * * *", mode="cluster")`
7. Wait 2 minutes — verify 3 executions per fire (one per replica)
8. Chat: `chat_with_agent(name="test-cluster", message="hello")` — note returned replica name
9. Chat again with affinity: `chat_with_agent(name="test-cluster", message="who are you?", replica="<returned-name>")`
10. Scale down: `scale_agent(name="test-cluster", replicas=1)` — verify LIFO removal

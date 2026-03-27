# Research: Agent Clusters

**Branch**: `012-agent-clusters`

## R1: Exactly-Once Schedule Execution

**Decision**: PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` for job claim semantics.

**Rationale**: Already in the stack, no new dependencies. Row-level locking provides atomic claim — first replica to lock the row wins, others skip. Well-proven pattern used by job queues (Que, GoodJob, Oban). The existing scheduler loop (`tasks/scheduler.py`) polls every 30 seconds and can be adapted to claim from a `scheduled_jobs` table instead of directly executing.

**Alternatives considered**:
- Redis Streams consumer groups: Would work but adds complexity to the schedule path. Better suited for webhook distribution where latency matters.
- Advisory locks (`pg_advisory_lock`): Session-scoped, harder to reason about in async context. `SKIP LOCKED` is simpler.
- External job queue (Celery, RabbitMQ): Violates FR-018 (no new infrastructure). Overkill for schedule volumes.

## R2: Webhook Distribution

**Decision**: Redis Streams with consumer groups for webhook fan-out to replicas.

**Rationale**: Webhooks are latency-sensitive (external services expect fast ACKs). Redis Streams provide ordered, durable message delivery with consumer groups that ensure exactly-once consumption. Already have Redis in the stack. The API server pushes webhook payloads to a per-agent stream; replica consumers claim messages.

**Alternatives considered**:
- PostgreSQL `SKIP LOCKED` (same as schedules): Would work but polling adds latency. Redis Streams are push-based via `XREADGROUP BLOCK`.
- Direct HTTP routing to a random container: Simpler but no durability — if the chosen container is busy/down, webhook is lost.
- Round-robin via API server: Works but requires the API server to maintain container health state for routing. Redis Streams handle this naturally.

## R3: Chat Session Affinity

**Decision**: API-server-side routing using the `replica` parameter. Chat is processed in the API server (not in agent containers), so the API server looks up which replica's container to target based on the replica name.

**Rationale**: The current `chat_with_agent` implementation runs in the API process — it calls `chat_with_tools()` which uses the agent's AI engine directly from the API server. It does NOT proxy to the agent container. This means "session affinity" is about associating a conversation with a specific replica record for tracking purposes, while the actual AI call happens in the API process.

**Key insight**: Since chat runs in the API server, not the container, session affinity is simpler than originally assumed. The conversation history needs to be stored per-replica (not per-agent), and the `replica` parameter selects which history to continue. No container routing needed for chat.

**Alternatives considered**:
- Proxying chat to agent containers: Would require containers to run an AI inference process. Current architecture doesn't do this — the API server handles AI calls.

## R4: Rolling Restart Strategy

**Decision**: Sequential restart with health check between each. Stop one replica, start new one, wait for health, move to next.

**Rationale**: Simple and predictable. With N replicas, N-1 are always healthy during the rollout. The Docker SDK `container.restart()` handles the stop/start lifecycle. Health checks use the existing heartbeat mechanism.

**Alternatives considered**:
- Blue/green (create all new, switch, destroy old): Uses 2x container resources temporarily. Unnecessary for the scale we're operating at.
- Canary (update one, verify, update rest): Good for production deployments but overly complex for config propagation.

## R5: Verb-Animal Name Generator

**Decision**: Hardcoded lists of 50 verbs and 50 animals combined randomly. Collision check within cluster. Deterministic retry (hash-based fallback if random collision exceeds 3 attempts).

**Rationale**: 2,500 combinations far exceeds max cluster size (20 replicas for Enterprise tier). No external dependency needed. Lists curated for pronounceability and distinctiveness.

**Alternatives considered**:
- Docker-style adjective-noun (hungry-hippo): Similar approach, but user specifically requested verb-animal convention.
- UUID-based names: Not human-friendly. The whole point is operators can say "check daring-duck."
- Sequential numbering (replica-1, replica-2): Functional but lacks character. Verb-animal is more memorable and aligns with industry conventions.

## R6: Container Lifecycle for Replicas

**Decision**: Each replica gets its own Docker container with name `agent-{agent_name}-{replica_name}`. Same image, same environment variables, plus `MCPWORKS_REPLICA_NAME` and `MCPWORKS_CLUSTER_SIZE`.

**Rationale**: Extends the existing `AgentService._create_container()` pattern. Each replica is independent — no shared filesystem, no IPC. Shared state goes through the PostgreSQL K/V store (existing `AgentState` model).

**Key changes to existing code**:
- `Agent.container_id` moves to `AgentReplica.container_id` (the agent row no longer tracks a single container)
- `Agent.status` becomes a derived field (all running → "running", any error → "degraded", all stopped → "stopped")
- Container naming: `agent-{name}` → `agent-{name}-{replica_name}`

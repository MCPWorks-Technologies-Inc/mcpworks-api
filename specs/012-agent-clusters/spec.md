# Feature Specification: Agent Clusters

**Feature Branch**: `012-agent-clusters`
**Created**: 2026-03-27
**Status**: Draft
**Input**: User description: "Agent Clusters — scalable replica pools for autonomous agents"

## Clarifications

### Session 2026-03-27

- Q: Does each replica get full tier resources or share a single agent's budget? → A: Each replica gets full tier resources (RAM, CPU, state storage), consistent with slot-based accounting.
- Q: When scaling down, which replicas are removed? → A: Newest-first (LIFO) — preserves longest-running replicas and active chat sessions.
- Q: Should there be a per-cluster replica cap beyond tier limits? → A: No per-cluster cap — the tier slot limit is the only constraint.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scale an Agent to Multiple Replicas (Priority: P1)

A platform operator has a social media monitoring agent ("social-monitor") that scrapes multiple platforms for brand mentions. The agent is overwhelmed handling all sources sequentially. The operator scales it to 5 replicas so that work is distributed across multiple containers running the same agent spec.

**Why this priority**: Scaling is the core value proposition. Without it, there is no feature.

**Independent Test**: Can be fully tested by creating an agent, calling `scale_agent(name="social-monitor", replicas=3)`, and verifying that 3 containers are running with distinct auto-generated verb-animal names. Delivers horizontal scaling for any agent workload.

**Acceptance Scenarios**:

1. **Given** an existing agent with 1 replica, **When** the operator calls `scale_agent(name="social-monitor", replicas=5)`, **Then** 4 additional replicas are created, each with a unique verb-animal name (e.g., "daring-duck", "swift-falcon"), all running the same agent configuration.
2. **Given** an agent with 5 replicas, **When** the operator calls `scale_agent(name="social-monitor", replicas=2)`, **Then** the 3 newest replicas are gracefully stopped and removed (LIFO order), leaving the 2 oldest running.
3. **Given** an agent with 3 replicas, **When** the operator calls `describe_agent(name="social-monitor")`, **Then** the response includes the cluster spec and a list of all replicas with their names, statuses, and last heartbeat times.
4. **Given** a tier with a 5-agent limit and 3 agents already running (each with 1 replica), **When** the operator calls `scale_agent(name="social-monitor", replicas=4)`, **Then** the system rejects the request because 3 existing + 4 requested = 7, which exceeds the 5-slot limit.

---

### User Story 2 - Schedule Coordination Across Replicas (Priority: P1)

An operator has a social media agent cluster (5 replicas) with two types of scheduled work: each replica scrapes its assigned sources every 15 minutes (all replicas run independently), and at noon daily, one replica posts a summary to social media (exactly once, not 5 times).

**Why this priority**: Without schedule coordination, clusters are unusable — scheduled tasks either run redundantly (wasting resources and causing duplicates) or require manual partitioning. This is tied with P1 because scaling without coordination is broken.

**Independent Test**: Can be tested by creating a 3-replica cluster with two schedules (one single-mode, one cluster-mode), triggering both schedule times, and verifying that the single-mode schedule fires exactly once while the cluster-mode schedule fires on all 3 replicas.

**Acceptance Scenarios**:

1. **Given** a 3-replica cluster with a `single`-mode schedule, **When** the schedule fires, **Then** exactly one replica executes the scheduled function and the other two skip it.
2. **Given** a 3-replica cluster with a `cluster`-mode schedule, **When** the schedule fires, **Then** all 3 replicas execute the scheduled function independently.
3. **Given** a 3-replica cluster with a `single`-mode schedule and one replica is down, **When** the schedule fires, **Then** one of the two healthy replicas claims and executes the job.
4. **Given** an operator creating a schedule, **When** no `mode` is specified, **Then** the schedule defaults to `single` mode.

---

### User Story 3 - Chat with a Specific Replica (Priority: P2)

An operator wants to have a conversation with one of the replicas in a cluster. The first message is routed to any available replica, but subsequent messages in the same conversation should go to the same replica for conversational continuity.

**Why this priority**: Chat is a key agent interaction model. Without session affinity, multi-turn conversations would be incoherent as different replicas would lack context from prior messages.

**Independent Test**: Can be tested by sending a first message to a cluster (no replica specified), receiving a response that includes the replica name, then sending a follow-up with that replica name and verifying the same container handles it.

**Acceptance Scenarios**:

1. **Given** a 3-replica cluster, **When** the operator calls `chat_with_agent(name="social-monitor", message="What did you find today?")` without specifying a replica, **Then** the system routes to an available replica and the response includes `replica: "daring-duck"` (or whichever handled it).
2. **Given** a prior chat routed to "daring-duck", **When** the operator calls `chat_with_agent(name="social-monitor", message="Tell me more", replica="daring-duck")`, **Then** the message is routed to the "daring-duck" container specifically.
3. **Given** a chat targeting replica "daring-duck" but that replica is stopped, **When** the operator sends a message with `replica="daring-duck"`, **Then** the system returns an error indicating that replica is unavailable.

---

### User Story 4 - Config Propagation Across Replicas (Priority: P2)

An operator updates a function, changes the AI engine, or adds a schedule on a cluster. The change must propagate to all replicas without manual intervention.

**Why this priority**: Identical replicas are a core design constraint. If config drifts between replicas, the cluster model breaks.

**Independent Test**: Can be tested by updating a function on a 3-replica cluster and verifying all 3 replicas are running the updated code after a rolling restart.

**Acceptance Scenarios**:

1. **Given** a 3-replica cluster, **When** the operator updates a function via `update_function`, **Then** all replicas are restarted with the new function code via rolling restart (one at a time, maintaining availability).
2. **Given** a 3-replica cluster, **When** the operator calls `configure_ai` with a new model, **Then** all replicas restart with the new AI configuration.
3. **Given** a 3-replica cluster during a rolling restart, **When** one replica is restarting, **Then** the remaining replicas continue serving requests.

---

### User Story 5 - Webhook Distribution (Priority: P3)

External services send webhooks to the agent cluster. The platform distributes incoming webhooks to the first available replica rather than sending them to all replicas.

**Why this priority**: Webhooks are a common agent trigger, but they only need to be processed once. This is lower priority because agents can function without webhooks.

**Independent Test**: Can be tested by sending 10 webhooks to a 3-replica cluster in quick succession and verifying that each webhook is handled by exactly one replica, with work distributed across the pool.

**Acceptance Scenarios**:

1. **Given** a 3-replica cluster with a configured webhook, **When** an external service POSTs to the webhook URL, **Then** exactly one replica processes the webhook.
2. **Given** a 3-replica cluster receiving 10 webhooks in rapid succession, **When** all replicas are healthy, **Then** the webhooks are distributed across available replicas (not all sent to the same one).

---

### Edge Cases

- What happens when scaling down removes a replica that is mid-execution on a scheduled job? The system waits for in-progress jobs to complete before stopping the replica (graceful shutdown).
- What happens when all replicas in a cluster are stopped? Single-mode scheduled jobs accumulate as pending and execute when a replica starts. Cluster-mode jobs are skipped (no replicas to run them).
- What happens when two replicas attempt to claim the same single-mode job simultaneously? The database row lock ensures exactly one succeeds; the other skips the job.
- What happens when a replica crashes without heartbeating? After a configurable timeout (default 60 seconds), the system marks the replica as unhealthy. If the target replica count is not met, a replacement replica is started.
- What happens when `clone_agent` is called on a cluster with 5 replicas? The clone creates a new agent with 1 replica, copying the spec but not the replica count.
- What happens if a verb-animal name collision occurs? The generator retries with a new combination until a unique name within the cluster is found.
- What happens if the operator scales to 0 replicas? This is equivalent to `stop_agent` — the cluster spec is preserved but no containers run.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow scaling an agent to a specified number of replicas via a `scale_agent` tool with `name` and `replicas` parameters.
- **FR-002**: System MUST auto-generate a unique verb-animal name for each replica within a cluster (e.g., "daring-duck", "swift-falcon"), with a pool of at least 2,500 combinations.
- **FR-003**: System MUST enforce tier-based agent slot limits where each replica counts as one slot toward the total. Each replica receives the full tier resource allocation (RAM, CPU, state storage). There is no per-cluster replica cap — the tier slot limit is the only constraint.
- **FR-004**: System MUST support two schedule execution modes: `single` (exactly-once, default) and `cluster` (all replicas execute independently).
- **FR-005**: System MUST guarantee exactly-once execution for `single`-mode schedules even under concurrent replica contention.
- **FR-006**: System MUST route `chat_with_agent` requests to a specific replica when the optional `replica` parameter is provided, enabling session affinity for conversational continuity.
- **FR-007**: System MUST route `chat_with_agent` requests to any available replica when no `replica` parameter is specified, and include the handling replica's name in the response.
- **FR-008**: System MUST propagate all configuration changes (functions, AI engine, schedules, webhooks, channels, system prompt) to all replicas via rolling restart, maintaining at least one healthy replica throughout.
- **FR-009**: System MUST distribute incoming webhooks to the first available replica, ensuring each webhook is processed exactly once.
- **FR-010**: System MUST share the agent state (encrypted K/V store) across all replicas in a cluster, keyed by agent name rather than container.
- **FR-011**: System MUST inject `MCPWORKS_REPLICA_NAME` and `MCPWORKS_CLUSTER_SIZE` environment variables into each replica container.
- **FR-012**: System MUST support `start_agent` and `stop_agent` targeting either the entire cluster or a specific replica via an optional `replica` parameter.
- **FR-013**: System MUST perform graceful shutdown when scaling down — waiting for in-progress jobs to complete before stopping a replica. Scale-down MUST remove newest replicas first (LIFO) to preserve longest-running replicas and active chat sessions.
- **FR-014**: System MUST detect unhealthy replicas via heartbeat monitoring and start replacement replicas to maintain the target replica count.
- **FR-015**: `describe_agent` MUST return the cluster spec and a list of all replicas with their names, statuses, and last heartbeat times.
- **FR-016**: `clone_agent` MUST clone the agent spec into a new cluster with 1 replica, not preserving the source replica count.
- **FR-017**: `make_agent` MUST continue to work unchanged, creating a cluster with 1 auto-named replica (full backward compatibility).
- **FR-018**: System MUST NOT require any new infrastructure services — work distribution MUST use existing database and cache infrastructure only.

### Key Entities

- **Agent (Cluster Spec)**: The single source of truth for an agent's configuration — AI engine, model, system prompt, functions, schedules, webhooks, channels. Has a target replica count (default 1). Existing entity, extended with replica count.
- **Agent Replica**: A running container instance of an agent spec. Has a unique verb-animal name within its cluster, a container reference, a status (starting/running/stopped/error), and a last heartbeat timestamp. New entity.
- **Scheduled Job**: A record of a schedule firing event. For single-mode schedules, represents a claimable work item (exactly one replica executes it). For cluster-mode schedules, one record per replica. Tracks claim status, which replica executed it, and completion state. New entity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can scale an agent from 1 to 5 replicas and back to 1 within 60 seconds (excluding container image pull time).
- **SC-002**: Single-mode scheduled jobs execute exactly once across a cluster of any size — zero duplicate executions under concurrent contention.
- **SC-003**: Chat session affinity works correctly — a follow-up message routed to a named replica reaches the same container 100% of the time when that replica is healthy.
- **SC-004**: Configuration changes propagate to all replicas in a cluster without manual intervention, maintaining at least one healthy replica throughout the rolling restart.
- **SC-005**: Webhook distribution spreads work across available replicas — no single replica handles more than 60% of webhooks in a cluster of 3+ replicas under uniform load.
- **SC-006**: Existing single-replica agents continue to work identically with no behavior changes — full backward compatibility with all current MCP tools.
- **SC-007**: No new infrastructure services are added to the self-hosted Docker Compose file.
- **SC-008**: Unhealthy replicas are detected and replaced within 2 minutes of heartbeat failure.

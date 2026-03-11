# Feature Specification: MCPWorks Containerized Agents

**Feature Branch**: `003-containerized-agents`
**Created**: 2026-03-11
**Status**: Draft
**Input**: User description: "MCPWorks Agents - Containerized autonomous AI entities on top of the existing Functions platform"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create and Manage an Agent (Priority: P1)

A platform administrator upgrades an account to an agent-enabled tier, then the account owner uses their AI assistant (via MCP) to create a named agent. The agent provisions as a dedicated container with its own namespace, API keys, and resource limits. The owner can start, stop, and destroy the agent through MCP tools.

**Why this priority**: The agent container lifecycle is the foundation for all other agent capabilities. Without create/start/stop/destroy, nothing else works.

**Independent Test**: Can be fully tested by creating an agent via MCP, confirming the container is running, stopping it, restarting it, and destroying it. Delivers the core autonomous entity that all other features build on.

**Acceptance Scenarios**:

1. **Given** an account on a builder-agent tier with available agent slots, **When** the user requests agent creation with a name via MCP, **Then** a new agent is provisioned with a dedicated container, namespace, and API keys, and the agent status is "running".
2. **Given** a running agent, **When** the user requests the agent be stopped, **Then** the container stops and the agent status changes to "stopped".
3. **Given** a stopped agent, **When** the user requests the agent be started, **Then** the container resumes and the agent status changes to "running".
4. **Given** a running or stopped agent, **When** the user requests the agent be destroyed, **Then** the container is removed, the namespace and all associated data are deleted, and the agent slot is freed.
5. **Given** an account on the free tier, **When** the user attempts to create an agent, **Then** the system rejects the request and explains that an agent-enabled tier is required.
6. **Given** an account that has used all its agent slots, **When** the user attempts to create another agent, **Then** the system rejects the request and reports the slot limit.

---

### User Story 2 - Schedule Functions on an Agent (Priority: P2)

An account owner configures cron-based schedules on their agent so that specific functions execute automatically at defined intervals. The agent runs these functions on schedule and records each execution.

**Why this priority**: Scheduling is the primary value proposition of agents — autonomous, time-based execution without human intervention.

**Independent Test**: Can be tested by adding a schedule to an agent, waiting for the scheduled time, and confirming the function executed and the run was recorded.

**Acceptance Scenarios**:

1. **Given** a running agent with at least one function, **When** the user adds a cron schedule for that function, **Then** the schedule is persisted and the function executes at the specified times.
2. **Given** a builder-agent tier account, **When** the user attempts to add a schedule with an interval shorter than 5 minutes, **Then** the system rejects the schedule and reports the minimum interval for the tier.
3. **Given** a schedule on an agent, **When** the user removes the schedule, **Then** the function no longer executes on that schedule.
4. **Given** a scheduled function execution, **When** the execution completes (success or failure), **Then** an agent run record is created with trigger type, duration, and result summary.

---

### User Story 3 - Receive Webhooks on an Agent (Priority: P2)

An account owner registers webhook paths on their agent so that external systems can trigger function execution by sending HTTP requests to `{agent-name}.agent.mcpworks.io/webhook/{path}`.

**Why this priority**: Webhooks enable event-driven agents that respond to external triggers (price alerts, form submissions, notifications) — the second core trigger mechanism alongside scheduling.

**Independent Test**: Can be tested by registering a webhook path, sending an HTTP POST to the agent's webhook URL, and confirming the handler function executed and the run was recorded.

**Acceptance Scenarios**:

1. **Given** a running agent with a registered webhook path, **When** an external system sends an HTTP request to the webhook URL, **Then** the handler function executes with the webhook payload and an agent run record is created.
2. **Given** a webhook with a configured secret, **When** a request arrives without a valid secret, **Then** the request is rejected.
3. **Given** an agent name that does not exist, **When** a request arrives at `{name}.agent.mcpworks.io`, **Then** the system returns a not-found response.
4. **Given** a stopped agent, **When** a webhook request arrives, **Then** the system returns an appropriate error indicating the agent is not running.

---

### User Story 4 - Persist State Across Runs (Priority: P3)

Functions running inside an agent's namespace can store and retrieve key-value state that persists between executions. State is encrypted at rest and subject to tier-based size limits.

**Why this priority**: Persistent state enables agents to remember context across runs (last-seen price, conversation history, accumulated data), making them genuinely autonomous rather than stateless.

**Independent Test**: Can be tested by having a function write a value to state, then having a subsequent function read it back and confirm the value persists.

**Acceptance Scenarios**:

1. **Given** a running agent, **When** a function sets a key-value pair in state, **Then** the value is encrypted and persisted, and a subsequent function can read it back.
2. **Given** an agent approaching its tier's state storage limit, **When** a function attempts to store a value that would exceed the limit, **Then** the write is rejected with a clear error about the storage limit.
3. **Given** an agent with stored state, **When** the agent is destroyed, **Then** all state data is permanently deleted.
4. **Given** an agent with stored state, **When** the user lists state keys or gets a specific value via MCP tools, **Then** the current keys and values are returned.

---

### User Story 5 - Lock Functions Against Modification (Priority: P3)

An account owner locks critical functions in an agent's namespace so that only admin-scoped API keys can modify or delete them. The agent's own API key (write+execute scope) cannot alter locked functions.

**Why this priority**: Function locking prevents agents (or their AI engines) from accidentally modifying their own critical code, providing a safety net for production autonomy.

**Independent Test**: Can be tested by locking a function, attempting to modify it with the agent's API key (should fail), and then modifying it with the admin API key (should succeed).

**Acceptance Scenarios**:

1. **Given** an unlocked function, **When** an admin locks it, **Then** modification and deletion attempts using non-admin API keys are rejected.
2. **Given** a locked function, **When** an admin unlocks it, **Then** modification resumes as normal for all authorized API keys.
3. **Given** a locked function, **When** the agent's runtime attempts to execute (not modify) it, **Then** execution proceeds normally — locking only restricts modification.

---

### User Story 6 - Clone an Agent (Priority: P3)

An account owner clones an existing agent to create an independent copy with the same functions, state, schedules, and configuration but a new name and namespace.

**Why this priority**: Cloning enables rapid scaling of proven agent configurations without manual re-setup.

**Independent Test**: Can be tested by cloning an agent and verifying the new agent has copies of all functions, state, and schedules (schedules disabled by default), and that modifications to the clone do not affect the original.

**Acceptance Scenarios**:

1. **Given** a running agent, **When** the user clones it with a new name, **Then** a new independent agent is created with copies of all functions, state, and schedules, and the clone's schedules are disabled by default.
2. **Given** a cloned agent, **When** the user modifies the clone, **Then** the original agent is unaffected.
3. **Given** an account with no remaining agent slots, **When** the user attempts to clone an agent, **Then** the request is rejected due to slot limits.

---

### User Story 7 - Configure AI Engine and Communication Channels (Priority: P4)

An account owner configures an AI engine (BYOAI — bring your own AI) on their agent so the agent can reason autonomously. The owner also configures communication channels (Discord, Slack, etc.) so the agent can send outbound messages.

**Why this priority**: AI engine and communication channels are the advanced autonomy layer. They depend on all previous capabilities being functional.

**Independent Test**: Can be tested by configuring an AI engine and a Discord channel, triggering the agent via webhook, and confirming the agent reasons about the input and sends a message to Discord.

**Acceptance Scenarios**:

1. **Given** a running agent, **When** the user configures an AI engine with a provider, model, and API key, **Then** the AI configuration is encrypted and stored, and the agent can use it for autonomous reasoning.
2. **Given** an agent with a configured AI engine, **When** a trigger fires, **Then** the agent can use the AI to reason about the trigger and decide which functions to call.
3. **Given** a running agent, **When** the user adds a Discord communication channel, **Then** the agent can send messages to the configured Discord target.
4. **Given** an agent with a communication channel, **When** the user removes the channel, **Then** the agent can no longer send messages through that channel.

---

### User Story 8 - Admin Fleet Management (Priority: P2)

Platform administrators can view all agents across the platform, monitor their health, force-restart or force-destroy agents, and upgrade accounts to agent tiers.

**Why this priority**: Admin tooling is essential for platform operations — the team needs visibility and control over the agent fleet from day one.

**Independent Test**: Can be tested by an admin listing all agents, viewing container health, force-restarting an agent, and upgrading an account tier.

**Acceptance Scenarios**:

1. **Given** an admin user, **When** they request the platform-wide agent list, **Then** all agents are returned with their status, account, and resource usage.
2. **Given** a running agent in an error state, **When** an admin force-restarts it, **Then** the container is stopped and restarted, and the agent status reflects the restart.
3. **Given** an admin user, **When** they upgrade an account to an agent tier, **Then** the account's subscription is updated, agent slots are provisioned, and an audit log entry is created.
4. **Given** an admin user, **When** they request the agent health overview, **Then** the system reports the health status of all running agent containers.

---

### Edge Cases

- When a container fails to start due to resource exhaustion on the host, the agent status is set to "error" with a descriptive message including available capacity. The system logs a structlog alert. The admin health endpoint reports the capacity shortage.
- When an agent's scheduled function fails repeatedly, the system applies the failure policy chosen at schedule creation (continue, auto-disable after N, backoff, or combination). No implicit behavior.
- When multiple webhooks arrive simultaneously for the same agent, each webhook is processed concurrently (standard async behavior). Each execution creates its own independent AgentRun record.
- When the host is restarted, agent containers automatically recover via Docker's "unless-stopped" restart policy (FR-019).
- When a user attempts to downgrade from an agent tier while agents exist, the downgrade is blocked. All agents must be destroyed before the tier can be changed.
- When an agent's AI API key becomes invalid or rate-limited, the agent runtime logs the error, records a failed AgentRun, and does not retry the AI call. The user must update the key via the `configure_agent_ai` MCP tool.
- When a cloned agent's source is destroyed after cloning, the clone is unaffected — clones are fully independent from the moment of creation.
- Key rotation (re-encrypting DEKs with a new KEK) is deferred to post-MVP. When needed, it will be an offline batch job that re-wraps all DEKs with the new KEK without decrypting the underlying data.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support three new subscription tiers (builder-agent, pro-agent, enterprise-agent) as internal-only SKUs not exposed on public pricing pages.
- **FR-002**: System MUST enforce agent slot limits per tier: 1 (builder-agent), 5 (pro-agent), 20 (enterprise-agent).
- **FR-003**: System MUST enforce per-agent container resource limits: memory and CPU allocation matching the tier specification.
- **FR-004**: System MUST manage agent container lifecycle (create, start, stop, destroy) through a container runtime, with each agent running as an isolated container.
- **FR-005**: System MUST assign each agent a dedicated namespace with write+execute scoped API keys that cannot access other namespaces.
- **FR-006**: System MUST record all agent executions (runs) with trigger type, function name, duration, status, and PII-scrubbed result summary. Run records MUST be auto-purged based on tier retention: 7 days (builder), 30 days (pro), 90 days (enterprise).
- **FR-007**: System MUST support cron-based scheduling with tier-enforced minimum intervals: 5 min (builder), 30 sec (pro), 15 sec (enterprise). Each schedule MUST require an explicit failure policy at creation time (e.g., continue, auto-disable after N failures, exponential backoff). The system MUST NOT accept a schedule without a failure policy.
- **FR-008**: System MUST route incoming webhook requests from `{name}.agent.mcpworks.io/webhook/{path}` to the correct agent and handler function. Webhook payloads MUST be rejected if they exceed the tier-based size limit: 256 KB (builder), 1 MB (pro), 5 MB (enterprise).
- **FR-009**: System MUST provide encrypted persistent key-value state storage per agent, with tier-based size limits: 10 MB (builder), 100 MB (pro), 1 GB (enterprise).
- **FR-010**: System MUST support function locking where locked functions can only be modified by admin-scoped API keys.
- **FR-011**: System MUST support agent cloning that copies functions, state, schedules (disabled), channel configurations, and AI configuration to a new independent agent.
- **FR-012**: System MUST support BYOAI configuration where the user provides an AI provider, model, and API key, all encrypted at rest with envelope encryption.
- **FR-013**: System MUST support communication channel configuration (Discord, Slack, WhatsApp, email) with encrypted credentials.
- **FR-014**: System MUST provide admin endpoints for tier upgrades, platform-wide agent listing, force-restart, force-destroy, and health monitoring.
- **FR-015**: System MUST ensure agent containers are network-isolated from infrastructure services (database, cache) while allowing access to the platform API and the internet.
- **FR-016**: System MUST expose 18 MCP tools for agent management, only visible to users on agent-enabled tiers.
- **FR-017**: System MUST map agent tiers to their corresponding functions tier for all existing billing, rate-limiting, and execution-counting logic.
- **FR-021**: System MUST block tier downgrades from agent tiers while any agents exist on the account. All agents must be destroyed before a non-agent tier can be applied.
- **FR-018**: System MUST validate webhook secrets when configured, rejecting requests with invalid or missing secrets. Webhook secret verification is optional per webhook path — paths without a secret accept all requests.
- **FR-019**: System MUST automatically recover agent containers after host restarts (restart policy: unless-stopped).

### Key Entities

- **Agent**: A named, containerized autonomous entity belonging to an account. Has a lifecycle (creating, running, stopped, error, destroying), resource limits, optional AI engine configuration, and belongs to a namespace.
- **AgentSchedule**: A cron-based trigger that causes a specific function to execute at defined intervals within an agent. Subject to tier minimum interval enforcement. Includes a required failure policy that governs behavior on repeated execution failures.
- **AgentWebhook**: A registered HTTP path on an agent that maps incoming webhook requests to a handler function. Optionally protected by a shared secret. Incoming payloads subject to tier-based size limits (256 KB / 1 MB / 5 MB).
- **AgentRun**: An execution record capturing each time an agent runs a function, including trigger type (cron, webhook, manual, AI), duration, status, and result. Subject to tier-based retention (7/30/90 days) with automatic purging.
- **AgentState**: An encrypted key-value pair belonging to an agent, used for persisting data between function executions. Subject to tier-based total size limits.
- **AgentChannel**: A configured communication channel (Discord, Slack, WhatsApp, email) enabling an agent to send and receive messages. Credentials encrypted at rest.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An agent can be created, started, stopped, and destroyed within 30 seconds for each lifecycle operation.
- **SC-002**: Scheduled functions execute within 5 seconds of their scheduled time under normal load.
- **SC-003**: Webhook-triggered functions begin execution within 2 seconds of the webhook request arriving.
- **SC-004**: State read/write operations complete within 500 milliseconds per operation.
- **SC-005**: The platform supports at least 20 concurrent running agents on the target infrastructure without degradation.
- **SC-006**: Agent cloning completes within 60 seconds including function copying and state duplication.
- **SC-007**: All sensitive data (AI API keys, state values, channel credentials) is encrypted at rest — no plaintext secrets in the database.
- **SC-008**: Agent containers cannot access infrastructure services (database, cache) — network isolation is verified.
- **SC-009**: Admin health check reports accurate status for 100% of running agent containers.
- **SC-010**: Agent tier MCP tools are invisible to users on non-agent tiers — tool discovery correctly filters by tier.

## Clarifications

### Session 2026-03-11

- Q: What happens when an agent's scheduled function fails repeatedly? → A: Failure policy is a required configuration at schedule creation time. The user/LLM must choose a failure strategy (e.g., continue indefinitely, auto-disable after N failures, exponential backoff, or a combination) before the schedule is accepted. No implicit default — the platform forces an explicit decision.
- Q: What happens when a user downgrades from an agent tier while agents exist? → A: Downgrade is blocked while any agents exist. Admin must destroy all agents before the tier can be changed to a non-agent tier.
- Q: How long are AgentRun records retained? → A: Tier-based retention: 7 days (builder), 30 days (pro), 90 days (enterprise). Records older than the retention period are auto-purged.
- Q: What is the maximum webhook payload size? → A: Tier-based: 256 KB (builder), 1 MB (pro), 5 MB (enterprise). Payloads exceeding the limit are rejected.

## Assumptions

- The existing Functions platform (namespaces, functions, execution, billing) is stable and does not require modification for basic agent support.
- Agent tier upgrades are admin-only during the pre-commercialization phase; no self-service upgrade flow is needed.
- The current production droplet will be upgraded from s-2vcpu-4gb to s-4vcpu-8gb to accommodate agent containers.
- Cloudflare wildcard DNS already covers `*.mcpworks.io`, so `*.agent.mcpworks.io` routing requires only Caddy configuration.
- Docker SDK for Python is the container management interface; no Docker Compose or CLI subprocess calls.
- APScheduler runs inside each agent container, not centrally — schedules are database-sourced and loaded at container startup.
- Envelope encryption (AES-256-GCM) will be implemented as a new `core/encryption.py` module — no prior encryption-at-rest pattern exists in the codebase.
- Inter-agent communication is not supported — agents interact only through the platform API.

## Scope Boundaries

**In scope:**
- Subscription tier extension (3 agent tiers + add-on pricing model)
- Agent data models and database migrations
- Container lifecycle management via Docker SDK
- Docker bridge network for agent containers
- Caddy routing for `*.agent.mcpworks.io`
- Cron scheduling via APScheduler
- Webhook ingress routing and secret verification
- Encrypted persistent state (key-value store)
- Function locking
- Agent cloning
- AI engine configuration (BYOAI)
- Communication channels (Discord, Slack, WhatsApp, email)
- Admin fleet management endpoints
- 18 MCP tools for agent management
- Agent runtime base image

**Out of scope:**
- Public pricing page or self-service tier upgrades
- Customer onboarding flows for agents
- Multi-node scaling (Docker Swarm) — single droplet only for Phase 1
- Agent marketplace or sharing between accounts
- Billing for agent add-ons (Stripe product creation deferred until commercialization)
- Agent-to-agent direct communication
- Custom agent container images (all agents use the standard runtime image)

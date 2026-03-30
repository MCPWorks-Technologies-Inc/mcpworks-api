# MCPWorks Agents — Engineering Specification

**Version:** 1.0.0
**Date:** 2026-03-11
**Status:** Pre-implementation (Board-approved design)
**Audience:** Lead engineers, technical co-founders, senior backend developers
**Parent:** PRODUCT-SPEC.md (product-level specification)

---

## Scope

This document specifies the technical implementation of MCPWorks Agents on top of the existing MCPWorks Functions platform. It covers: subscription tier changes, data models, container lifecycle, networking, scheduling, state management, function locking, admin tooling, and phased build order.

It does not cover: public-facing marketing, pricing page updates, or customer onboarding flows. Agent tiers are internal-only until investment closes and commercialization begins.

---

## 1. Subscription Tier Extension

### New Internal SKUs

The existing `SubscriptionTier` enum gains three agent-enabled tiers. These are **internal-only** — not exposed on any public pricing page, product page, or self-service upgrade flow.

```python
class SubscriptionTier(str, Enum):
    FREE = "free"
    BUILDER = "builder"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    BUILDER_AGENT = "builder-agent"
    PRO_AGENT = "pro-agent"
    ENTERPRISE_AGENT = "enterprise-agent"
```

The `UserTier` enum in `models/user.py` must mirror these additions.

### Tier Mapping

| SKU | Monthly | Agents | Agent RAM | Agent CPU | Min Schedule | State Storage | Functions Tier |
|-----|---------|--------|-----------|-----------|-------------|---------------|----------------|
| `builder-agent` | $29 | 1 | 256 MB | 0.25 vCPU | 5 min | 10 MB | Full Builder |
| `pro-agent` | $179 | 5 | 512 MB | 0.5 vCPU | 30 sec | 100 MB | Full Pro |
| `enterprise-agent` | $599 | 20 (included) | 1 GB | 1.0 vCPU | 15 sec | 1 GB | Full Enterprise |

Agent add-ons (additional agents beyond tier allocation):

| Add-on | Price | Container Spec |
|--------|-------|---------------|
| Builder agent | $9/mo | 256 MB / 0.25 vCPU |
| Pro agent | $19/mo | 512 MB / 0.5 vCPU |
| Enterprise agent (standard) | $29/mo | 1 GB / 1.0 vCPU |
| Enterprise agent (heavy) | $49/mo | 2 GB / 2.0 vCPU |

### Functions Access

Agent tiers include full access to the corresponding Functions tier. The `effective_tier` property must resolve agent tiers to their Functions equivalent for all existing billing, rate-limiting, and execution-counting logic:

```python
@property
def functions_tier(self) -> str:
    mapping = {
        "builder-agent": "builder",
        "pro-agent": "pro",
        "enterprise-agent": "enterprise",
    }
    return mapping.get(self.value, self.value)
```

### Files Requiring Changes

| File | Change |
|------|--------|
| `models/subscription.py` | Add 3 agent tiers to `SubscriptionTier`, update `monthly_executions` |
| `models/user.py` | Add 3 agent tiers to `UserTier` |
| `middleware/billing.py` | Map agent tiers → Functions tier in `TIER_LIMITS` |
| `services/stripe_service.py` | Create Stripe products/prices for agent SKUs |
| `api/v1/admin.py` | Add endpoint to upgrade accounts to agent tiers |
| `api/v1/subscriptions.py` | Accept agent tiers in admin-only upgrade path |
| `schemas/subscription.py` | Add agent tiers to validation schemas |

### Admin-Only Upgrade

Agent tier upgrades are performed exclusively through the admin interface. No self-service flow exists until commercialization.

```
POST /api/v1/admin/accounts/{account_id}/upgrade
{
    "tier": "pro-agent",
    "billing_period": "monthly"  // or "annual"
}
```

This endpoint:
1. Creates/updates the Stripe subscription with the agent SKU price
2. Updates the user's `effective_tier` to the agent tier
3. Provisions agent slots (see Section 3)
4. Emits an audit log entry

---

## 2. Data Models

### Agent

```sql
CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES accounts(id),
    namespace_id UUID NOT NULL REFERENCES namespaces(id),
    name VARCHAR(63) NOT NULL,
    display_name VARCHAR(255),
    container_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'stopped',
    -- AI engine (optional, for autonomous mode)
    ai_engine VARCHAR(50),           -- 'anthropic', 'openai', 'google', 'openrouter', etc.
    ai_model VARCHAR(100),           -- 'claude-haiku-4-5-20251001', 'gpt-4o-mini', etc.
    ai_api_key_encrypted BYTEA,
    ai_api_key_dek_encrypted BYTEA,
    -- Container resources
    memory_limit_mb INTEGER NOT NULL DEFAULT 256,
    cpu_limit FLOAT NOT NULL DEFAULT 0.25,
    -- Metadata
    system_prompt TEXT,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cloned_from_id UUID REFERENCES agents(id),

    UNIQUE(account_id, name)
);
```

Agent `status` values: `creating`, `running`, `stopped`, `error`, `destroying`.

### AgentSchedule

```sql
CREATE TABLE agent_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    function_name VARCHAR(255) NOT NULL,
    cron_expression VARCHAR(255) NOT NULL,
    timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
    enabled BOOLEAN NOT NULL DEFAULT true,
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### AgentWebhook

```sql
CREATE TABLE agent_webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    path VARCHAR(255) NOT NULL,
    handler_function_name VARCHAR(255) NOT NULL,
    secret_hash VARCHAR(255),          -- optional webhook secret for verification
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(agent_id, path)
);
```

### AgentRun

```sql
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    trigger_type VARCHAR(20) NOT NULL,   -- 'cron', 'webhook', 'manual', 'ai'
    trigger_detail VARCHAR(255),         -- cron expression or webhook path
    function_name VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    result_summary TEXT,                 -- PII-scrubbed
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### AgentState

```sql
CREATE TABLE agent_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    key VARCHAR(255) NOT NULL,
    value_encrypted BYTEA NOT NULL,
    value_dek_encrypted BYTEA NOT NULL,
    size_bytes INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(agent_id, key)
);
```

State storage is enforced per tier. Total `size_bytes` across all keys for an agent must not exceed the tier limit.

### AgentChannel

```sql
CREATE TABLE agent_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    channel_type VARCHAR(20) NOT NULL,   -- 'discord', 'slack', 'whatsapp', 'email'
    config_encrypted BYTEA NOT NULL,
    config_dek_encrypted BYTEA NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(agent_id, channel_type)
);
```

### SQLAlchemy Models

All models follow the existing project pattern: SQLAlchemy 2.0 declarative base, `Mapped[]` type annotations, `mapped_column()`. Place new models in `src/mcpworks_api/models/agent.py` (single file for all agent-related models). Register in `models/__init__.py`.

---

## 3. Container Lifecycle

### Technology: Docker SDK for Python

Use `docker` (Python SDK) for all container operations. No `docker-compose` files, no subprocess calls to `docker` CLI.

```
pip install docker
```

### Agent Container Image

A single base image: `mcpworks/agent-runtime:latest`

Contents:
- Python 3.11 slim base
- `httpx`, `apscheduler`, `fastapi`, `uvicorn` (webhook listener)
- `anthropic`, `openai`, `google-generativeai` (AI SDKs)
- `discord.py` (communication)
- MCPWorks agent runtime (entrypoint script)

The agent runtime entrypoint:
1. Starts a FastAPI server on an internal port (webhook listener)
2. Loads schedules from the platform API and configures APScheduler
3. Connects to configured communication channels
4. If AI engine is configured, initializes the LLM client
5. Enters the event loop

### Container Create Flow

```
make_agent(name, account_id)
    │
    ├── Validate: account has available agent slots
    ├── Create namespace: {name}.create / {name}.run
    ├── Generate API keys for agent namespace (write+execute scope)
    ├── INSERT into agents table (status='creating')
    │
    ├── docker.from_env().containers.run(
    │       image='mcpworks/agent-runtime:latest',
    │       name=f'agent-{agent_id}',
    │       detach=True,
    │       mem_limit=f'{memory_limit_mb}m',
    │       nano_cpus=int(cpu_limit * 1e9),
    │       network='mcpworks-agents',
    │       environment={
    │           'AGENT_ID': str(agent_id),
    │           'AGENT_NAME': name,
    │           'MCPWORKS_API_URL': 'http://mcpworks-api:8000',
    │           'MCPWORKS_API_KEY': agent_api_key,
    │           'MCPWORKS_NAMESPACE': name,
    │       },
    │       restart_policy={'Name': 'unless-stopped'},
    │       labels={
    │           'mcpworks.agent_id': str(agent_id),
    │           'mcpworks.account_id': str(account_id),
    │           'mcpworks.tier': tier,
    │       },
    │   )
    │
    ├── UPDATE agents SET container_id=..., status='running'
    └── Return agent object
```

### Container Stop / Start / Destroy

```python
# Stop
container = client.containers.get(agent.container_id)
container.stop(timeout=10)
agent.status = 'stopped'

# Start
container.start()
agent.status = 'running'

# Destroy
container.stop(timeout=10)
container.remove(v=True)
# Delete namespace, schedules, webhooks, state, channels
# DELETE FROM agents WHERE id = agent_id
```

### Service Layer

Create `src/mcpworks_api/services/agent_service.py`:

```python
class AgentService:
    async def create_agent(self, account_id, name, ...) -> Agent
    async def start_agent(self, agent_id) -> Agent
    async def stop_agent(self, agent_id) -> Agent
    async def destroy_agent(self, agent_id) -> None
    async def clone_agent(self, agent_id, new_name) -> Agent
    async def get_agent(self, agent_id) -> Agent
    async def list_agents(self, account_id) -> list[Agent]
    async def configure_ai(self, agent_id, engine, model, api_key) -> Agent
    async def get_agent_slots(self, account_id) -> dict  # used, available, max
```

---

## 4. Networking

### DNS

With path-based routing, all traffic goes through `api.mcpworks.io`. No additional DNS records needed for agents.

### Caddy Routing

All agent traffic is handled via path-based routing through the main `api.mcpworks.io` block. Agent endpoints:
- `/mcp/agent/{name}` — MCP protocol
- `/mcp/agent/{name}/webhook/{path}` — webhook ingress
- `/mcp/agent/{name}/chat/{token}` — public chat
- `/mcp/agent/{name}/view/{token}/` — scratchpad view

The API server's `PathRoutingMiddleware` extracts the agent name from the URL path and routes to the appropriate handler.

### Webhook Ingress Path

```
External system
    │
    │ POST https://api.mcpworks.io/mcp/agent/dogedetective/webhook/price-alert
    │
    ├── Cloudflare (DDoS, TLS termination)
    ├── Caddy (TLS, reverse proxy)
    ├── MCPWorks API server
    │   ├── Extract agent name from Host header
    │   ├── Look up agent + webhook path in database
    │   ├── Validate webhook secret (if configured)
    │   ├── Forward to agent container via Docker network
    │   └── Record AgentRun
    └── Agent container processes webhook
```

### Docker Network

```python
docker_client.networks.create(
    'mcpworks-agents',
    driver='bridge',
    internal=False,  # agents need outbound internet
)
```

The API server container and all agent containers share this network. Agent containers can reach the API via `http://mcpworks-api:8000`. Agent containers can reach the internet for external API calls.

---

## 5. Scheduling (APScheduler)

### Architecture Decision

Schedules are stored in the database (source of truth) and loaded into APScheduler inside each agent container at startup. The agent runtime polls for schedule changes periodically (every 60 seconds) or receives push notifications from the API.

### Agent Runtime Scheduler

Inside the agent container:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

async def execute_scheduled_function(schedule_id: str, function_name: str):
    # Call /mcp/run/{namespace} to execute the function
    # Record AgentRun
    pass

# Load schedules from API
for schedule in await fetch_schedules():
    scheduler.add_job(
        execute_scheduled_function,
        CronTrigger.from_crontab(schedule['cron_expression'],
                                  timezone=schedule['timezone']),
        args=[schedule['id'], schedule['function_name']],
        id=schedule['id'],
    )

scheduler.start()
```

### Minimum Schedule Enforcement

The API validates cron expressions against the tier's minimum schedule interval before persisting:

| Tier | Min Interval |
|------|-------------|
| Builder | 5 minutes |
| Pro | 30 seconds |
| Enterprise | 15 seconds |

---

## 6. Persistent State

### Access Pattern

Agent state is a key-value store accessible to functions running in the agent's namespace. Functions access state via a platform-provided SDK function injected into the sandbox environment:

```python
# Inside a sandboxed function:
from mcpworks import state

# Read
value = state.get("last_price")

# Write
state.set("last_price", 42150.50)

# Delete
state.delete("last_price")

# List keys
keys = state.keys()
```

Under the hood, these calls hit the MCPWorks API with the agent's API key:

```
GET  /api/v1/agents/{agent_id}/state/{key}
PUT  /api/v1/agents/{agent_id}/state/{key}
DELETE /api/v1/agents/{agent_id}/state/{key}
GET  /api/v1/agents/{agent_id}/state
```

### Encryption

All state values are encrypted at rest using envelope encryption (AES-256-GCM), consistent with the existing secrets pattern. The DEK is per-agent.

### Size Enforcement

On every `PUT`, the API calculates total state size for the agent. If adding the new value would exceed the tier limit, return `413 Payload Too Large`.

---

## 7. Function Locking

### Implementation

Add a `locked` boolean column to the `functions` table (already in PRODUCT-SPEC.md data model):

```sql
ALTER TABLE functions ADD COLUMN locked BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE functions ADD COLUMN locked_by UUID REFERENCES users(id);
ALTER TABLE functions ADD COLUMN locked_at TIMESTAMPTZ;
```

### Auth Middleware Check

In the create endpoint handler, before any function modification (update, delete):

```python
if function.locked and request_api_key.scope != 'admin':
    raise HTTPException(403, "Function is locked. Only admin can modify locked functions.")
```

Agent API keys are scoped to `write+execute`. Admin API keys (user's own) have `admin` scope. Two lines of logic in the existing auth flow.

### Lock/Unlock Endpoints

```
POST   /api/v1/namespaces/{ns}/functions/{fn}/lock     # admin only
DELETE /api/v1/namespaces/{ns}/functions/{fn}/lock     # admin only
```

---

## 8. Agent MCP Tools

The existing MCP create_handler gains new tools for agent management. These tools are available to the user's primary AI (Claude, Copilot, etc.) via the standard MCP protocol.

### Tool List

| Tool | Description |
|------|------------|
| `make_agent` | Create a new agent with name and optional config |
| `list_agents` | List all agents for the account |
| `describe_agent` | Get full agent details including status, schedules, channels |
| `start_agent` | Start a stopped agent |
| `stop_agent` | Stop a running agent |
| `destroy_agent` | Permanently destroy an agent and its namespace |
| `clone_agent` | Clone an existing agent to a new instance |
| `configure_agent_ai` | Set/update the agent's AI engine, model, and API key |
| `add_schedule` | Add a cron schedule to an agent |
| `remove_schedule` | Remove a cron schedule |
| `add_webhook` | Register a webhook path with a handler function |
| `remove_webhook` | Remove a webhook registration |
| `set_agent_state` | Set a key-value pair in agent state |
| `get_agent_state` | Get a value from agent state |
| `add_channel` | Configure a communication channel (Discord, Slack, etc.) |
| `remove_channel` | Remove a communication channel |
| `lock_function` | Lock a function in the agent's namespace |
| `unlock_function` | Unlock a function |

These tools are only available to users on agent tiers. The tool discovery response filters based on `effective_tier`.

---

## 9. Agent Cloning

### Flow

```
clone_agent(source_agent_id, new_name)
    │
    ├── Validate: account has available agent slots
    ├── Create new agent record (cloned_from_id = source)
    ├── Create new namespace
    ├── Copy all functions from source namespace to new namespace
    ├── Copy state snapshot (all key-value pairs)
    ├── Copy schedules (disabled by default)
    ├── Copy channel configurations
    ├── Copy AI engine configuration
    ├── Do NOT copy: webhook secrets, container_id
    ├── Create and start new container
    └── Return new agent
```

Cloned schedules start disabled so the user can review before activating. The clone is independent from that point forward.

---

## 10. Admin Interface Changes

### New Admin Endpoints

```
POST   /api/v1/admin/accounts/{id}/upgrade        # Upgrade to agent tier
GET    /api/v1/admin/agents                        # List all agents (platform-wide)
GET    /api/v1/admin/agents/{id}                   # Agent details with container status
POST   /api/v1/admin/agents/{id}/restart           # Force restart agent container
DELETE /api/v1/admin/agents/{id}                   # Force destroy agent
GET    /api/v1/admin/agents/health                 # Health check all running agents
```

### Admin Dashboard Additions

The existing admin dashboard (if web-based) or admin API needs:

1. Account detail view showing current tier + agent count + agent list
2. Tier upgrade action (dropdown: `builder-agent`, `pro-agent`, `enterprise-agent`)
3. Agent fleet overview: all running agents, resource usage, error rates
4. Container health monitoring: status, uptime, restart count, memory usage

---

## 11. Infrastructure

### Current → Required

| Component | Current | Required |
|-----------|---------|----------|
| Droplet | s-2vcpu-4gb ($24/mo) | s-4vcpu-8gb ($48/mo) |
| Docker | Running API + Caddy | + agent containers |
| Network | Single bridge | + `mcpworks-agents` bridge |
| DNS | `api.mcpworks.io` A record | Path-based routing — no wildcard DNS needed |

### Resource Budget (s-4vcpu-8gb = 8 GB RAM, 4 vCPU)

| Component | RAM | CPU |
|-----------|-----|-----|
| API server | 512 MB | 0.5 vCPU |
| Caddy | 128 MB | 0.1 vCPU |
| OS + overhead | 512 MB | 0.2 vCPU |
| Available for agents | ~6.8 GB | ~3.2 vCPU |

At Builder spec (256 MB each): ~26 agents max
At Pro spec (512 MB each): ~13 agents max
At Enterprise spec (1 GB each): ~6 agents max

### Scaling Path

1. **Phase 1 (MVP):** Single droplet, all containers co-located
2. **Phase 2 (10+ agents):** Dedicated agent droplet(s), API stays on current droplet
3. **Phase 3 (50+ agents):** Docker Swarm across multiple nodes. No Kubernetes.

---

## 12. Security Considerations

### Container Isolation

- Agent containers run as non-root user inside the container
- `--read-only` root filesystem where possible (writable tmpfs for `/tmp`)
- No `--privileged` flag
- Drop all capabilities except `NET_BIND_SERVICE`
- Resource limits enforced via Docker (mem_limit, nano_cpus)
- No access to Docker socket

### Agent API Key Scope

- Agent containers receive a `write+execute` scoped API key for their own namespace only
- They cannot access other namespaces, other agents, or admin endpoints
- The user retains `admin` scope over the agent's namespace

### Secrets at Rest

- AI API keys: AES-256-GCM envelope encryption (per-agent DEK)
- State values: AES-256-GCM envelope encryption (per-agent DEK)
- Channel configs: AES-256-GCM envelope encryption (per-agent DEK)
- DEKs encrypted with platform KEK, stored separately

### Network Isolation

- Agent containers on `mcpworks-agents` bridge network
- Agents can reach: the API server, the internet (for external APIs)
- Agents cannot reach: the database, Redis, other infrastructure containers
- Inter-agent communication is not permitted (agents talk via the API only)

---

## 13. Phased Build Order

### Phase A: Agent Shell (Week 1-2)

Deliverables:
- Agent SQLAlchemy models + Alembic migrations
- `AgentService` with create/start/stop/destroy/list/get
- Docker SDK integration for container lifecycle
- Agent runtime base image (entrypoint + FastAPI webhook listener)
- Admin endpoint for agent tier upgrades
- Subscription tier enum extension (3 new agent tiers)
- Basic MCP tools: `make_agent`, `list_agents`, `describe_agent`, `start_agent`, `stop_agent`, `destroy_agent`

Exit criteria: Can create an agent via MCP, see its container running, stop/start/destroy it.

### Phase B: Webhooks + Scheduling (Week 3)

Deliverables:
- AgentSchedule + AgentWebhook models + migrations
- APScheduler integration in agent runtime
- Webhook ingress routing (Caddy config + API forwarding)
- AgentRun recording
- MCP tools: `add_schedule`, `remove_schedule`, `add_webhook`, `remove_webhook`
- Minimum schedule interval enforcement per tier

Exit criteria: Agent executes a function on a cron schedule. External webhook triggers a function execution. Runs are recorded.

### Phase C: State + Locking + Cloning (Week 4)

Deliverables:
- AgentState model + migrations + encrypted storage
- State API endpoints + sandbox SDK integration
- Function locking (column + auth middleware check)
- Agent cloning flow
- MCP tools: `set_agent_state`, `get_agent_state`, `lock_function`, `unlock_function`, `clone_agent`
- Size enforcement per tier

Exit criteria: Agent functions can persist state between runs. Functions can be locked. An agent can be cloned.

### Phase D: AI Engine + Communication (Week 5)

Deliverables:
- AI engine configuration (BYOAI)
- AgentChannel model + migrations
- Discord integration (outbound messages + bidirectional)
- `configure_agent_ai` MCP tool
- `add_channel`, `remove_channel` MCP tools
- Agent autonomous mode: AI can reason and call functions

Exit criteria: Agent with AI engine can receive a webhook, reason about it, execute functions, and send a Discord message with results.

---

## 14. Testing Strategy

### Unit Tests
- Agent service methods (mock Docker SDK)
- Tier validation and slot counting
- State size enforcement
- Cron expression validation
- Function lock checks

### Integration Tests
- Container lifecycle (create → start → stop → destroy)
- Webhook ingress end-to-end
- Schedule execution
- State read/write through sandbox SDK
- Agent cloning

### Staging Environment
- Before any agent runs on production, deploy to a staging droplet
- Test with real Docker containers, real APScheduler, real webhook delivery

---

## Changelog

**v1.0.0 (2026-03-11):** Initial engineering specification. Derived from Board Session 2026-03-11 decisions, PRODUCT-SPEC.md v3.0.0 agent design, and CTO architecture assessment. Covers subscription tiers, data models, container lifecycle, networking, scheduling, state, locking, admin tooling, and 4-phase build order.

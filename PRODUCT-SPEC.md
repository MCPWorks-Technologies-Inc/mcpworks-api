# MCPWorks Product Specification

**Version:** 3.3.0
**Date:** 2026-03-12
**Status:** Developer Preview (A0) / Agents: Invite-Only Preview
**Author:** Simon Carr / Claude

---

## What This Document Is

A high-level product specification for MCPWorks as it exists today and where it's headed. This is not an API spec (see SPEC.md) or an architecture doc. This describes the product: what it does, who it's for, how it works, and what's built vs. planned.

---

## Product Summary

MCPWorks is two products on one platform:

**MCPWorks Functions** is namespace-based function hosting for AI assistants. Any agentic system can create and execute Python functions via MCP over HTTPS. Functions are the execution substrate. This is live in Developer Preview.

**MCPWorks Agents** is an overlay product for autonomous, optionally intelligent, containerized AI entities that run on MCPWorks infrastructure. An agent has its own container, its own namespace, its own optional AI engine, and its own subdomain for receiving webhooks. Subscribing to MCPWorks Agents includes full access to MCPWorks Functions. We eat our own dogfood.

**One-liner:** Describe the automation. Your AI builds it. MCPWorks runs it.

---

## Product Relationship

```
MCPWorks Agents (overlay product)
    |
    | includes full access to
    v
MCPWorks Functions (foundation product)
    |
    | executes in
    v
Code Sandbox (nsjail, secure execution)
```

MCPWorks Functions has standalone value. Any MCP-compatible AI system can use it to create and run functions. You do not need Agents to use Functions.

MCPWorks Agents builds on Functions. Agents use Functions as their execution substrate. An agent's scheduled jobs, event responses, and self-created tools are all Functions underneath.

---

## Product Status

### MCPWorks Functions (Live, Developer Preview, March 10 2026)

| Component | Status | Notes |
|-----------|--------|-------|
| Namespace endpoints | Production | `{ns}.create.mcpworks.io` / `{ns}.run.mcpworks.io` |
| REST management API | Production | Full CRUD for namespaces, services, functions |
| MCP protocol (Create) | Production | 13 management tools via official MCP SDK |
| MCP protocol (Run) | Production | Dynamic tool generation from user functions |
| Code Sandbox backend | Production | nsjail isolation, tier-based limits, PII scrubbing |
| Auth (JWT + API key) | Production | OAuth 2.1 (Google, GitHub), scope-based access |
| Usage tracking | Production | Redis rate limiting, execution counting |
| Billing (Stripe) | Production | Subscription management, tier enforcement |
| Subdomain routing | Production | Middleware parses namespace + endpoint type |
| Admin dashboard | Production | Domain-restricted, token-auth |
| CI/CD | Production | GitHub Actions, auto-deploy to DigitalOcean |

> **Availability:** Agent functionality is production-ready and available to invited users. Public launch pending funding (SAFE Tranche 1). Contact simon.carr@mcpworks.io for early access.

### MCPWorks Agents (Production — Invite-Only)

| Component | Status | Notes |
|-----------|--------|-------|
| Agent container runtime | Production (Invite-Only) | Docker-based, one container per agent |
| Agent namespace provisioning | Production (Invite-Only) | Each agent gets its own create/run namespace |
| Agent MCP endpoint | Production (Invite-Only) | `{agent-name}.agent.mcpworks.io` for webhooks/communication |
| AI engine configuration | Production (Invite-Only) | User-supplied API key for agent's own LLM |
| Cron scheduling | Production (Invite-Only) | Scheduled function execution within agent container |
| Webhook ingress | Production (Invite-Only) | Reverse proxy to agent subdomain on :443 |
| Persistent state | Production (Invite-Only) | Key-value store scoped per agent |
| Secrets management | Production (Invite-Only) | Envelope encryption (AES-256-GCM) |
| Function locking | Production (Invite-Only) | Protect Claude-authored functions from agent modification |
| Agent cloning/forking | Production (Invite-Only) | Clone agent to new instance with divergent evolution |
| Outbound communication | Production (Invite-Only) | Discord, WhatsApp, Slack, email channels |
| Agent MCP tools | Production (Invite-Only) | `make_agent`, `list_agents`, `describe_agent`, `update_agent`, `delete_agent`, `clone_agent` |

---

## MCPWorks Functions (Detailed)

### Endpoint Pattern

```
*.create.mcpworks.io    Management (CRUD functions and services)
*.run.mcpworks.io       Execution (call functions)
```

### Architecture

```
AI Assistant (Claude Code / Copilot / Codex / Kimi / any MCP client)
    |
    | HTTPS (direct connection, no proxy, no local install)
    |
    +---> {namespace}.create.mcpworks.io/mcp
    |         make_service, list_services, delete_service
    |         make_function, update_function, delete_function
    |         list_functions, describe_function
    |
    +---> {namespace}.run.mcpworks.io/mcp
    |         Dynamically generated tools from user's functions
    |         e.g. service1/function1, service1/function2
    |
    +---> api.mcpworks.io/v1/*
              REST: Auth, account management, billing, admin
```

### Request Flow

1. AI assistant sends MCP request to namespace subdomain
2. Caddy reverse proxy terminates TLS, routes to mcpworks-api container
3. Subdomain middleware extracts namespace name and endpoint type (create/run)
4. Auth middleware validates API key, resolves user and scopes
5. Billing middleware checks execution limits against subscription tier
6. MCP handler processes request:
   - **Create**: CRUD operation on namespace/service/function (writes to Postgres)
   - **Run**: Resolves function, dispatches to Code Sandbox, returns result
7. nsjail spawns isolated Python process, executes function code, returns stdout/result
8. Usage counter incremented on successful execution
9. Execution record written (with PII scrubbing)

### Function Lifecycle

**Creation:** AI calls `make_function` with code, parameters, and description. Function stored in Postgres. Immutable FunctionVersion v1 created. Function appears as MCP tool on Run endpoint.

**Execution:** AI calls function via Run endpoint. Billing check. nsjail spawns isolated process with tier-based limits. Result returned. Execution recorded.

**Versioning:** Every update creates a new immutable FunctionVersion. The `active_version` pointer determines which version executes. Instant rollback by pointing to a previous version.

### Code-Mode Execution

Code-mode execution is the architectural pattern that differentiates MCPWorks from traditional MCP servers.

Traditional MCP loads ALL tool schemas into AI context (150K+ tokens for large toolsets). Code-mode loads only function NAMES (~2K tokens). The AI writes compact code that runs in the sandbox. Intermediate data stays in the sandbox and never enters the AI's context.

| Metric | Traditional MCP | Code-Mode | Savings |
|--------|----------------|-----------|---------|
| Tokens per operation | ~15,400 | ~3,300 | 78.5% |
| Tool definition overhead | 150,000 | 2,000 | 98.7% |
| Total cost per interaction | baseline | -70% | ~70% |

Source: Anthropic's Code Execution MCP research, January 2026.

Privacy benefit: Intermediate data (customer records, PII) stays in the sandbox. Architectural data minimization for GDPR/HIPAA/SOX compliance.

### Fleet Management

Functions live on MCPWorks infrastructure, not on individual machines. When an orchestrator updates a function, every connected agent's next call uses the new version. Rollback is instant. No git pulls, no config syncs, no fleet-wide deploys.

---

## MCPWorks Agents (Detailed)

### What an Agent Is

An MCPWorks Agent is a **containerized, optionally intelligent, autonomous entity** that runs on MCPWorks infrastructure. It is not a thin wrapper over functions. It is a persistent process with:

- Its own Docker container
- Its own namespace (create + run endpoints)
- Its own subdomain (`{agent-name}.agent.mcpworks.io`) for webhook ingress
- An optional AI engine (user-configured, BYOAI via API key: OpenAI, Anthropic, Google Gemini, xAI Grok, Mistral, DeepSeek, Moonshot Kimi, OpenRouter (200+ models), Groq, Together AI, Fireworks AI, Cohere, Cerebras, or Ollama (local). Any provider with OpenAI-compatible function calling works.)
- Cron jobs for scheduled work
- Webhook listeners for event-driven work
- Heartbeat mode for proactive autonomy (agent wakes and decides what to do)
- Optional soul document for persistent identity (LLM-configurable, user-viewable)
- Persistent state between runs
- Encrypted secrets for external service access
- Outbound communication channels (Discord, WhatsApp, Slack, email)

### Endpoint Pattern

```
*.create.mcpworks.io       Manage functions (user's namespace)
*.run.mcpworks.io          Execute functions (user's namespace)
*.agent.mcpworks.io        Agent webhook ingress + MCP communication
```

The agent endpoint is a third subdomain pattern alongside create and run. It serves two purposes: receiving inbound webhooks from external systems, and providing an MCP interface for communicating with the agent (including from the user's primary AI assistant).

### Intelligence Levels

An agent can operate at two levels:

**Without intelligence (automation mode):** The agent runs functions on schedules and responds to webhooks with predefined logic. It executes what it was told to do. Powerful but static. No AI engine needed, no token costs.

**With intelligence (autonomous mode):** The agent has its own LLM (user-supplied API key). It can reason, make decisions, and critically, it can use its own namespace's create and run interfaces to build and modify its own functions. It doesn't just execute. It evolves.

### Agent Namespace

When an agent is created, it gets its own namespace. This means the agent has:

- `{agent-name}.create.mcpworks.io` for creating its own services and functions
- `{agent-name}.run.mcpworks.io` for executing its own functions

The user who created the agent has full admin access to this namespace. They can inspect, override, or delete anything the agent created. The agent operates within its namespace autonomously, but the user is always the authority.

### The Intelligence Hierarchy

```
User (human, full admin over everything)
    |
    | natural language instructions
    v
Primary AI (Claude, Copilot, etc. -- the user's main LLM partner)
    |
    | writes high-quality functions, configures agent,
    | sets locks, issues instructions via MCP
    v
MCPWorks Agent (autonomous entity, potentially cheaper LLM)
    |
    | executes functions, responds to events,
    | can self-modify within its unlocked scope,
    | communicates back via Discord/WhatsApp/Slack/email
    v
MCPWorks Functions (the execution layer)
```

This hierarchy enables a powerful pattern: the user's primary AI (often a more capable model) can write high-quality functions that are beyond what the agent's own LLM could produce, push them into the agent's namespace, and lock them. The agent uses these locked functions for its critical path while retaining the ability to create its own functions for things within its capability.

### Function Locking

Functions in an agent's namespace can be marked as **locked**. A locked function:

- Cannot be modified or deleted by the agent's own AI
- Can only be modified by the user or their primary AI (with admin access)
- Ensures the critical path is protected from degradation by a less capable model
- Can be unlocked by the admin at any time

This creates a safety boundary: Claude writes the important functions and locks them. The agent (running on a cheaper model) handles day-to-day operations using those locked functions and can create its own unlocked functions for ad-hoc needs.

### Agent Soul (Persistent Identity)

An agent can optionally have a **soul** — a persistent identity document that shapes its reasoning, personality, and decision-making across every invocation. The soul is:

- **Optional:** Agents work without one (automation-mode agents typically don't need one)
- **LLM-configurable:** The agent's own AI engine can read and update its soul document, enabling self-refinement over time
- **User-viewable:** Always visible and editable in the user console — the user is the ultimate authority
- **Injected before every AI turn:** When an agent uses AI orchestration, the soul document is loaded into context before the LLM reasons about the trigger
- **Stored as agent state:** Uses the reserved key `__soul__` in the agent's key-value store

The soul document contains:
- **Identity:** Who the agent is, what it's for, its name and role
- **Values:** Decision-making principles, priorities, risk tolerance
- **Long-term instructions:** Standing orders that persist across all invocations
- **Accumulated context:** Knowledge the agent has gathered that should inform future decisions

The primary AI (Claude, Copilot) can write the initial soul when creating the agent. The agent's own LLM can refine it over time — adding context it's learned, adjusting its approach based on outcomes. The user can inspect and override at any time via the console.

This is distinct from configuration. Configuration says *what* the agent does. The soul says *who* the agent is.

### Heartbeat Mode

In addition to scheduled (cron) and event-driven (webhook) triggers, agents with AI engines can run in **heartbeat mode** — a proactive autonomy loop where the agent wakes on a configurable interval, evaluates its goals, and decides whether action is needed.

Heartbeat is fundamentally different from a cron schedule:
- A **cron schedule** runs a specific function at a specific time. The action is predetermined.
- A **heartbeat** runs the agent's *reasoning loop itself*. The agent decides what to do — or whether to do anything at all.

On each heartbeat tick:
1. The agent's soul document is loaded (if present)
2. The agent's goals/checklist from state storage (`__heartbeat_goals__`) is loaded
3. Recent run history and state changes are summarized
4. The full context is sent to the agent's AI engine
5. The AI decides: act (call functions, send messages), update goals, or return `HEARTBEAT_OK` (nothing to do)

Heartbeat intervals follow the same tier minimums as schedules:
- **Builder:** Minimum 5 minutes
- **Pro:** Minimum 30 seconds
- **Enterprise:** Minimum 15 seconds

Heartbeat ticks count as executions. Each tick that invokes AI orchestration is bounded by the same orchestration limits (iterations, tokens, timeout) as any other AI-mode trigger.

**Heartbeat + Soul together** enable truly autonomous agents: the soul provides persistent identity and values, the heartbeat provides proactive initiative. The agent doesn't just respond to events — it pursues goals.

### Event Model

Agents respond to three types of triggers:

**Scheduled (cron):** The agent has cron jobs that fire on a schedule. Each cron tick executes a function in the agent's namespace.

**Event-driven (webhooks):** External systems or MCPWorks functions can POST to `{agent-name}.agent.mcpworks.io`. The agent receives the webhook and its AI (or predefined logic) decides what to do.

**Heartbeat (proactive):** The agent wakes on a configurable interval, loads its soul and goals, and its AI decides whether to act. Requires an AI engine. See Heartbeat Mode above.

### Orchestration Modes

When an agent trigger fires (cron, webhook, or heartbeat), the agent can process it in one of three modes:

**Direct:** Execute the handler function immediately and return its result. No AI involvement. Fastest, cheapest, most predictable. Use for automation-mode agents.

**Reason First:** Send the trigger payload to the agent's AI engine. The AI reasons about the event and decides which functions to call (if any). Use when the appropriate response depends on context.

**Run Then Reason:** Execute the handler function first, then send the result to the agent's AI for analysis and follow-up actions. Use for monitoring patterns where you want raw data plus intelligent interpretation.

| Mode | AI Required | Latency | Token Cost | Best For |
|------|------------|---------|------------|----------|
| Direct | No | Lowest | $0 | Predictable automation |
| Reason First | Yes | Medium | Per-invocation | Context-dependent decisions |
| Run Then Reason | Yes | Highest | Per-invocation | Monitoring + analysis |

**The watcher pattern:** A Function runs on a cron schedule monitoring something (price feeds, API changes, log patterns). When it detects a condition, it fires a webhook to an Agent. The Function is the sensor. The Agent is the brain.

**The heartbeat pattern:** An agent with a soul and heartbeat mode enabled wakes every N minutes, reviews its goals and recent activity, and decides what to do next. No external trigger needed. The agent pursues its mission autonomously.

Example: Dogecoin monitoring

```
Function: "doge-watcher" (runs every 5 min via cron)
    |
    | monitors price feed, detects 5% drop in 1 hour
    |
    | POST to dogedetective.agent.mcpworks.io
    v
Agent: "dogedetective" (has Kimi K2 as its AI engine)
    |
    | receives webhook, reasons about the event
    | searches news APIs (using functions in its namespace)
    | correlates price drop with news events
    | decides this is worth reporting
    |
    | sends message to user's Discord
    v
User (on phone, anywhere)
    |
    | replies on Discord: "dig deeper, compare last 3 times"
    v
Agent: receives instruction, runs deeper analysis
    | creates a new function for historical comparison
    | executes it, formats results, sends back to Discord
```

### Outbound Communication

Agents can communicate with users through configured channels:

- **Discord** (bot integration, channel messages, DMs)
- **WhatsApp** (via API integration)
- **Slack** (bot integration, channel messages)
- **Email** (via transactional email provider)

Users can respond through these same channels with direct instructions. The agent's AI interprets the response and acts on it. The user does not need to open Claude Code or any development environment. They're on their phone, responding to their agent.

### Agent Cloning (Forking)

If a user has available agent slots, they can clone an existing agent to a new instance:

- The clone gets a new name, new namespace, new container
- It inherits: function code, state snapshot, configuration, secrets
- From that point, the original and clone evolve independently
- The user (or their primary AI) can diverge the clone's behavior

Use case: dogedetective is working well for volatility alerts. Clone it to dogedetective-contrarian. Tell the clone to look for buying opportunities during negative sentiment instead. Two agents, shared lineage, divergent strategies. Compare performance. Merge good ideas back by copying functions between namespaces.

This is `git branch` for autonomous AI entities.

### Agent Data Model

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| Agent | Agent definition | name, container_id, namespace_id, ai_engine, ai_api_key_encrypted, heartbeat_enabled, heartbeat_interval, enabled |
| AgentSchedule | Cron jobs | agent_id, function_id, cron_expression, enabled |
| AgentWebhook | Webhook endpoints | agent_id, path, handler_function_id |
| AgentRun | Execution history | agent_id, trigger_type (cron/webhook/manual), started_at, duration, status |
| AgentState | Persistent key-value store | agent_id, key, value_encrypted, updated_at |
| AgentChannel | Communication channels | agent_id, channel_type (discord/slack/whatsapp/email), config_encrypted |

### Agent Tiers

| Tier | Agents | Container Resources | Min Schedule | State Storage | Includes Functions |
|------|--------|-------------------|-------------|---------------|--------------------|
| Free | 0 | - | - | - | Free tier |
| Builder ($29) | 1 | 256 MB / 0.25 vCPU | 5 min | 10 MB | Full Functions access |
| Pro ($179) | 5 | 512 MB / 0.5 vCPU | 30 sec | 100 MB | Full Functions access |
| Enterprise ($599) | 20 (included) | 1 GB / 1.0 vCPU | 15 sec | 1 GB | Full Functions access |

Agent add-ons beyond tier allocation: $9 (Builder), $19 (Pro), $29/$49 (Enterprise standard/heavy).

### Agent AI Orchestration Limits

When agents use AI reasoning (Reason First or Run Then Reason modes), orchestration is bounded per-invocation:

| Limit | Builder | Pro | Enterprise |
|-------|---------|-----|------------|
| Max iterations per invocation | 5 | 10 | 25 |
| Max tokens per invocation | 50,000 | 200,000 | 1,000,000 |
| Max orchestration timeout | 60s | 120s | 300s |
| Max functions per invocation | 3 | 10 | 25 |

---

## Sandbox Security Model

### Isolation Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Process isolation | Linux namespaces (PID, NET, MNT, UTS, IPC) | Separate process tree, network, filesystem |
| Resource limits | cgroups v2 | CPU time, memory, disk I/O caps |
| Syscall filtering | seccomp-bpf | Block dangerous system calls |
| Orchestration | nsjail | Combines all three with config-driven policies |

### Tier-Based Resource Limits (Functions)

| Tier | Timeout | Memory | CPU Time | Concurrent | Network |
|------|---------|--------|----------|------------|---------|
| Free | 10s | 128MB | 5s | 1 | No |
| Builder | 30s | 256MB | 15s | 3 | Yes |
| Pro | 90s | 512MB | 45s | 10 | Yes |
| Enterprise | 300s | 2GB | 120s | 50 | Yes |

### Safety Measures

- Dangerous pattern detection (os.system, subprocess, eval, exec, __import__)
- PII scrubbing from error messages before storage
- Read-only function code mount
- Ephemeral execution environment (destroyed after each run)
- Agent state is the only persistence layer (scoped per-agent)
- Locked functions cannot be modified by the agent's own AI

---

## Secrets Management

Both Functions (at the platform level) and Agents use envelope encryption:

- Each secret encrypted with AES-256-GCM using a per-entity data encryption key (DEK)
- DEK encrypted with a key encryption key (KEK) stored separately
- Secrets decrypted and injected into the sandbox/container at runtime
- Secrets never stored in plaintext, never logged, never returned in API responses

For agents, secrets include:
- The agent's AI engine API key
- External service credentials (Discord bot token, API keys, etc.)
- User-provided secrets for the agent's functions

---

## Authentication Model

### API Keys

- Generated per-namespace with configurable scopes (read, write, execute)
- 12-character prefix for identification + argon2 hash for verification
- Separate keys for Create (management) and Run (execution) access
- Agent namespaces get their own keys (agent has write+execute, user has admin)
- Keys can be rotated without downtime

### OAuth 2.1

- Google and GitHub providers implemented
- Used for web dashboard and initial registration
- Generates JWT for session management

### Scope-Based Access Control

| Scope | Create Endpoint | Run Endpoint | Agent Endpoint |
|-------|----------------|--------------|----------------|
| read | List/describe functions | N/A | Read agent state/logs |
| write | Create/update/delete functions | N/A | Configure agent |
| execute | N/A | Call functions | Send commands to agent |
| admin | Full namespace control | Full namespace control | Full agent control |

---

## Billing Model

### Subscription Tiers

| Tier | Monthly | Annual | Functions | Executions/mo | Namespaces | Agents |
|------|---------|--------|-----------|---------------|------------|--------|
| Free | $0 | - | 5 | 1,000 | 1 | 0 |
| Builder | $29 | $290/yr | Unlimited | 25,000 | 3 | 1 |
| Pro | $179 | $1,790/yr | Unlimited | 250,000 | Unlimited | 5 |
| Enterprise | $599 | $5,990/yr | Unlimited | 1,000,000 | Unlimited | 20 (included) |

### What Counts as an Execution

- One function call via Run endpoint = one execution
- One scheduled agent cron tick = one execution
- One webhook-triggered agent action = one execution
- Failed executions count (prevents abuse)
- Retries count separately

### Overage Handling

- At 80%: email warning
- At 90%: in-app one-click upgrade prompt (Stripe proration)
- At 95%: email warning
- At 100%: functions and agents pause until next billing cycle (no overage charges)

### Rate Limits

| Metric | Free | Builder | Pro | Enterprise |
|--------|------|---------|-----|------------|
| Executions/min | 10 | 30 | 100 | 300 |
| Concurrent | 2 | 5 | 15 | 50 |

---

## Data Models (Key Entities)

### Functions (Production)

| Entity | Purpose | Key Fields |
|--------|---------|-----------|
| User | Account holder | email, status, effective_tier |
| Account | Billing unit (1:1 with User) | user_id, name |
| Namespace | Organizational container | name, account_id, call_count |
| Service | Groups functions within namespace | namespace_id, name |
| Function | Callable unit | name, service_id, active_version, backend, call_count, locked |
| FunctionVersion | Immutable version record | function_id, version, code, config, requirements |
| Execution | Execution history | function_id, user_id, status, duration, input/result (PII-scrubbed) |
| APIKey | Auth credential | key_prefix, key_hash, namespace_id, scopes |
| Subscription | Billing state | user_id, tier, auto_renew |
| AuditLog | Compliance trail | event, user_id, resource_id |

### Agents (Production — Invite-Only)

| Entity | Purpose | Key Fields |
|--------|---------|-----------|
| Agent | Agent definition | name, container_id, namespace_id, ai_engine, ai_api_key_encrypted, heartbeat_enabled, heartbeat_interval, enabled |
| AgentSchedule | Cron jobs | agent_id, function_id, cron_expression, enabled |
| AgentWebhook | Webhook endpoints | agent_id, path, handler_function_id |
| AgentRun | Execution history | agent_id, trigger_type, started_at, duration, status |
| AgentState | Persistent key-value store | agent_id, key, value_encrypted, updated_at |
| AgentChannel | Communication channels | agent_id, channel_type, config_encrypted |

---

## Infrastructure

### Current (A0 Developer Preview - Functions)

| Component | Provider | Details |
|-----------|----------|---------|
| API server | DigitalOcean droplet (TOR1) | s-2vcpu-4gb, Docker |
| Database | DO Managed PostgreSQL | db-s-1vcpu-2gb, VPC, daily backups |
| Cache | DO Managed Valkey (Redis) | db-s-1vcpu-1gb, VPC, TLS |
| Reverse proxy | Caddy (container) | Auto TLS, reverse proxy to API |
| CDN/DDoS | Cloudflare | Enterprise (Startup program credits) |
| DNS | Cloudflare | Wildcard `*.mcpworks.io` |
| Email | Resend | Transactional (welcome, alerts) |
| Payments | Stripe | Subscriptions, prorated upgrades |
| CI/CD | GitHub Actions | Lint, test, build, deploy on push to main |

### Required for Agents

- Docker runtime for agent containers (likely same droplet initially, dedicated nodes later)
- Wildcard routing for `*.agent.mcpworks.io` (Cloudflare + Caddy)
- Container management via Docker SDK for Python (not Compose files, not K8s)
- Scaling path: single droplet → dedicated agent nodes → Docker Swarm
- Droplet upgrade from s-2vcpu-4gb to s-4vcpu-8gb ($48/mo)
- Agent container image with pre-installed Python, APScheduler, FastAPI, AI SDKs, and communication libraries

---

## Developer Preview Program

- **Duration:** Up to 90 days from March 10, 2026
- **Access:** Full Builder tier at no cost
- **Obligation:** None. Cancel any time.
- **After preview:** 14 days written notice before downgrade to Free tier
- **Goal:** Real feedback from real engineers building real things
- **Agents:** Will be available to preview users when the agent product ships

---

## Product Roadmap (High Level)

### Live (A0: Functions Developer Preview)

- Code Sandbox backend (Python, nsjail)
- Namespace/service/function CRUD via MCP and REST
- Auth, billing, usage tracking
- Fleet propagation and instant rollback

### Live (A0: Agents — Invite-Only Preview)

- Agent container runtime and namespace provisioning
- Agent MCP endpoint (`*.agent.mcpworks.io`)
- AI engine configuration (BYOAI at the agent level)
- Orchestration modes (direct, reason_first, run_then_reason)
- Cron scheduling within agent containers
- Webhook ingress via agent subdomain
- Persistent state and secrets management
- Function locking (protect Claude-authored functions)
- Outbound communication (Discord, Slack, email)
- Agent cloning/forking
- Agent MCP tools on Create endpoint

### Later (A1+)

- WhatsApp integration for agent communication
- Function templates (pre-built starting points)
- TypeScript sandbox support
- Agent marketplace (share/sell agent configurations)
- Inter-agent communication (agents calling each other)
- GitHub Repo backend (MCPWorks framework)
- SOC 2 Type I certification

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Two branded products (Functions + Agents) | Functions has standalone value for any MCP client. Agents is the premium overlay. |
| Agents include full Functions access | Dogfooding. Agents are built on Functions. |
| Each agent gets its own namespace | Isolation, self-modification capability, admin visibility |
| Third subdomain pattern (*.agent.mcpworks.io) | Webhook ingress + MCP communication with agents |
| Optional AI engine (BYOAI per agent) | Agents can be pure automation or intelligent. User controls cost. |
| Function locking | Protects high-quality functions from degradation by less capable agent LLMs |
| Agent cloning/forking | Enables evolutionary divergence without risking working agents |
| Outbound communication channels | Agents are persistent presences, not scripts. Users interact naturally. |
| Direct HTTPS, no proxy | Zero install friction for Functions. |
| Immutable function versions | Safe rollback, audit trail, no accidental overwrites |
| nsjail for sandbox, Docker for agents | Right tool for each job: nsjail for ephemeral execution, Docker for persistent processes |
| BYOAI (no token selling) | 75-85% gross margins, no AI vendor dependency |

---

## Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| API Specification | `SPEC.md` | Complete API spec with data models and endpoints |
| Agents Tech Spec | `docs/specs/AGENTS-TECH-SPEC.md` | Engineering specification for Agents implementation |
| Constitution | `docs/implementation/specs/CONSTITUTION.md` | Development principles |
| Database Models | `docs/implementation/database-models-specification.md` | A0 data model spec |
| Namespace Architecture | `../mcpworks-internals/docs/implementation/namespace-architecture.md` | Create/run pattern |
| Sandbox Specification | `../mcpworks-internals/docs/implementation/code-execution-sandbox-specification.md` | nsjail isolation |
| Strategy | `../mcpworks-internals/STRATEGY.md` | Business strategy |
| Pricing | `../mcpworks-internals/PRICING.md` | Tier details, rate limits, agent tiers |
| Funding Action Plan | `../mcpworks-internals/docs/business/funding-action-plan-2026-03.md` | A0 execution timeline |
| Investor Pitch | `../mcpworks-internals/docs/business/investor-pitch-narrative.md` | Angel investor pitch narrative |

---

## Changelog

**v3.2.0 (2026-03-11):** Agents status updated from "Design" to "Production (Invite-Only)". Added orchestration modes (direct, reason_first, run_then_reason). Added AI orchestration tier limits. Expanded BYOAI supported provider list. Added agent availability note.

**v3.1.0 (2026-03-11):** Updated to v6.0.0 pricing (Pro $179, Enterprise $599, Enterprise agents 20 included). Added container resources and agent add-ons to Agent Tiers table. Updated infrastructure section with Docker SDK approach, s-4vcpu-8gb upgrade, and scaling path. Added Agents Tech Spec and Investor Pitch to related documents.

**v3.0.0 (2026-03-11):** Two-product specification (Functions + Agents). Agent architecture: containerized entities, intelligence hierarchy, function locking, cloning, communication channels, BYOAI.

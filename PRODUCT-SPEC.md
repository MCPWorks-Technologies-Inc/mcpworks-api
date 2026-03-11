# MCPWorks Product Specification

**Version:** 2.0.0
**Date:** 2026-03-10
**Status:** Developer Preview (A0)
**Author:** Simon Carr / Claude

---

## What This Document Is

A high-level product specification for MCPWorks as it exists today and where it's headed. This is not an API spec (see SPEC.md) or an architecture doc. This describes the product: what it does, who it's for, how it works, and what's built vs. planned.

---

## Product Summary

MCPWorks is an AI-built autonomous agent platform on namespace-based infrastructure.

Users describe automation in natural language. Their AI assistant builds agents using MCP tools. Agents run persistently on MCPWorks infrastructure on a schedule. Underneath, everything is a function executing in a secure Code Sandbox.

**One-liner:** Describe the automation. Your AI builds it. MCPWorks runs it.

**Two products, one platform:**

1. **MCPWorks Functions** (live now, Developer Preview) -- Namespace-based function hosting. AI assistants create and execute Python functions via MCP over HTTPS. The foundation.

2. **MCPWorks Agents** (shipping A0) -- Persistent, scheduled automations built on top of Functions. An agent is a function + cron schedule + persistent state + secrets. The AI builds it, MCPWorks runs it after the conversation ends.

---

## Product Status

### What's Live (Developer Preview, March 10 2026)

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
| Welcome email | Production | Resend provider, triggered on registration |

### What's Next (A0, Weeks 2-6)

| Component | Status | Notes |
|-----------|--------|-------|
| Agent data model | Not started | 3 new Postgres tables (Agent, AgentRun, AgentState) |
| Agent dispatcher | Not started | Cron scheduler, fires agents on schedule via Code Sandbox |
| Agent MCP tools | Not started | `make_agent`, `list_agents`, `describe_agent`, `update_agent`, `delete_agent` |
| Persistent state | Not started | `mcpworks.state.get/set` for data between agent runs |
| Secrets management | Not started | Envelope encryption (AES-256-GCM) for API keys/tokens |
| Namespace sharing | Partial | Model exists, REST endpoints incomplete |
| Webhooks | Partial | Model exists, integration incomplete |

### Backends

| Backend | Status | Notes |
|---------|--------|-------|
| Code Sandbox | Production | nsjail, Python, tier-based limits |
| GitHub Repo | Future | MCPWorks framework functions from user repos |

---

## Architecture Overview

```
AI Assistant (Claude Code / Copilot / Codex / Kimi / any MCP client)
    |
    | HTTPS (direct connection, no proxy, no local install)
    |
    +---> {namespace}.create.mcpworks.io/mcp
    |         Management tools:
    |         make_service, list_services, delete_service
    |         make_function, update_function, delete_function
    |         list_functions, describe_function
    |         make_agent, list_agents, describe_agent       [A0 next]
    |         update_agent, delete_agent                    [A0 next]
    |
    +---> {namespace}.run.mcpworks.io/mcp
    |         Execution tools:
    |         Dynamically generated from user's functions
    |         e.g. service1/function1, service1/function2
    |         Agent dispatcher calls these on schedule
    |
    +---> api.mcpworks.io/v1/*
              REST API:
              Auth, account management, billing, admin
```

### Request Flow (Functions)

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

### Request Flow (Agents, planned)

1. User describes desired automation to their AI assistant
2. AI calls `make_agent` via Create endpoint, which creates:
   - A function (the agent's code)
   - A cron schedule (when it runs)
   - A state bucket (persistent data between runs)
   - Encrypted secrets (API keys the agent needs)
3. Dispatcher picks up the agent on its next scheduled tick
4. Dispatcher calls the agent's function via the Run endpoint
5. Agent code can read/write persistent state via `mcpworks.state.get/set`
6. Agent code can access secrets injected into its sandbox environment
7. Execution record written, next run scheduled

---

## Functions

Functions are the building blocks. They are callable units of Python code that execute in a secure sandbox.

### Lifecycle

**Creation:**
```
AI: "Create a function that fetches weather data"
    |
    v
make_function(
    service: "weather",
    name: "get_forecast",
    description: "Fetch weather forecast for a city",
    parameters: { city: { type: "string" } },
    code: "import requests\ndef execute(city):\n    ...",
    backend: "sandbox",
    language: "python"
)
    |
    v
Function stored in Postgres
FunctionVersion v1 created (immutable)
Function appears as MCP tool on Run endpoint
```

**Execution:**
```
AI: calls weather/get_forecast(city="Vancouver")
    |
    v
Run endpoint resolves function
    |
    v
Billing check: executions_count < executions_limit?
    |
    v
Code Sandbox: nsjail spawns isolated process
    - Mounts function code as read-only
    - Applies tier-based limits (timeout, memory, CPU)
    - Executes with pre-installed libraries (requests, pandas, numpy, etc.)
    - Network access available (Builder tier and above)
    |
    v
Result returned to AI
Execution record written
Usage counter incremented
```

### Versioning

Functions use immutable versioning. Every update creates a new FunctionVersion. The function's `active_version` pointer determines which version executes. This enables:

- Instant rollback (point active_version to previous version)
- Audit trail (every version preserved)
- Safe updates (new version created before switching)

---

## Agents (Shipping A0)

Agents are the product. Functions are the building blocks.

An agent is: **a function + cron schedule + persistent state + encrypted secrets.** The user describes what they want. The AI builds it via MCP tools. MCPWorks runs it autonomously after the conversation ends.

### What Makes an Agent Different from a Function

| | Function | Agent |
|--|----------|-------|
| Execution | On-demand (AI calls it) | Scheduled (cron dispatcher) |
| State | Stateless (fresh each run) | Persistent (`mcpworks.state.get/set`) |
| Secrets | None (sandbox is ephemeral) | Encrypted (AES-256-GCM, injected at runtime) |
| Lifecycle | Exists until deleted | Runs autonomously until stopped |
| Created by | AI via `make_function` | AI via `make_agent` |

### Agent MCP Tools (5 new tools on Create endpoint)

| Tool | Description |
|------|-------------|
| `make_agent` | Create agent: function code + schedule + state + secrets |
| `list_agents` | List all agents in namespace |
| `describe_agent` | Get agent details, recent runs, state summary |
| `update_agent` | Update code, schedule, or secrets |
| `delete_agent` | Stop and remove agent |

### Agent Data Model (3 new Postgres tables)

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| Agent | Agent definition | function_id, schedule (cron), enabled, secrets_encrypted |
| AgentRun | Execution history | agent_id, started_at, duration, status, error |
| AgentState | Persistent key-value store | agent_id, key, value, updated_at |

### Agent Tiers

| Tier | Agents | Min Schedule | State Storage |
|------|--------|-------------|---------------|
| Free | 0 | - | - |
| Builder ($29) | 1 | 5 min | 10MB |
| Pro ($149) | 5 | 30 sec | 100MB |
| Enterprise ($499+) | Unlimited | 15 sec | 1GB |

### Secrets Management

Agents need API keys, tokens, and credentials to interact with external services. These are stored using envelope encryption:

- Each secret encrypted with AES-256-GCM using a per-agent data encryption key (DEK)
- DEK encrypted with a key encryption key (KEK) stored separately
- Secrets decrypted and injected into the sandbox environment at runtime
- Secrets never stored in plaintext, never logged, never returned in API responses

### Dispatcher Architecture (planned)

The dispatcher is a background process that:

1. Queries Postgres for agents whose next_run_at <= now
2. For each due agent, calls the agent's function via the Run endpoint
3. Injects persistent state and decrypted secrets into the sandbox
4. Records the AgentRun result
5. Updates next_run_at based on the cron schedule

The dispatcher reuses the existing Code Sandbox execution path. An agent run is just a function execution with extra context (state + secrets).

---

## Code-Mode Execution

Code-mode execution is the architectural pattern that differentiates MCPWorks from traditional MCP servers.

### Traditional MCP

- Load ALL tool schemas into AI context (150K+ tokens for large toolsets)
- AI calls tools one at a time
- Every intermediate result flows back into AI context
- Token cost scales linearly with tool count and data volume

### MCPWorks Code-Mode

- Load only function NAMES into AI context (~2K tokens)
- AI writes compact code that calls multiple functions
- Code runs in sandbox; intermediate data stays in sandbox
- Only final result returns to AI context
- Token cost is nearly flat regardless of data volume

### Measured Savings (Anthropic Research, January 2026)

| Metric | Traditional MCP | Code-Mode | Savings |
|--------|----------------|-----------|---------|
| Tokens per operation | ~15,400 | ~3,300 | 78.5% |
| Tool definition overhead | 150,000 | 2,000 | 98.7% |
| Total cost per interaction | baseline | -70% | ~70% |

### Privacy Benefit

Intermediate data (customer records, financial figures, PII) stays in the sandbox execution environment. It never enters the AI's context window. This is architectural data minimization, not policy-based. Relevant for GDPR, HIPAA, and SOX compliance.

---

## Sandbox Security Model

### Isolation Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Process isolation | Linux namespaces (PID, NET, MNT, UTS, IPC) | Separate process tree, network, filesystem |
| Resource limits | cgroups v2 | CPU time, memory, disk I/O caps |
| Syscall filtering | seccomp-bpf | Block dangerous system calls |
| Orchestration | nsjail | Combines all three with config-driven policies |

### Tier-Based Resource Limits

| Tier | Timeout | Memory | CPU Time | Concurrent | Network |
|------|---------|--------|----------|------------|---------|
| Free | 10s | 128MB | 5s | 1 | No |
| Builder | 30s | 256MB | 15s | 3 | Yes |
| Pro | 90s | 512MB | 45s | 10 | Yes |
| Enterprise | 300s | 2GB | 120s | 50 | Yes |

### Safety Measures

- Dangerous pattern detection (os.system, subprocess, eval, exec, __import__)
- PII scrubbing from error messages before storage (regex for emails, phones, API keys, SSNs)
- Read-only function code mount
- Ephemeral execution environment (destroyed after each run)
- Agent state is the only persistence layer (scoped per-agent, not per-sandbox)

---

## Fleet Management (Cluster Propagation)

### The Problem

Teams running agent fleets (8, 16, 50+ agentic systems) face painful MCP management:
- Function updates require git pulls/config syncs across every machine
- Version drift between agents causes inconsistent behavior
- Debugging failures across a fleet is slow and manual
- Rolling back a bad update means touching every machine

### The MCPWorks Solution

Functions live on MCPWorks infrastructure, not on individual machines. All agents connect to the same Run endpoint.

```
Orchestrator AI (e.g. Claude with Create access)
    |
    | make_function() or update_function()
    v
MCPWorks (single source of truth)
    |
    | Function immediately available
    v
Agent 1  Agent 2  Agent 3  ...  Agent N
(all connected to {ns}.run.mcpworks.io)
```

**Propagation is instant.** When the orchestrator updates a function, every agent's next call to that function uses the new version. No deploy step. No sync step.

**Rollback is instant.** Point active_version back to the previous FunctionVersion. Every agent immediately uses the old version.

**Self-healing pattern:** The orchestrator monitors agent execution logs. If a function starts failing, the orchestrator can:
1. Inspect the error via describe_function or execution logs
2. Update or roll back the function
3. Verify the fix by checking subsequent executions

This creates a closed loop: deploy, observe, fix, redeploy. All through MCP. All without human intervention if desired.

---

## Authentication Model

### API Keys

- Generated per-namespace with configurable scopes (read, write, execute)
- 12-character prefix for identification + argon2 hash for verification
- Separate keys for Create (management) and Run (execution) access
- Keys can be rotated without downtime

### OAuth 2.1

- Google and GitHub providers implemented
- Used for web dashboard and initial registration
- Generates JWT for session management

### Scope-Based Access Control

| Scope | Create Endpoint | Run Endpoint |
|-------|----------------|--------------|
| read | List/describe functions and agents | N/A |
| write | Create/update/delete functions and agents | N/A |
| execute | N/A | Call functions |

---

## Billing Model

### Subscription Tiers

| Tier | Monthly | Annual | Functions | Executions/mo | Namespaces | Agents |
|------|---------|--------|-----------|---------------|------------|--------|
| Free | $0 | - | 5 | 1,000 | 1 | 0 |
| Builder | $29 | $290/yr | Unlimited | 25,000 | 3 | 1 |
| Pro | $149 | $1,490/yr | Unlimited | 250,000 | Unlimited | 5 |
| Enterprise | $499+ | $4,990+/yr | Unlimited | 1,000,000 | Unlimited | Unlimited |

### What Counts as an Execution

- One function call via Run endpoint = one execution
- One scheduled agent run = one execution
- Failed executions count (prevents abuse)
- Retries count separately

### Overage Handling

- At 80%: email warning
- At 90%: in-app one-click upgrade prompt (Stripe proration)
- At 95%: email warning
- At 100%: functions pause until next billing cycle (no overage charges)
- Agents are paused at 100% and resume at next billing cycle

### Rate Limits

| Metric | Free | Builder | Pro | Enterprise |
|--------|------|---------|-----|------------|
| Executions/min | 10 | 30 | 100 | 300 |
| Concurrent | 2 | 5 | 15 | 50 |

---

## Data Models (Key Entities)

### Existing (Production)

| Entity | Purpose | Key Fields |
|--------|---------|-----------|
| User | Account holder | email, status, effective_tier |
| Account | Billing unit (1:1 with User) | user_id, name |
| Namespace | Organizational container | name, account_id, call_count |
| Service | Groups functions within namespace | namespace_id, name |
| Function | Callable unit | name, service_id, active_version, backend, call_count |
| FunctionVersion | Immutable version record | function_id, version, code, config, requirements |
| Execution | Execution history | function_id, user_id, status, duration, input/result (PII-scrubbed) |
| APIKey | Auth credential | key_prefix, key_hash, namespace_id, scopes |
| Subscription | Billing state | user_id, tier, auto_renew |
| AuditLog | Compliance trail | event, user_id, resource_id |

### Planned (Agents, A0 next)

| Entity | Purpose | Key Fields |
|--------|---------|-----------|
| Agent | Agent definition | function_id, schedule, enabled, secrets_encrypted, state_size_limit |
| AgentRun | Agent execution history | agent_id, started_at, duration, status, error |
| AgentState | Persistent key-value store | agent_id, key, value_encrypted, updated_at |

---

## Infrastructure

### Current (A0 Developer Preview)

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

### Planned (A1)

- Dedicated sandbox execution nodes (separate from API)
- Horizontal scaling for execution capacity
- Geographic distribution if demand warrants

---

## Developer Preview Program

- **Duration:** Up to 90 days from March 10, 2026
- **Access:** Full Builder tier at no cost (includes 1 agent when agents ship)
- **Obligation:** None. Cancel any time.
- **After preview:** 14 days written notice before downgrade to Free tier
- **Goal:** Real feedback from real engineers building real things

---

## Product Roadmap (High Level)

### Now (A0: Developer Preview)

**Functions (live):**
- Code Sandbox backend (Python, nsjail)
- Namespace/service/function CRUD via MCP and REST
- Auth, billing, usage tracking
- Fleet propagation and instant rollback

**Agents (shipping weeks 2-6):**
- Agent data model (3 Postgres tables)
- Dispatcher (cron scheduler)
- 5 agent MCP tools on Create endpoint
- Persistent state (`mcpworks.state.get/set`)
- Secrets management (envelope encryption, AES-256-GCM)

### Next (A1: General Availability)

- Function templates (pre-built starting points)
- TypeScript sandbox support
- Package/dependency management for functions
- Enhanced execution logging and debugging tools
- Webhook event listeners for agents (supplement cron scheduling)
- nanobot.ai partnership exploration (Obot AI's MCP agent framework as inspiration)

### Later (A2+)

- GitHub Repo backend (MCPWorks framework)
- Data backends (persistent storage beyond agent state)
- SOC 2 Type I certification
- Namespace sharing (cross-account collaboration)

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Direct HTTPS, no proxy | Zero install friction. AI connects with two URLs. |
| Agents = functions + schedule + state | Minimal delta over existing function infrastructure (3 tables, 1 dispatcher, 5 tools) |
| Immutable function versions | Safe rollback, audit trail, no accidental overwrites |
| Per-account billing (not per-namespace) | Namespaces are organizational, not cost centers |
| nsjail over Docker/K8s for sandbox | Lighter weight, faster spawn, direct Linux primitives |
| Stateless MCP sessions | Simpler scaling, no session affinity required |
| PII scrubbing on execution records | Compliance by default, not by policy |
| Free tier: no network, no agents | Natural conversion lever to Builder |
| Envelope encryption for agent secrets | Defense in depth; KEK/DEK separation limits blast radius |
| BYOAI (no token selling) | 75-85% gross margins, no AI vendor dependency |

---

## Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| API Specification | `SPEC.md` | Complete API spec with data models and endpoints |
| Constitution | `docs/implementation/specs/CONSTITUTION.md` | Development principles |
| Database Models | `docs/implementation/database-models-specification.md` | A0 data model spec |
| Namespace Architecture | `../mcpworks-internals/docs/implementation/namespace-architecture.md` | Create/run pattern |
| Sandbox Specification | `../mcpworks-internals/docs/implementation/code-execution-sandbox-specification.md` | nsjail isolation |
| Strategy | `../mcpworks-internals/STRATEGY.md` | Business strategy (v5.0.0: agents pivot) |
| Pricing | `../mcpworks-internals/PRICING.md` | Tier details, rate limits, agent tiers |
| Funding Action Plan | `../mcpworks-internals/docs/business/funding-action-plan-2026-03.md` | A0 execution timeline |

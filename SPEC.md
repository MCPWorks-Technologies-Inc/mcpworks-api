# MCPWorks API Specification

**Version:** 3.0.0
**Status:** Production
**Last Updated:** 2026-03-15

---

## Overview

The **mcpworks-api** is the backend service powering the MCPWorks namespace-based function hosting and autonomous agent platform. AI assistants connect directly via HTTPS to namespace endpoints where they create, manage, and execute functions backed by multiple backends. Agents run autonomously on schedules, respond to webhooks, and use AI orchestration to reason and act.

### Key Responsibilities

- **Namespace Management**: Namespaces, services, and functions (CRUD via MCP protocol)
- **Function Execution**: Secure code sandbox (nsjail), Activepieces workflows, future backends
- **Autonomous Agents**: Containerized agents with scheduling, webhooks, AI orchestration, state, and communication channels
- **User & Account Management**: Registration, OAuth (Google/GitHub), API key management
- **Usage Tracking & Billing**: Tier-based execution limits enforced via Redis, Stripe subscriptions
- **Security**: Rate limiting, concurrency caps, output sanitization, secret scrubbing, audit logging

### Technology Stack

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI 0.109+ (async) |
| Database | PostgreSQL 15+ with SQLAlchemy 2.0+ (async ORM) |
| Cache | Redis/Valkey 7+ (rate limiting, sessions, usage tracking) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| HTTP Client | httpx |
| Auth | ES256 JWT (PyJWT), Argon2 password hashing, HMAC API keys |
| Payments | Stripe |
| Encryption | AES-256-GCM envelope encryption (KEK/DEK) |
| Sandbox | nsjail (Linux namespaces, cgroups v2, seccomp-bpf) |
| Deployment | Docker + docker-compose on DigitalOcean |

---

## Architecture

### System Context

```
┌─────────────────────────────────────────────────────────┐
│  Claude Code / Codex / GitHub Copilot (MCP Client)      │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS (direct connection)
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
┌─────────────────────┐  ┌─────────────────────┐
│ {ns}.create.mcpworks│  │ {ns}.run.mcpworks.io│
│ Management (CRUD)   │  │ Execution           │
└─────────┬───────────┘  └─────────┬───────────┘
          │                        │
          └────────────┬───────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│  mcpworks-api                                           │
│  ┌──────────────┐ ┌─────────────┐ ┌──────────────────┐ │
│  │ MCP Protocol │ │ REST API    │ │ Agent Scheduler  │ │
│  │ (JSON-RPC)   │ │ (/v1/*)     │ │ (cron, webhooks) │ │
│  └──────┬───────┘ └──────┬──────┘ └────────┬─────────┘ │
│         └────────────────┼─────────────────┘           │
│                          ▼                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Middleware Stack                                 │   │
│  │ MCPTransport → Billing → RateLimit → Subdomain  │   │
│  └─────────────────────────────────────────────────┘   │
└────────┬───────────┬───────────┬─────────────┬──────────┘
         │           │           │             │
         ▼           ▼           ▼             ▼
    ┌────────┐  ┌──────────┐  ┌──────┐  ┌──────────┐
    │Postgres│  │  Redis   │  │ Code │  │  Stripe  │
    │   DB   │  │ (Valkey) │  │Sandbox│  │ Payments │
    └────────┘  └──────────┘  └──────┘  └──────────┘
```

### Endpoint Pattern

| Pattern | Purpose |
|---------|---------|
| `{namespace}.create.mcpworks.io` | Management interface — CRUD functions, services, agents |
| `{namespace}.run.mcpworks.io` | Execution interface — call functions, run code |
| `{agent}.agent.mcpworks.io` | Agent webhook ingress |
| `api.mcpworks.io` | REST API — auth, billing, admin |

### Function Backends

| Backend | Status | Description |
|---------|--------|-------------|
| **Code Sandbox** | Production | LLM-authored Python execution via nsjail |
| **Activepieces** | Production | Visual workflow builder (150+ integrations) |
| **nanobot.ai** | Deferred (A1) | AI agent framework partnership |
| **GitHub Repo** | Future | Repository-backed functions |

### Middleware Stack (execution order)

1. **CorrelationIdMiddleware** — assigns request trace ID
2. **RequestLoggingMiddleware** — structured JSON logging (structlog)
3. **SubdomainMiddleware** — parses `{ns}.{type}.mcpworks.io` → namespace + endpoint type
4. **RateLimitMiddleware** — auth rate limits, per-IP throttling
5. **BillingMiddleware** — monthly quota, per-minute rate, concurrency enforcement
6. **MCPTransportMiddleware** — intercepts `/mcp` → JSON-RPC 2.0 dispatch

---

## Data Models

### Core Entities

```
Account (1:1 User)
  └── Namespace (many)
        ├── NamespaceService (many)
        │     └── Function (many)
        │           └── FunctionVersion (many, immutable)
        └── Agent (many)
              ├── AgentRun (many)
              ├── AgentSchedule (many)
              ├── AgentWebhook (many)
              ├── AgentState (many, encrypted)
              └── AgentChannel (many, encrypted)
```

### User

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| email | VARCHAR(255) | Unique, indexed |
| password_hash | VARCHAR(255) | Nullable (OAuth users) |
| name | VARCHAR(255) | |
| tier | VARCHAR(20) | Default: `trial-agent` |
| status | VARCHAR(20) | active, pending_verification, pending_approval, rejected, suspended, deleted |
| email_verified | BOOLEAN | |
| tier_override | VARCHAR(20) | Admin-set tier override |
| tier_override_expires_at | TIMESTAMPTZ | |
| tos_accepted_at | TIMESTAMPTZ | |

### Account

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| user_id | UUID | FK → users (unique, 1:1) |
| name | VARCHAR(255) | Display name |

### Namespace

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| account_id | UUID | FK → accounts |
| name | VARCHAR(63) | DNS-compliant, globally unique |
| description | TEXT | |
| deleted_at | TIMESTAMPTZ | Soft delete |

### Function

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| service_id | UUID | FK → namespace_services |
| name | VARCHAR(63) | Unique within service |
| description | TEXT | |
| tags | TEXT[] | |
| active_version | INTEGER | Points to FunctionVersion |
| backend | VARCHAR(20) | code_sandbox, activepieces, nanobot, github_repo |
| locked | BOOLEAN | Prevents modification when true |
| locked_by | VARCHAR(100) | Attribution |

### FunctionVersion (immutable)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| function_id | UUID | FK → functions |
| version | INTEGER | Auto-incrementing |
| code | TEXT | Source code |
| config | JSONB | Backend-specific config |
| input_schema | JSONB | JSON Schema for inputs |
| output_schema | JSONB | JSON Schema for outputs |
| requirements | TEXT[] | Python packages |
| required_env | TEXT[] | Required environment variables |
| optional_env | TEXT[] | Optional environment variables |
| created_by | VARCHAR(100) | Attribution (e.g., "Claude Opus 4.6") |

### Agent

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| account_id | UUID | FK → accounts |
| namespace_id | UUID | FK → namespaces |
| name | VARCHAR(63) | DNS-compliant, unique per account |
| display_name | VARCHAR(255) | |
| status | VARCHAR(20) | creating, running, stopped, error, destroying |
| ai_engine | VARCHAR(50) | anthropic, openai, google, openrouter, grok, deepseek, kimi, ollama |
| ai_model | VARCHAR(100) | |
| ai_api_key_encrypted | BYTEA | AES-256-GCM encrypted |
| ai_api_key_dek_encrypted | BYTEA | Envelope encryption DEK |
| system_prompt | TEXT | Agent personality/instructions |
| memory_limit_mb | INTEGER | Per tier |
| cpu_limit | FLOAT | Per tier |
| tool_tier | VARCHAR(20) | execute_only, standard, builder, admin |
| scheduled_tool_tier | VARCHAR(20) | Tool tier for cron/webhook context |
| auto_channel | VARCHAR(20) | Auto-post AI responses to channel |
| mcp_servers | JSONB | External MCP server configs |
| orchestration_limits | JSONB | Per-agent overrides (nullable, tier defaults used when null) |
| cloned_from_id | UUID | FK → agents (self-referential) |

### AgentState (encrypted key-value store)

| Column | Type | Notes |
|--------|------|-------|
| agent_id | UUID | FK → agents |
| key | VARCHAR(255) | Unique per agent |
| value_encrypted | BYTEA | AES-256-GCM |
| value_dek_encrypted | BYTEA | Envelope encryption |
| size_bytes | INTEGER | For quota tracking |

### Subscription

| Column | Type | Notes |
|--------|------|-------|
| user_id | UUID | FK → users (unique, 1:1) |
| tier | VARCHAR(20) | trial-agent, pro-agent, enterprise-agent, dedicated-agent |
| status | VARCHAR(20) | active, cancelled, past_due, trialing |
| stripe_subscription_id | VARCHAR(255) | |
| stripe_customer_id | VARCHAR(255) | |
| current_period_start | TIMESTAMPTZ | |
| current_period_end | TIMESTAMPTZ | |
| interval | VARCHAR(10) | monthly, annual |

---

## Subscription Tiers

Per PRICING.md v7.0.0. All accounts have agent functionality.

| Tier | Monthly | Executions/mo | Agents | RAM/Agent | CPU/Agent | Min Schedule |
|------|---------|---------------|--------|-----------|-----------|-------------|
| **Trial** (14-day) | $0 | 125,000 | 5 | 512MB | 0.5 vCPU | 30s |
| **Pro** | $179 | 250,000 | 5 | 512MB | 0.5 vCPU | 30s |
| **Enterprise** | $599 | 1,000,000 | 20 | 1GB | 1.0 vCPU | 15s |
| **Dedicated** | $999 | Unlimited | Unlimited | 2GB | 2.0 vCPU | 15s |

### Rate Limits

| Metric | Trial | Pro | Enterprise | Dedicated |
|--------|-------|-----|------------|-----------|
| Executions/minute | 100 | 100 | 300 | 500 |
| Concurrent executions | 10 | 15 | 50 | 100 |

### Sandbox Limits

| Metric | Trial/Pro | Enterprise/Dedicated |
|--------|-----------|---------------------|
| Timeout | 90s | 300s |
| Memory | 512MB | 2GB |
| Network | Available | Available |

### Orchestration Limits (defaults, configurable per-agent)

| Metric | Trial/Pro | Enterprise | Dedicated |
|--------|-----------|------------|-----------|
| Max iterations | 10 | 25 | 50 |
| Max AI tokens | 200,000 | 1,000,000 | 2,000,000 |
| Max execution time | 120s | 300s | 300s |
| Max functions called | 10 | 25 | Unlimited |

---

## MCP Protocol Interface

AI assistants connect via JSON-RPC 2.0 over HTTPS. Two endpoint types:

### Create Interface (`{ns}.create.mcpworks.io/mcp`)

Management tools for building and configuring.

**Namespace & Service Management:**
- `make_namespace` / `list_namespaces`
- `make_service` / `list_services` / `delete_service`

**Function Management:**
- `make_function` / `update_function` / `delete_function`
- `list_functions` / `describe_function`
- `list_packages` / `list_templates` / `describe_template`
- `lock_function` / `unlock_function`

**Agent Lifecycle:**
- `make_agent` / `list_agents` / `describe_agent`
- `start_agent` / `stop_agent` / `destroy_agent` / `clone_agent`

**Agent Configuration:**
- `configure_agent_ai` / `remove_agent_ai`
- `configure_mcp_servers`
- `configure_orchestration_limits`
- `chat_with_agent`

**Agent Triggers:**
- `add_schedule` / `remove_schedule` / `list_schedules`
- `add_webhook` / `remove_webhook` / `list_webhooks`

**Agent State & Channels:**
- `set_agent_state` / `get_agent_state` / `delete_agent_state` / `list_agent_state_keys`
- `add_channel` / `remove_channel`

**Tool Scopes:** Each tool requires `read` or `write` scope on the API key.

### Run Interface (`{ns}.run.mcpworks.io/mcp`)

Execution tools, dynamically generated from namespace functions.

- Each function in the namespace becomes a callable MCP tool
- Tool descriptions include sandbox tier limits
- `_env_status` tool shows configured environment variables
- **Code mode**: `execute` tool for ad-hoc Python with access to all namespace functions via `from functions import ...`

### Authentication

API key in Bearer header: `Authorization: Bearer mcpw_...`

Key format: `mcpw_` prefix + 12-char visible prefix + Argon2 hash storage.

Scopes: `read`, `write`, `execute`, `admin`.

---

## REST API Endpoints

### Authentication (`/v1/auth`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/auth/register` | Register (email/password, returns verification PIN) |
| POST | `/v1/auth/login` | Login (returns JWT access + refresh tokens) |
| POST | `/v1/auth/token` | Exchange API key for JWT tokens |
| POST | `/v1/auth/refresh` | Refresh access token |
| POST | `/v1/auth/verify-email` | Verify email with PIN |
| POST | `/v1/auth/resend-verification` | Resend verification PIN |
| POST | `/v1/auth/logout-all` | Revoke all refresh tokens |

### OAuth (`/v1/auth/oauth`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/auth/oauth/{provider}/login` | Initiate OAuth flow (google, github) |
| GET | `/v1/auth/oauth/{provider}/callback` | OAuth callback handler |

New OAuth users are created with `trial-agent` tier and `active` status.

### Account & Usage (`/v1/account`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/account/usage` | Current execution count, limit, billing period, tier |

### Subscriptions (`/v1/subscriptions`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/subscriptions` | Create Stripe Checkout session (tier: pro, enterprise, dedicated) |
| GET | `/v1/subscriptions/current` | Get subscription details |
| DELETE | `/v1/subscriptions/current` | Cancel at period end |
| POST | `/v1/subscriptions/portal` | Create Stripe Customer Portal session |
| POST | `/v1/subscriptions/webhook` | Stripe webhook handler |

Checkout automatically maps to agent tiers (e.g., `pro` → `pro-agent`).

### Namespaces (`/v1/namespaces`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/namespaces` | Create namespace |
| GET | `/v1/namespaces` | List namespaces (paginated) |
| GET | `/v1/namespaces/{name}` | Get namespace details |
| PATCH | `/v1/namespaces/{name}` | Update namespace |
| DELETE | `/v1/namespaces/{name}` | Soft-delete (recovery period) |
| POST | `/v1/namespaces/{name}/services` | Create service |
| GET | `/v1/namespaces/{name}/services` | List services |
| POST | `/v1/namespaces/{name}/services/{id}/functions` | Create function |
| GET | `/v1/namespaces/{name}/services/{id}/functions` | List functions |
| PATCH | `/v1/namespaces/{name}/services/{id}/functions/{id}` | Update function |
| DELETE | `/v1/namespaces/{name}/services/{id}/functions/{id}` | Delete function |

### Namespace Sharing (`/v1/shares`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/namespaces/{name}/shares` | Create share invite |
| GET | `/v1/namespaces/{name}/shares` | List shares |
| POST | `/v1/shares/{id}/accept` | Accept share invitation |
| DELETE | `/v1/shares/{id}` | Revoke share |

### Agents (`/v1/agents`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/agents` | Create agent |
| GET | `/v1/agents` | List agents |
| GET | `/v1/agents/{id}` | Get agent details |
| POST | `/v1/agents/{id}/start` | Start agent |
| POST | `/v1/agents/{id}/stop` | Stop agent |
| POST | `/v1/agents/{id}/destroy` | Destroy agent |
| POST | `/v1/agents/{id}/clone` | Clone agent |
| GET | `/v1/agents/{id}/runs` | List run history |
| POST | `/v1/agents/{id}/state` | Set state key-value |
| GET | `/v1/agents/{id}/state/{key}` | Get state value |
| DELETE | `/v1/agents/{id}/state/{key}` | Delete state key |
| GET | `/v1/agents/{id}/state` | List state keys |
| POST | `/v1/agents/{id}/schedules` | Add cron schedule |
| GET | `/v1/agents/{id}/schedules` | List schedules |
| DELETE | `/v1/agents/{id}/schedules/{id}` | Remove schedule |
| POST | `/v1/agents/{id}/webhooks` | Add webhook |
| GET | `/v1/agents/{id}/webhooks` | List webhooks |
| DELETE | `/v1/agents/{id}/webhooks/{id}` | Remove webhook |
| POST | `/v1/agents/{id}/ai` | Configure AI engine |
| DELETE | `/v1/agents/{id}/ai` | Remove AI engine |
| PUT | `/v1/agents/{id}/mcp-servers` | Configure MCP servers |
| GET | `/v1/agents/{id}/mcp-servers` | Get MCP server config |
| DELETE | `/v1/agents/{id}/mcp-servers` | Remove MCP servers |
| PUT | `/v1/agents/{id}/orchestration-limits` | Set orchestration limits |
| GET | `/v1/agents/{id}/orchestration-limits` | Get effective limits |
| DELETE | `/v1/agents/{id}/orchestration-limits` | Reset to tier defaults |
| POST | `/v1/agents/{id}/channels` | Add channel (discord, slack, whatsapp, email) |
| DELETE | `/v1/agents/{id}/channels/{type}` | Remove channel |
| GET | `/v1/agents/{id}/telemetry` | SSE telemetry stream |

### Agent Webhook Ingress

| Method | Path | Description |
|--------|------|-------------|
| POST | `/webhook/{path}` | Incoming webhook (routed by `{agent}.agent.mcpworks.io`) |

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/health` | Basic health check |
| GET | `/v1/health/ready` | Readiness (DB, Redis, sandbox) |
| GET | `/v1/health/live` | Liveness probe |

### Audit

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/audit/logs` | Security events (paginated, filterable) |

### Admin (`/v1/admin`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/admin/search` | Cross-resource search |
| POST | `/v1/admin/accounts/{id}/agent-tier` | Set agent tier |
| POST | `/v1/admin/users/{id}/tier-override` | Set tier override |
| GET | `/v1/admin/usage` | Usage across all accounts |

---

## Usage Tracking

### Monthly Execution Limits

Tracked in Redis: `usage:{account_id}:{year}:{month}`

- Checked before every run endpoint execution
- Incremented on successful execution (status < 400)
- Resets at start of each calendar month
- 62-day TTL on Redis keys

### Per-Minute Rate Limits

Tracked in Redis: `execrate:{account_id}:{minute_bucket}`

- Sliding window per account
- Returns `429 EXECUTION_RATE_EXCEEDED` with `Retry-After: 60`

### Concurrency Limits

Tracked in Redis: `concurrent:{account_id}`

- Atomic increment before execution, decrement in `finally` block
- Returns `429 CONCURRENCY_LIMIT_EXCEEDED` with `Retry-After: 5`

### Daily Compute Budgets

Tracked in Redis: `compute:daily:{account_id}:{date}`

- CPU-seconds consumed per day
- Trial: 3,600s, Pro: 14,400s, Enterprise: 86,400s, Dedicated: 345,600s
- 80% warning threshold, 100% hard stop

### Overage Handling

- No overage charges
- Functions pause at 100% monthly limit
- In-app upgrade prompt at 90%
- Email warnings at 80% and 95%

---

## Agent Orchestration

### Orchestration Modes

Each schedule or webhook trigger can use one of three modes:

| Mode | Description |
|------|-------------|
| **direct** | Execute handler function, return result. No AI. |
| **reason_first** | Send trigger payload to agent's AI, let it decide which functions to call. |
| **run_then_reason** | Execute function first, then pass output to AI for analysis and follow-up actions. |

### BYOAI (Bring Your Own AI)

Agents use the account owner's LLM API key. MCPWorks does not host AI models.

Supported engines: anthropic, openai, google, openrouter, grok, deepseek, kimi, ollama.

API keys are stored with AES-256-GCM envelope encryption (KEK/DEK pattern).

### Orchestration Loop

```
Trigger → Load agent AI config → Build tool definitions (namespace functions + MCP servers)
  → AI reasoning loop:
    1. Send context to LLM
    2. If LLM returns tool_use → dispatch tool call → append result → loop
    3. If LLM returns text → orchestration complete
    4. Enforce limits (iterations, AI tokens, wall clock, function calls)
  → Post-orchestration: auto_channel output, record AgentRun
```

### Configurable Limits

Orchestration limits can be overridden per-agent via `orchestration_limits` JSONB column.
Null fields fall back to tier defaults. Valid keys:

- `max_iterations` (1-200)
- `max_ai_tokens` (1,000-10,000,000)
- `max_execution_seconds` (10-3,600)
- `max_functions_called` (1-500)

### Tool Permission Tiers

Agents have scoped tool access to prevent excessive agency (OWASP LLM06):

| Tier | Access |
|------|--------|
| `execute_only` | Only function execution |
| `standard` | Read operations + state management |
| `builder` | Create/update functions, configure AI, manage schedules |
| `admin` | Destructive operations (delete, destroy) |

Scheduled/webhook triggers default to `execute_only` unless elevated.

---

## Security

### Authentication

| Method | Use Case |
|--------|----------|
| API Key (Bearer) | MCP protocol access from AI assistants |
| JWT (ES256) | REST API access, 60-min access tokens |
| OAuth 2.0 | Google and GitHub login |

### Rate Limiting (Redis sliding window)

| Endpoint | Limit | Scope |
|----------|-------|-------|
| Auth failures | 5/minute | Per IP |
| Auth attempts | 20/minute | Per IP |
| Registration | 3/hour | Per IP |
| User requests | 1,000/hour | Per user |
| IP requests | 100/hour | Per IP |
| Executions | Per tier | Per account (see Rate Limits table) |

### Output Sanitization

All sandbox output is scrubbed before returning to LLMs:

- API keys (`sk-*`, `AKIA*`, `ghp_*`, `mcpw_*`) → `[REDACTED]`
- JWTs → `[REDACTED_JWT]`
- Connection strings → `[REDACTED_CONNECTION_URI]`
- Private keys → `[REDACTED_PRIVATE_KEY]`

Output size limits: Trial/Pro 1MB, Enterprise 5MB, Dedicated 10MB.

### Environment Variable Isolation

- Declared per-function (`required_env`, `optional_env`)
- Passed via `X-MCPWorks-Env` header at execution time
- Injected into sandbox, never logged or persisted
- Cleared from memory after sandbox setup

### Security Events

Logged asynchronously (fire-and-forget) for audit:

- `auth.login_failed` — failed authentication
- `billing.quota_exceeded` — monthly limit hit
- `sandbox.violation` — nsjail seccomp/resource kill
- `compute_budget_warning` / `compute_budget_exceeded` — daily budget thresholds

### Encryption

- Passwords: Argon2
- API keys: HMAC-SHA256 (prefix stored in plaintext for lookup)
- Agent secrets (AI keys, channel configs, state values): AES-256-GCM with envelope encryption

---

## Error Handling

### HTTP Error Responses

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable description",
  "details": {}
}
```

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `UNAUTHORIZED` | 401 | Missing or invalid credentials |
| `FORBIDDEN` | 403 | Insufficient permissions or tier |
| `NOT_FOUND` | 404 | Resource not found |
| `CONFLICT` | 409 | Duplicate name or resource conflict |
| `VALIDATION_ERROR` | 422 | Invalid input |
| `QUOTA_EXCEEDED` | 429 | Monthly execution limit exceeded |
| `EXECUTION_RATE_EXCEEDED` | 429 | Per-minute rate limit exceeded |
| `CONCURRENCY_LIMIT_EXCEEDED` | 429 | Too many concurrent executions |
| `DAILY_COMPUTE_BUDGET_EXCEEDED` | 429 | Daily CPU budget exhausted |
| `DAILY_EXEC_LIMIT_EXCEEDED` | 429 | Daily execution count exceeded |
| `RATE_LIMIT_EXCEEDED` | 429 | General rate limit |

### MCP Error Codes (JSON-RPC)

| Code | Description |
|------|-------------|
| -32700 | Parse error |
| -32600 | Invalid request |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32001 | Unauthorized |
| -32003 | Forbidden |
| -32004 | Not found |
| -32050 | Execution error |

---

## Deployment

### Production Infrastructure

| Component | Details |
|-----------|---------|
| API Server | Docker container, port 8000 (internal) |
| Reverse Proxy | Caddy (ports 80, 443, auto-TLS) |
| Database | DO Managed PostgreSQL (VPC) |
| Cache | DO Managed Valkey (VPC, TLS) |
| Server | DigitalOcean s-2vcpu-4gb, TOR1 |

### CI/CD

Push to `main` triggers:
1. **CI** — lint (ruff), test (pytest), build, security scan (detect-secrets)
2. **Deploy** — SSH to server, rsync code, rebuild container, health check

### Endpoints

- Production API: `https://api.mcpworks.io`
- Health: `https://api.mcpworks.io/v1/health`

---

## Related Documentation

| Document | Location |
|----------|----------|
| Database Models | `docs/implementation/database-models-specification.md` |
| Constitution | `docs/implementation/specs/CONSTITUTION.md` |
| Token Optimization | `docs/implementation/guidance/mcp-token-optimization.md` |

---

## Changelog

**v3.0.0 (2026-03-15):**
- Complete rewrite reflecting production implementation
- Removed all "workflows" terminology (replaced by namespace functions)
- Updated tiers: trial/pro/enterprise/dedicated (all agent-enabled)
- Documented MCP protocol interface (create + run handlers, 39 tools)
- Documented agent system (orchestration, BYOAI, state, channels, scheduling)
- Added per-minute execution rate limits and concurrency caps
- Added configurable per-agent orchestration limits
- Renamed max_total_tokens → max_ai_tokens
- Removed stale SQL schemas (replaced with model reference tables)
- Removed Activepieces integration details (backend abstraction layer)

**v2.0.0 (2026-02-10):**
- Namespace architecture migration from workflows
- Added function backends concept

**v1.0.0 (2025-12-17):**
- Initial specification

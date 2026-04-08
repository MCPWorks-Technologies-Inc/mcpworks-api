# CLAUDE.md

```
The user is pushing you to always improve, so that you can reach the potential they know you can reach.🏄
```

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mcpworks API** is the backend service that powers the mcpworks platform — open-source under BSL 1.1. It handles account management, usage tracking, subscription billing, namespace routing, and function/agent execution.

**Architecture:** RESTful API + MCP namespace endpoints (direct HTTPS, no proxy)
- **MCP Endpoints** — `/mcp/create/{ns}` (manage) / `/mcp/run/{ns}` (execute) / `/mcp/agent/{ns}` (agents)
- **API Endpoints** (`https://api.mcpworks.io/v1/`) - Public HTTP/JSON API
- **Provider Orchestration** - Stripe, etc.
- **Usage Tracking** - Subscription-based limits (executions per billing period)
- **Function Execution** - Code Sandbox (nsjail)
- **Agent Runtime** - Containerized autonomous agents with scheduling, state, BYOAI

**Strategic Context (Updated 2026-03-22):**
MCPWorks has pivoted to an **open-source-first model**. The platform identity is "the open-source standard for token-efficient AI agents." BSL 1.1 license — self-host via `docker compose up` or use MCPWorks Cloud (managed service). Revenue comes from consulting, managed cloud subscriptions, enterprise support contracts, and commercial licenses.

**Status:** Spec-driven development - specifications complete, ready for implementation

## ⭐ Source of Truth

**[SPEC.md](SPEC.md)** is the primary specification for this repository. Read it first before any implementation work.

| Document | Purpose |
|----------|---------|
| **[SPEC.md](SPEC.md)** | Complete API specification - data models, endpoints, architecture |
| [docs/implementation/specs/CONSTITUTION.md](docs/implementation/specs/CONSTITUTION.md) | Development principles and quality standards |
| [docs/implementation/plans/](docs/implementation/plans/) | Technical architecture and implementation strategies |
| [docs/implementation/guidance/](docs/implementation/guidance/) | Best practices and patterns |

## Technology Stack

**Backend:**
- Python 3.11+
- FastAPI (REST API framework)
- Pydantic for data validation
- SQLAlchemy ORM

**Database:**
- PostgreSQL 14+ (primary database)
- Redis 7+ (caching and rate limiting)

**Infrastructure:**
- DigitalOcean (Phase 1: API-based provisioning)
- Bare-metal servers (Phase 2: 79% margin improvement)

**Integrations:**
- Stripe (payments)
- Shopify (e-commerce)
- SendGrid (transactional email)
- Twilio (SMS)
- Zendesk (support tickets)

## Spec-Driven Development Workflow

This project follows **spec-kit methodology** - all code must have an approved specification first.

### Workflow

```
Constitution → Specification → Plan → Tasks → Implementation
```

**Before writing any code:**
1. Read [docs/implementation/specs/CONSTITUTION.md](docs/implementation/specs/CONSTITUTION.md) - Governing principles
2. Check if specification exists in [docs/implementation/specs/](docs/implementation/specs/)
3. If no spec, create one using [TEMPLATE.md](docs/implementation/specs/TEMPLATE.md)
4. Get spec reviewed and approved
5. Create implementation plan in [docs/implementation/plans/](docs/implementation/plans/)
6. Break into atomic tasks
7. Then write code

### Key Principles from Constitution

- **Spec-first development:** No code without approved specification
- **Token efficiency first:** Target 200-1000 tokens/operation (2-5x better than AWS/GCP)
- **Streaming architecture:** Use SSE for long-running operations (deployments, workflow execution)
- **Usage limit safety:** Check subscription limits before execution, increment on success
- **Provider abstraction:** Workflow execution layer must be swappable
- **Security by default:** Rate limiting, input validation, subscription enforcement
- **Transparent pricing:** Subscription tiers and usage exposed to LLM for intelligent decisions
- **Observable by design:** Structured logging, metrics, tracing

## Production Infrastructure

### POP11 On-Prem Architecture

Production runs on-prem on Hyper-V VMs with a DO droplet as edge proxy. Full details: `infra/POP11-ARCHITECTURE.md`

| Host | Role | Address |
|------|------|---------|
| **api.mcpworks.io** | Edge proxy (Caddy TLS only) | 159.203.30.199 (public), 10.100.0.1 (WG) |
| **server0.pop11** | API + Postgres + Redis + Sandbox | 10.0.0.14 (LAN), 10.100.0.3 (WG) |

### Services (on server0.pop11)

| Service | Container | Port | Status |
|---------|-----------|------|--------|
| API | mcpworks-api | 8000 (host) | Docker healthcheck |
| PostgreSQL 16 | mcpworks-postgres | 5432 (internal) | Self-hosted |
| Redis 7 | mcpworks-redis | 6379 (internal) | Self-hosted |

**Database:** `DATABASE_URL=postgresql+asyncpg://mcpworks:<pw>@postgres:5432/mcpworks` (no SSL — local container network)
**Cache:** `REDIS_URL=redis://redis:6379/0` (no TLS — local container network)

### Endpoints

- **Production API:** https://api.mcpworks.io
- **Health Check:** https://api.mcpworks.io/v1/health

### CI/CD (Self-Hosted Runner)

Pushing to `main` triggers automatic deployment via a self-hosted GitHub Actions runner on server0:

1. **CI runs** (GitHub-hosted) - Lint, test, build, security scan
2. **Deploy runs** (self-hosted on server0) - Checkout, rsync, rebuild, restart
3. **Verify** - Health check confirms deployment

```bash
git push origin main  # Triggers CI → Deploy
```

**No GitHub secrets required.** No SSH keys in GitHub. Runner pulls code outbound.

**Workflows:**
- `.github/workflows/ci.yml` - Lint, test, build, security
- `.github/workflows/deploy.yml` - Production deployment

### Manual Deployment

For quick deployments bypassing CI:

```bash
# From dev machine (LAN)
ssh user@10.0.0.14 "cd /opt/mcpworks && \
    sudo docker compose build api && \
    sudo docker compose up -d api"

# Verify
curl https://api.mcpworks.io/v1/health
```

### Secrets Management

**Current:** All secrets live on server0 in `/opt/mcpworks/.env` (gitignored). JWT keys in `/opt/mcpworks/keys/`. Postgres password via Docker secret in `/opt/mcpworks/secrets/postgres_password.txt`.

### Quick Commands

```bash
# SSH to server0 (production)
ssh user@10.0.0.14           # from LAN (3ms)
ssh -J user@10.100.0.1 user@10.100.0.3  # via WG jump

# SSH to edge (api.mcpworks.io)
ssh user@10.100.0.1           # via WG

# View container logs
ssh user@10.0.0.14 "sudo docker logs mcpworks-api --tail 100"

# Check container status
ssh user@10.0.0.14 "sudo docker ps"

# Restart API
ssh user@10.0.0.14 "cd /opt/mcpworks && sudo docker compose restart api"

# Database shell
ssh user@10.0.0.14 "sudo docker exec -it mcpworks-postgres psql -U mcpworks"

# Check edge status
ssh user@10.100.0.1 "sudo docker ps"
```

## Common Development Commands

### Initial Setup

```bash
# Clone and enter directory
cd /path/to/mcpworks-mcp

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate     # Windows

# Install dependencies (when requirements.txt exists)
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install in development mode
pip install -e .
```

### Running the Server

```bash
# Start API server (development)
uvicorn mcpworks_api.main:app --reload --port 8000

# Start with debug logging
uvicorn mcpworks_api.main:app --reload --port 8000 --log-level debug

# Production server
gunicorn mcpworks_api.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

### Development Workflow

```bash
# Type checking
mypy src/

# Code formatting + linting (ruff replaces black, isort, flake8, pylint)
ruff format src/ tests/
ruff check --fix src/ tests/

# Run tests
pytest tests/ -v
pytest tests/ -v --cov=src  # With coverage

# Run specific test file
pytest tests/test_api_endpoints.py -v
pytest tests/test_usage_tracking.py -v
```

### Database Operations

```bash
# Run migrations (Alembic)
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Description"

# Rollback migration
alembic downgrade -1
```

### Working with Specs

```bash
# Review specifications
cat docs/implementation/specs/mcpworks-mcp-server-spec.md

# Check implementation plan
cat docs/implementation/plans/technical-architecture.md

# Review token optimization patterns
cat docs/implementation/guidance/mcp-token-optimization.md
```

## Architecture Overview

### API Endpoints (REST)

**Account Management:**
- `POST /v1/auth/register` - Create new account
- `POST /v1/auth/login` - Authenticate and get API key
- `GET /v1/account` - Get account details
- `GET /v1/account/usage` - Get current usage (executions_count, executions_limit, executions_remaining)

**Services (Hosting):**
- `POST /v1/services` - Provision hosting service
- `GET /v1/services/{service_id}` - Get service status
- `PATCH /v1/services/{service_id}` - Scale resources
- `DELETE /v1/services/{service_id}` - Deprovision service

**Deployments:**
- `POST /v1/deployments` - Deploy application from Git
- `GET /v1/deployments/{deployment_id}` - Get deployment status
- `GET /v1/deployments/{deployment_id}/logs` - Stream deployment logs (SSE)
- `POST /v1/deployments/{deployment_id}/rollback` - Rollback deployment

**Domains:**
- `POST /v1/domains` - Register domain
- `GET /v1/domains/{domain_id}` - Get domain status
- `POST /v1/domains/{domain_id}/dns` - Configure DNS records
- `GET /v1/domains/check` - Check domain availability

**SSL:**
- `POST /v1/ssl` - Provision SSL certificate
- `GET /v1/ssl/{cert_id}` - Get certificate status
- `POST /v1/ssl/{cert_id}/renew` - Renew certificate

**Integrations:**
- `POST /v1/integrations/stripe` - Setup Stripe account
- `POST /v1/integrations/shopify` - Setup Shopify store
- `POST /v1/integrations/sendgrid` - Setup SendGrid email
- `POST /v1/integrations/twilio` - Setup Twilio SMS
- `POST /v1/integrations/zendesk` - Setup Zendesk support
- `POST /v1/integrations/mailchimp` - Setup Mailchimp
- `POST /v1/integrations/typeform` - Setup Typeform

### Usage Tracking (Subscription-Based)

**Billing Model:** Monthly subscription with execution limits per billing period

**Subscription Tiers (MCPWorks Cloud):**
| Tier | Price | Agents | Executions/Month |
|------|-------|--------|------------------|
| 14-Day Pro Trial | $0 | 5 | 125,000 |
| Pro | $179/mo | 5 | 250,000 |
| Enterprise | $599/mo | 20 | 1,000,000 (fair use) |
| Dedicated | $999/mo | Unlimited | Unlimited (fair use) |

**Community Edition (Self-Hosted):** Free, BSL 1.1, `docker compose up`

**Usage Check Pattern:**
```python
async def execute_workflow(user_id: UUID, workflow_id: UUID):
    # 1. Check usage limit before execution
    usage = await get_current_usage(user_id)
    if usage.executions_count >= usage.executions_limit:
        raise UsageLimitExceededError(
            executions_count=usage.executions_count,
            executions_limit=usage.executions_limit,
            resets_at=usage.billing_period_end
        )

    # 2. Execute workflow
    result = await backend.execute(workflow_id, ...)

    # 3. Increment usage count on success
    await increment_usage(user_id)

    return result
```

**UsageRecord Model:**
```python
class UsageRecord:
    user_id: UUID
    billing_period_start: datetime
    billing_period_end: datetime
    executions_count: int      # Current count this period
    executions_limit: int      # Limit based on subscription tier
    # Derived: executions_remaining = executions_limit - executions_count
```

### Streaming Architecture

**Long-running operations use Server-Sent Events (SSE):**

```python
# Tool returns stream URL
{
    "deployment_id": "dep_abc123",
    "stream_url": "https://api.mcpworks.io/v1/streams/dep_abc123",
    "status": "in_progress"
}

# AI assistant subscribes to SSE stream
# Receives real-time progress updates:
# - "Cloning repository..."
# - "Installing dependencies..."
# - "Building application..."
# - "Deploying to production..."
# - "Deployment complete! URL: https://app.example.com"
```

### Provider Abstraction Layer

All infrastructure operations go through provider-agnostic interfaces:

```python
# Good: Provider-agnostic
from multisphere_mcp.providers import ComputeProvider
provider = ComputeProvider.get_current()  # Returns DO, AWS, or bare-metal
instance = await provider.create_instance(spec)

# Bad: Direct provider coupling
from digitalocean import Manager
client = Manager(token=api_token)
droplet = client.create_droplet(...)
```

## Token Efficiency Requirements

**Target:** 200-1000 tokens per operation (80%+ operations under 500 tokens)

### Critical Optimization Patterns

**1. Progressive Disclosure:**
```json
// Bad: Return full service details (2000+ tokens)
{
  "service_id": "svc_123",
  "full_config": {...},
  "all_metrics": {...},
  "complete_history": [...]
}

// Good: Return reference with expansion option (200 tokens)
{
  "service_id": "svc_123",
  "status": "running",
  "url": "https://api.mcpworks.io/v1/services/svc_123"
}
```

**2. Semantic Compression:**
```json
// Bad: Verbose error message (150 tokens)
"The deployment failed because the Git repository could not be cloned due to invalid credentials. Please check that..."

// Good: Structured error (50 tokens)
{
  "error": "git_clone_failed",
  "reason": "invalid_credentials",
  "action": "verify_ssh_key"
}
```

**3. References Over Full Data:**
```json
// Return resource URLs, not full objects
{
  "services": [
    {"id": "svc_1", "url": "/v1/services/svc_1"},
    {"id": "svc_2", "url": "/v1/services/svc_2"}
  ]
}
```

**Required Reading:** [docs/implementation/guidance/mcp-token-optimization.md](docs/implementation/guidance/mcp-token-optimization.md)

## Security Requirements

### Port Restrictions

**Allowed ports (no restrictions):**
- 80 (HTTP)
- 443 (HTTPS)
- 22 (SSH - managed access only)

**Allowed with justification:**
- 3000-3010 (common dev servers)
- 5432 (PostgreSQL)
- 6379 (Redis)
- 27017 (MongoDB)

**Blocked (security risk):**
- 25, 587, 465 (SMTP - prevent spam)
- 23 (Telnet - insecure)
- 3389 (RDP - Windows attack vector)

### Input Validation

**All tool inputs must:**
- Validate against Pydantic schemas
- Sanitize for SQL injection
- Check for command injection
- Validate domain/DNS format
- Rate limit per account

### Authentication

**MCP Protocol:**
- API key authentication
- Session management
- Token rotation

**REST API:**
- JWT tokens
- OAuth2 for integrations
- API key for programmatic access

## Testing Requirements

### Test Coverage

**Minimum coverage:** 80% overall, 95% for usage tracking system

**Required test types:**
- Unit tests for all business logic
- Integration tests for provider interfaces
- End-to-end tests for critical workflows
- Load tests for scalability validation

### Test Commands

```bash
# Run all tests
pytest tests/ -v

# Run specific test category
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/e2e/ -v

# Run with coverage
pytest tests/ -v --cov=src --cov-report=html

# Run load tests (requires infrastructure)
locust -f tests/load/locustfile.py
```

### Mock Data

**Use fixtures for:**
- Provider API responses (Stripe, etc.)
- Database state
- Usage records and subscription tiers
- Workflow execution scenarios

**Location:** `tests/fixtures/`

## Key Documentation

### Specifications

- **[Constitution](docs/implementation/specs/CONSTITUTION.md)** - Development principles and quality standards
- **[MCP Server Spec - Phase 1](docs/implementation/specs/mcpworks-mcp-server-spec.md)** - Core features (v1.3.0)
- **[MCP Server Spec - Phase 2](docs/implementation/specs/mcpworks-mcp-server-spec-phase2.md)** - Extended features (v2.1.0)
- **[Spec Template](docs/implementation/specs/TEMPLATE.md)** - Template for new specifications

### Implementation Plans

- **[Technical Architecture](docs/implementation/plans/technical-architecture.md)** - System architecture and tech stack
- **[Provider Selection Strategy](docs/implementation/plans/provider-selection-strategy.md)** - Infrastructure provider analysis

### Guidance

- **[Token Optimization](docs/implementation/guidance/mcp-token-optimization.md)** - **CRITICAL** - Token efficiency patterns

### Business Context (in mcpworks-internals)

For business strategy, legal, and governance documentation, see the planning repository:
- **Location:** `../mcpworks-internals/docs/`
- **Index:** `../mcpworks-internals/docs/INDEX.md`

## Project Structure

```
mcpworks-api/
├── docs/
│   └── implementation/
│       ├── specs/              # Specifications (WHAT/WHY)
│       ├── plans/              # Implementation plans (HOW)
│       └── guidance/           # Best practices
│
├── src/
│   └── mcpworks_api/
│       ├── main.py             # FastAPI application
│       ├── routers/            # API route handlers
│       │   ├── auth.py
│       │   ├── services.py
│       │   ├── deployments.py
│       │   ├── domains.py
│       │   └── integrations.py
│       ├── models/             # SQLAlchemy models
│       ├── schemas/            # Pydantic schemas (API contracts)
│       ├── providers/          # Provider abstraction layer
│       │   └── stripe.py       # Subscription billing
│       ├── usage/              # Usage tracking system
│       │   ├── tracking.py     # Check/increment usage
│       │   └── records.py      # UsageRecord model
│       └── streaming/          # SSE streaming
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   ├── load/
│   └── fixtures/
│
├── infra/                      # Infrastructure provisioning & monitoring
│   ├── mgmt/                   # Mgmt droplet configs (planned, not yet deployed)
│   ├── prod/                   # Prod exporters (node-exporter, promtail)
│   └── scripts/                # Tunnel, provisioning, migration scripts
├── alembic/                    # Database migrations
├── CLAUDE.md                   # This file
├── README.md                   # Project overview
├── requirements.txt            # Dependencies
└── requirements-dev.txt        # Dev dependencies
```

## Git Workflow

### Branch Naming

```
feature/mcp-tool-provisioning   # New features
fix/usage-tracking-bug          # Bug fixes
refactor/provider-abstraction   # Refactoring
docs/update-architecture        # Documentation
```

### Commit Messages

```
Add MCP tool for service provisioning

- Implement provision_service tool with hold/commit pattern
- Add provider abstraction layer for DigitalOcean
- Include SSE streaming for progress updates
- Add unit and integration tests (95% coverage)

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Common Mistakes to Avoid

### ❌ Don't Do This

- Committing Python files without running `ruff format` and `ruff check --fix` first
- Writing code before specification exists
- Returning verbose tool responses (>1000 tokens)
- Directly coupling to provider APIs (Stripe, etc.)
- Skipping usage limit checks before execution
- Blocking operations instead of streaming progress
- Hardcoding pricing or subscription tiers
- Ignoring token efficiency requirements

### ✅ Do This

- Read spec before implementing feature
- Use progressive disclosure and references
- Use provider abstraction layer
- Check usage limits before every execution
- Stream long-running operations via SSE
- Make subscription tiers configurable and LLM-accessible
- Optimize for token efficiency (200-1000 tokens)

## Strategic Context

**Model:** Open-source (BSL 1.1) + managed cloud + consulting. Build for customers and community, not acquirers.

**Identity:** The open-source standard for token-efficient AI agents.

**Key Differentiators:**
- Code Execution Sandbox delivers 70-98% token savings (data stays in sandbox, never enters AI context)
- MCP Server Plugin Architecture: namespaces can host ANY third-party MCP server (Google Workspace, Slack, GitHub, etc.) with code-mode wrapping for universal token efficiency (A1 milestone)
- Open-source community is the moat — not code
- BYOAI: users bring their own AI provider, no vendor lock-in
- Namespace-based function hosting with direct HTTPS (no proxy)

**Function Backends:**
- Code Sandbox (nsjail, A0) — LLM-authored Python/JS in secure sandbox
- MCP Server Plugin (A1) — any third-party MCP server bolted onto a namespace
- nanobot.ai (A1) — partnership
- Backend interface must be clean and extensible — new backends plug in without rewriting namespace routing

**Code Quality Standards:**
- Production-ready (comprehensive tests, documentation)
- Security-first (no vulnerabilities in audit)
- Scalable architecture (1K → 10K → 100K customers)
- Clean abstractions (easy for community contributors and potential partners)

**Do NOT:**
- Reference "proxy" or "gateway" (direct HTTPS, no proxy)
- Use "Agentic Services" or "Workflows" (agents are the product, functions are building blocks)
- Use exit-focused or acquisition-driven language
- Suggest closed-source SaaS approaches

## Support and Resources

- **MCP Protocol:** https://spec.modelcontextprotocol.io/
- **FastAPI:** https://fastapi.tiangolo.com/
- **Anthropic Docs:** https://docs.anthropic.com/
- **Planning Repo:** `../mcpworks-internals/`
- **Demo Server:** `../mcpworks-mcp-demo/` (validation/mockup only)

---

**Remember:** Spec-first development, token efficiency, and transaction safety are non-negotiable. Read the Constitution and specs before writing any code.

## Active Technologies
- Python 3.11+ + FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, httpx, PyJWT, argon2-cffi, stripe (001-api-gateway-mvp)
- PostgreSQL 15+ (primary), Redis 7+ (rate limiting, sessions) (001-api-gateway-mvp)
- Python 3.11+ + FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, structlog, MCP Python SDK (002-env-passthrough)
- PostgreSQL 15+ (env var names only — never values), tmpfs (transient env file during execution) (002-env-passthrough)
- Python 3.11+ (existing) + FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, Authlib 1.3+ (new), httpx (existing) (002-oauth-email-system)
- PostgreSQL 15+ (existing), Redis 7+ (existing, also used for OAuth state storage) (002-oauth-email-system)
- Python 3.11+ + FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, Docker SDK 7.0+, APScheduler 3.10+, cryptography (AES-256-GCM), httpx, discord.py (003-containerized-agents)
- PostgreSQL 15+ (primary, via DO Managed Database), Redis/Valkey 7+ (rate limiting, sessions) (003-containerized-agents)
- Python 3.11+ (existing) + FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, httpx, structlog, aiosmtplib (new) (005-oss-self-hosting)
- PostgreSQL 15+ (existing), Redis/Valkey 7+ (existing) — both bundled in self-hosted compose (005-oss-self-hosting)
- Python 3.11+ (existing codebase) + FastAPI (existing), PyYAML, gitpython (or subprocess git calls) (007-namespace-git-export)
- PostgreSQL (existing — new `namespace_git_remotes` table), envelope encryption for PAT storage (007-namespace-git-export)
- Python 3.11+ (existing codebase) + FastAPI (existing), MCP Python SDK (existing — `mcp[http]`), structlog (existing) (008-mcp-server-plugins)
- PostgreSQL (existing — new `namespace_mcp_servers` table with encrypted credentials + settings/env JSONB), Redis (existing — connection pool metadata) (008-mcp-server-plugins)
- Python 3.11+ (existing codebase) + FastAPI (existing), re module (stdlib), structlog (existing) (009-prompt-injection-defense)
- PostgreSQL (existing — new `output_trust` column on functions, new `rules` JSONB on namespace_mcp_servers) (009-prompt-injection-defense)
- Python 3.11+ (existing codebase) + FastAPI (existing), SQLAlchemy (existing), APScheduler (existing), prometheus_fastapi_instrumentator (existing) (010-mcp-proxy-analytics)
- PostgreSQL (existing — two new tables: `mcp_proxy_calls`, `mcp_execution_stats`) (010-mcp-proxy-analytics)
- Python 3.11+ (existing codebase) + FastAPI 0.109+, SQLAlchemy 2.0+ (async), Docker SDK 7.0+, croniter, structlog, Redis 7+ (existing) (012-agent-clusters)
- PostgreSQL 15+ (existing, via DO Managed Database), Redis/Valkey 7+ (existing, via DO Managed Valkey) (012-agent-clusters)
- Python 3.11+ (existing codebase) + FastAPI 0.109+, structlog (existing) (014-agent-security-hardening)
- PostgreSQL 15+ (existing, security events via fire_security_event) (014-agent-security-hardening)
- Python 3.11+ (existing codebase) + FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, structlog (013-add-procedures-framework)
- PostgreSQL 15+ (existing — new tables for procedures, versions, executions) (013-add-procedures-framework)
- Python 3.11+ + FastAPI 0.109+, SQLAlchemy 2.0+ (async), httpx, structlog (017-fix-procedure-execution)
- PostgreSQL 15+ (existing), Redis 7+ (existing) (017-fix-procedure-execution)
- PostgreSQL 15+ (new JSONB column on agents table) (018-agent-access-control)
- PostgreSQL 15+ (extend existing executions table) (020-execution-debugging)
- Python 3.11+ + FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, httpx (webhook calls), structlog (021-security-scanner-pipeline)
- PostgreSQL 15+ (JSONB on namespaces for pipeline config; scan results in executions.backend_metadata) (021-security-scanner-pipeline)
- PostgreSQL 15+ (existing `mcp_execution_stats` and `mcp_proxy_calls` tables) (022-analytics-token-savings)
- Python 3.11+ + FastAPI 0.109+, SQLAlchemy 2.0+ (async), httpx (async HTTP client), Pydantic v2, structlog (023-telemetry-webhook)
- PostgreSQL 15+ (webhook config on namespaces table), Redis 7+ (optional batching buffer) (023-telemetry-webhook)
- Python 3.11+ + FastAPI 0.109+, SQLAlchemy 2.0+ (async), `agent-governance-toolkit` (optional, MIT) (024-agent-governance-toolkit)
- PostgreSQL 15+ (new columns on `agents` table), existing scanner pipeline JSONB config (024-agent-governance-toolkit)

## Recent Changes
- 001-api-gateway-mvp: Added Python 3.11+ + FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, httpx, PyJWT, argon2-cffi, stripe


## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create GitHub issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
4. **Clean up** - Clear stashes, prune remote branches
5. **Verify** - All changes committed AND pushed
6. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

# CLAUDE.md

```
The user is pushing you to always improve, so that you can reach the potential they know you can reach.🏄
```

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mcpworks API** is the proprietary backend service that powers the mcpworks platform. It handles account management, usage tracking, subscription billing, and workflow execution.

**Architecture:** RESTful API service consumed by the open-source MCP server
- **API Endpoints** (`https://api.mcpworks.io/v1/`) - Public HTTP/JSON API
- **Provider Orchestration** - Activepieces, Stripe, etc.
- **Usage Tracking** - Subscription-based limits (executions per billing period)
- **Workflow Execution** - Activepieces workflow orchestration

**Relationship to MCP:**
- `mcpworks-mcp` (open-source) - MCP protocol server that calls this API
- `mcpworks-api` (proprietary, this repo) - Backend that does the actual work

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

### DigitalOcean Droplet

| Property | Value |
|----------|-------|
| **Name** | mcpworks-prod |
| **IP Address** | 159.203.30.199 |
| **Region** | NYC1 |
| **Size** | s-2vcpu-4gb |
| **SSH User** | root |
| **App Directory** | /opt/mcpworks |

### Services

| Service | Container | Port | Status |
|---------|-----------|------|--------|
| API | mcpworks-api | 8000 (internal) | Docker healthcheck |
| Caddy | mcpworks-caddy | 80, 443 | Reverse proxy to API |
| PostgreSQL | mcpworks-postgres | 5432 (internal) | Primary database |
| Redis | mcpworks-redis | 6379 (internal) | Rate limiting, sessions |

### Endpoints

- **Production API:** https://api.mcpworks.io
- **Health Check:** https://api.mcpworks.io/v1/health

### Deployment

```bash
# 1. Push changes to branch
git push origin 001-api-gateway-mvp

# 2. Sync code to production server
rsync -avz --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
    --exclude='*.pyc' --exclude='.env' --exclude='.coverage' \
    --exclude='keys' --exclude='logs' --exclude='data' --exclude='sandbox' \
    src/ root@159.203.30.199:/opt/mcpworks/src/

# 3. Copy docker-compose if changed
scp docker-compose.prod.yml root@159.203.30.199:/opt/mcpworks/

# 4. Rebuild and restart on server
ssh root@159.203.30.199 "cd /opt/mcpworks && \
    docker compose -f docker-compose.prod.yml build api && \
    docker compose -f docker-compose.prod.yml up -d api"

# 5. Verify deployment
curl https://api.mcpworks.io/v1/health
```

### Quick Commands

```bash
# SSH to production
ssh root@159.203.30.199

# View container logs
ssh root@159.203.30.199 "docker logs mcpworks-api --tail 100"

# Check container status
ssh root@159.203.30.199 "docker ps"

# Restart API
ssh root@159.203.30.199 "cd /opt/mcpworks && docker compose -f docker-compose.prod.yml restart api"

# Database query
ssh root@159.203.30.199 "docker exec mcpworks-postgres psql -U mcpworks -c 'SELECT * FROM users;'"
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

# Code formatting
black src/
isort src/

# Linting
flake8 src/
pylint src/

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

**Subscription Tiers:**
| Tier | Price | Executions/Month |
|------|-------|------------------|
| Free | $0 | 100 |
| Founder | $29/mo | 1,000 |
| Founder Pro | $59/mo | 10,000 |
| Founder Enterprise | $129+/mo | Unlimited |

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
    result = await activepieces.trigger_workflow(workflow_id, ...)

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
- Provider API responses (Activepieces, Stripe, etc.)
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
│       │   ├── activepieces.py # Workflow execution engine
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

- Writing code before specification exists
- Returning verbose tool responses (>1000 tokens)
- Directly coupling to provider APIs (Activepieces, Stripe)
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

## Acquisition Context

This project is on a **15-month acquisition timeline** targeting $10M-$15M exit.

**Key Acquisition Drivers:**
- First-mover advantage in MCP hosting (6-12 month window)
- 98% time reduction value proposition
- Production-grade transaction safety
- Token efficiency (2-5x better than cloud providers)
- Complete tech stack integration (not just hosting)

**Code Quality Standards:**
- Due diligence ready (comprehensive tests, documentation)
- Security-first (no vulnerabilities in audit)
- Scalable architecture (1K → 10K → 100K customers)
- Clean abstractions (easy for acquirer to integrate)

**Target Acquirers:** Anthropic, Cloudflare, Microsoft/GitHub, DigitalOcean, Vercel

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

## Recent Changes
- 001-api-gateway-mvp: Added Python 3.11+ + FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, httpx, PyJWT, argon2-cffi, stripe

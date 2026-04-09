# CLAUDE.md

```
The user is pushing you to always improve, so that you can reach the potential they know you can reach.
```

## Project Overview

**mcpworks API** — Backend for the mcpworks platform (BSL 1.1). Namespace-based function hosting, agent runtime, usage tracking, subscription billing.

**Architecture:** RESTful API + MCP namespace endpoints (direct HTTPS, no proxy)
- `/mcp/create/{ns}` (manage) / `/mcp/run/{ns}` (execute) / `/mcp/agent/{ns}` (agents)
- Public REST API at `https://api.mcpworks.io/v1/`

## Source of Truth

| Document | Purpose |
|----------|---------|
| **[SPEC.md](SPEC.md)** | Complete API specification — data models, endpoints, architecture |
| [docs/implementation/specs/CONSTITUTION.md](docs/implementation/specs/CONSTITUTION.md) | Development principles and quality standards |

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0+ (async)
- **Database:** PostgreSQL 15+, Redis/Valkey 7+
- **Integrations:** Stripe, SendGrid, Twilio, Zendesk
- **Identity:** The open-source standard for token-efficient AI agents

## Dev Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Run
uvicorn mcpworks_api.main:app --reload --port 8000

# Test
pytest tests/unit/ -q              # Unit tests (fast, no DB needed)
pytest tests/integration/ -v       # Integration (needs Postgres)

# Lint
ruff format src/ tests/
ruff check --fix src/ tests/

# Database
alembic upgrade head               # Run migrations
alembic revision --autogenerate -m "Description"  # Create migration
```

## Deep-Dive References

Read these when working in the relevant area — not upfront.

| Topic | File |
|-------|------|
| API endpoints, usage tracking, streaming, provider abstraction | [docs/claude/architecture.md](docs/claude/architecture.md) |
| Token optimization patterns (200-1000 tokens/op target) | [docs/claude/token-efficiency.md](docs/claude/token-efficiency.md) |
| Port restrictions, auth, input validation | [docs/claude/security.md](docs/claude/security.md) |
| Test coverage targets, test organization | [docs/claude/testing.md](docs/claude/testing.md) |
| Spec-first workflow (constitution, spec, plan, tasks, code) | [docs/claude/spec-workflow.md](docs/claude/spec-workflow.md) |
| Branch naming, commit messages, PR process | [docs/claude/git-workflow.md](docs/claude/git-workflow.md) |
| Token optimization deep dive | [docs/implementation/guidance/mcp-token-optimization.md](docs/implementation/guidance/mcp-token-optimization.md) |

## Project Structure

```
src/mcpworks_api/
├── main.py             # FastAPI app
├── routers/            # API route handlers
├── models/             # SQLAlchemy models
├── schemas/            # Pydantic schemas
├── services/           # Business logic
├── core/               # Scanner pipeline, agent access, database
├── mcp/                # MCP protocol handlers (create, run, agent)
├── backends/           # Execution backends (sandbox)
├── middleware/          # Rate limiting, billing, metrics
└── api/v1/             # REST endpoints

tests/unit/             # No DB needed
tests/integration/      # Needs Postgres (CI only)
alembic/versions/       # Database migrations
specs/                  # Speckit artifacts per feature
```

## Rules

- **Spec-first:** No production code without approved specification
- **Token efficiency:** Target 200-1000 tokens/operation
- **Usage safety:** Check subscription limits before execution, increment on success
- **Security:** Rate limiting, input validation, subscription enforcement
- Never reference "proxy" or "gateway" (direct HTTPS)
- Never use "Agentic Services" or "Workflows" (agents + functions)
- Never commit secrets or keys
- Read files before editing; prefer editing over creating new files
- structlog throughout (not stdlib logging)
- Ruff for formatting and linting (not black/flake8 separately)

## Function Backends

- **Code Sandbox** (nsjail, A0) — LLM-authored Python/JS in secure sandbox
- **MCP Server Plugin** (A1) — any third-party MCP server bolted onto a namespace
- Backend interface must be clean and extensible — new backends plug in without rewriting namespace routing

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
- PostgreSQL 15+ (new trust_score columns on `agents` table) (024-trust-scoring-and-compliance)

## Recent Changes
- 001-api-gateway-mvp: Added Python 3.11+ + FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, httpx, PyJWT, argon2-cffi, stripe

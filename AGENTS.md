# AGENTS.md — LLM Coding Standards

This file provides guidance to AI coding assistants (Claude Code, Copilot, Cursor, etc.) when working with this repository.

## Project Overview

**mcpworks-api** is the backend service for MCPWorks — an open-source platform for token-efficient AI agents. It handles account management, namespace routing, function execution (sandboxed), and agent orchestration.

**License:** BSL 1.1 (open-source, self-hostable)

**Architecture:** RESTful API + MCP namespace endpoints (direct HTTPS, no proxy)
- MCP endpoints: `/mcp/create/{ns}` (manage) / `/mcp/run/{ns}` (execute) / `/mcp/agent/{ns}` (agents)
- API endpoints: `https://api.mcpworks.io/v1/`
- Function execution: Code Sandbox (nsjail) with Python/TypeScript support
- Agent runtime: Autonomous agents with scheduling, state, webhooks, BYOAI

## Technology Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI 0.109+, Pydantic v2, SQLAlchemy 2.0+ (async)
- **Database:** PostgreSQL 15+, Redis/Valkey 7+
- **Auth:** JWT (ES256), OAuth2 (Google, GitHub)
- **Sandbox:** nsjail for code execution isolation
- **Deployment:** Docker Compose (self-hosted) or managed cloud

## Development Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Run locally
docker compose up -d postgres redis
uvicorn mcpworks_api.main:app --reload --port 8000

# Tests
pytest tests/ -v
pytest tests/ -v --cov=src

# Lint & Format
ruff check src/
ruff format src/

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

## Code Style

- Follow existing conventions in the file you're editing
- Ruff handles formatting and linting (configured in `pyproject.toml`)
- Use type hints for all function signatures
- Use Pydantic v2 for all API schemas
- Use SQLAlchemy 2.0 async patterns
- Use structlog for logging (not stdlib `logging`)
- Never add comments unless explicitly requested
- Never commit secrets, keys, or credentials

## Key Principles

### Spec-First Development
No production code without an approved specification in `docs/implementation/specs/`. Read the Constitution at `docs/implementation/specs/CONSTITUTION.md` before making architectural changes.

### Token Efficiency
Target 200-1000 tokens per MCP operation. Use progressive disclosure (return references, not full objects), semantic compression for errors, and streaming (SSE) for long-running operations.

### Provider Abstraction
Never couple directly to infrastructure providers. All backends (sandbox, workflow, etc.) go through abstract interfaces so they can be swapped.

### Usage Safety
Always check subscription limits before execution and increment usage on success. Never skip this pattern.

## Project Structure

```
src/mcpworks_api/
    main.py              # FastAPI application entry point
    config.py            # Settings (Pydantic BaseSettings)
    url_builder.py       # Centralized URL construction
    routers/             # API route handlers
    models/              # SQLAlchemy ORM models
    schemas/             # Pydantic API schemas
    services/            # Business logic layer
    backends/            # Execution backends (sandbox, etc.)
    mcp/                 # MCP protocol handlers (create, run)
    tasks/               # Background tasks (orchestrator, scheduler)
    middleware/           # Auth, rate limiting, metrics
    core/                # Database, exceptions, security
    sandbox/             # nsjail sandbox utilities
```

## Git Workflow

- Branch: `feature/description`, `fix/description`, `refactor/...`, `docs/...`
- Commits: descriptive, focus on "why" not "what"
- End commits with: `Co-Authored-By: Claude <noreply@anthropic.com>` (or your AI assistant's attribution)

## Common Mistakes to Avoid

- Referencing "proxy" or "gateway" (MCPWorks uses direct HTTPS, no proxy)
- Using "Agentic Services" or "Workflows" as terminology (agents are the product, functions are building blocks)
- Returning verbose tool responses (>1000 tokens) from MCP endpoints
- Skipping usage limit checks before function execution
- Hardcoding pricing, tiers, or infrastructure details in source code

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->

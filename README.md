# MCPWorks API

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![CI](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/actions/workflows/ci.yml/badge.svg)](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/actions/workflows/ci.yml)

**The open-source standard for token-efficient AI agents.**

MCPWorks is a platform for hosting AI agent functions with 70-98% token savings through sandboxed code execution. Data stays in the sandbox, never enters the AI context window — dramatically reducing costs and improving performance.

## Key Features

- **Code Execution Sandbox** — Run Python and TypeScript in nsjail-isolated sandboxes with namespace, cgroup, and seccomp protection
- **Namespace-based Function Hosting** — Organize functions into services within namespaces, each with its own MCP endpoint
- **Autonomous Agent Runtime** — Agents with scheduling, persistent state, webhooks, Discord integration, and AI orchestration
- **BYOAI (Bring Your Own AI)** — No vendor lock-in. Use Claude, GPT, Gemini, or any OpenAI-compatible provider
- **MCP Protocol Native** — Full Model Context Protocol support with `{ns}.create.mcpworks.io` and `{ns}.run.mcpworks.io` endpoints
- **Architectural Compliance** — GDPR/SOX compliance by design, not bolt-on

## Architecture

```
Client (Claude, GPT, etc.)
    |
    v
*.create.mcpworks.io  ──>  Create Handler  ──>  Manage functions, agents, state
*.run.mcpworks.io     ──>  Run Handler     ──>  Execute functions in sandbox
api.mcpworks.io       ──>  REST API        ──>  Auth, accounts, usage, admin
```

**Stack:** Python 3.11+ / FastAPI / SQLAlchemy (async) / PostgreSQL / Redis / nsjail

## Quick Start

### Self-Hosted (Docker Compose)

```bash
git clone https://github.com/MCPWorks-Technologies-Inc/mcpworks-api.git
cd mcpworks-api

# Generate JWT signing keys
mkdir -p keys
openssl ecparam -genkey -name prime256v1 -noout -out keys/private.pem
openssl ec -in keys/private.pem -pubout -out keys/public.pem

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start everything
docker compose up -d

# Run database migrations
docker compose exec api alembic upgrade head
```

The API is now available at `http://localhost:8001`.

See [docs/SELF-HOSTING.md](docs/SELF-HOSTING.md) for detailed deployment instructions.

### MCPWorks Cloud

Use the managed service at [mcpworks.io](https://mcpworks.io) — no infrastructure to manage.

## Development

```bash
# Create virtual environment
python3 -m venv venv && source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Start infrastructure
docker compose up -d postgres redis

# Run migrations
alembic upgrade head

# Start development server
uvicorn mcpworks_api.main:app --reload --port 8000

# Run tests
pytest tests/ -v

# Lint
ruff check src/
```

## How It Works

### Token Efficiency

Traditional AI tool calls return full results into the context window, consuming thousands of tokens. MCPWorks keeps data in the sandbox:

1. AI writes code that calls namespace functions
2. Code executes in an isolated sandbox
3. Functions fetch/process data inside the sandbox
4. Only the final result (tens of tokens) returns to the AI

Result: 70-98% fewer tokens per operation.

### Function Backends

| Backend | Description | Status |
|---------|-------------|--------|
| Code Sandbox (nsjail) | LLM-authored Python/TypeScript in secure sandbox | Production |
| Activepieces | Visual workflow builder | Production |
| MCP Server Plugin | Host any third-party MCP server | Planned (A1) |

### Subscription Tiers (Cloud)

| Tier | Price | Agents | Executions/Month |
|------|-------|--------|------------------|
| 14-Day Pro Trial | Free | 5 | 125,000 |
| Pro | $179/mo | 5 | 250,000 |
| Enterprise | $599/mo | 20 | 1,000,000 |
| Community (Self-Hosted) | Free | Unlimited | Unlimited |

## Project Structure

```
src/mcpworks_api/
    main.py           # FastAPI application
    config.py         # Settings (Pydantic BaseSettings)
    routers/          # REST API route handlers
    models/           # SQLAlchemy ORM models
    schemas/          # Pydantic API schemas
    services/         # Business logic
    backends/         # Execution backends (sandbox, activepieces)
    mcp/              # MCP protocol handlers
    tasks/            # Background tasks (orchestrator, scheduler)
    middleware/       # Auth, rate limiting, metrics
    core/             # Database, exceptions, security
    sandbox/          # nsjail sandbox utilities
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and PR process.

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) for responsible disclosure instructions. Do not open public issues for security vulnerabilities.

## License

MCPWorks API is licensed under the [Business Source License 1.1](LICENSE).

- **Use**: Free for non-production use. Production use for internal business purposes is permitted
- **Change Date**: 2030-03-22
- **Change License**: Apache License 2.0

After the Change Date, the code automatically converts to Apache 2.0.

See [LICENSE](LICENSE) for full terms.

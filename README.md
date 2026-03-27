# MCPWorks API

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![CI](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/actions/workflows/ci.yml/badge.svg)](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/actions/workflows/ci.yml)

**The open-source standard for token-efficient AI agents.**

MCPWorks is a platform for hosting AI agent functions with 70-98% token savings through sandboxed code execution. Data stays in the sandbox, never enters the AI context window — dramatically reducing costs and improving performance.

## Why MCPWorks?

Traditional AI tool calls return full results into the context window:

```
Without MCPWorks:
  AI asks: "Get all 500 leads from the database"
  → Tool returns 500 lead records into context → 47,000 tokens consumed
  → AI summarizes → 200 token response
  Total: ~47,200 tokens

With MCPWorks:
  AI writes: "from functions import store_lead; result = store_lead(action='stats')"
  → Code runs in sandbox → data never enters context
  → Only the result returns → 85 tokens consumed
  Total: ~300 tokens (99.4% savings)
```

The AI writes code that calls your functions inside a secure sandbox. Data stays in the sandbox. Only the final answer comes back.

## Key Features

- **Code Execution Sandbox** — Run Python and TypeScript in nsjail-isolated sandboxes with namespace, cgroup, and seccomp protection
- **Namespace-based Function Hosting** — Organize functions into services within namespaces, each with its own MCP endpoint
- **Autonomous Agent Runtime** — Agents with scheduling, persistent state, webhooks, Discord integration, and AI orchestration
- **BYOAI (Bring Your Own AI)** — No vendor lock-in. Use Claude, GPT, Gemini, or any OpenAI-compatible provider
- **MCP Protocol Native** — Full Model Context Protocol support with `{ns}.create.{domain}` and `{ns}.run.{domain}` endpoints
- **Architectural Compliance** — GDPR/SOX compliance by design, not bolt-on

## Architecture

```
Client (Claude, GPT, etc.)
    |
    v
*.create.{domain}  ──>  Create Handler  ──>  Manage functions, agents, state
*.run.{domain}     ──>  Run Handler     ──>  Execute functions in sandbox
api.{domain}       ──>  REST API        ──>  Auth, accounts, usage, admin
```

**Stack:** Python 3.11+ / FastAPI / SQLAlchemy (async) / PostgreSQL / Redis / nsjail

## Quick Start

### Self-Hosted (Docker Compose)

```bash
git clone https://github.com/MCPWorks-Technologies-Inc/mcpworks-api.git
cd mcpworks-api

# Configure environment
cp .env.self-hosted.example .env
# Edit .env — set BASE_DOMAIN, ENCRYPTION_KEK_B64, ADMIN_EMAILS

# Generate JWT signing keys
mkdir -p keys
openssl ecparam -genkey -name prime256v1 -noout -out keys/private.pem
openssl ec -in keys/private.pem -pubout -out keys/public.pem

# Start everything (migrations run automatically on startup)
docker compose -f docker-compose.self-hosted.yml up -d
```

The API is now available at `https://api.yourdomain.com/v1/health` (Caddy handles TLS automatically).

See [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md) for the full walkthrough — from deployment to running your first function.

## Development

```bash
# Create virtual environment
python3 -m venv venv && source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Start database and cache (Docker)
docker compose up -d postgres redis

# Run migrations
alembic upgrade head

# Start API server (locally, not in Docker)
uvicorn mcpworks_api.main:app --reload --port 8000

# Run tests
pytest tests/ -v

# Lint
ruff check src/
```

## Who Is This For?

- **AI agent developers** building tools for Claude, GPT, or other LLMs
- **Teams running AI in production** who need to control token costs
- **Companies with compliance requirements** (GDPR, SOX) who need architectural guarantees
- **Anyone self-hosting AI infrastructure** who wants an open-source foundation

The self-hosted community edition is free with no limits.

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

## Community

- [LinkedIn](https://www.linkedin.com/company/mcpworks/)
- [Bluesky](https://bsky.app/profile/mcpworks.io)
- [YouTube](https://www.youtube.com/@MCPWorks)
- [GitHub Discussions](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/discussions)

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) for responsible disclosure instructions. Do not open public issues for security vulnerabilities.

## Versioning

MCPWorks follows [Semantic Versioning](https://semver.org/). The public API surface
includes REST endpoints, MCP protocol behavior, Docker Compose configuration, and
database migration compatibility.

**Current status: pre-1.0.** The project is functional and deployed in production, but
the API surface is still evolving. Minor releases (0.x.0) may include breaking changes,
always documented in the [CHANGELOG](CHANGELOG.md) with migration instructions. Patch
releases (0.1.x) are safe to pull without breaking existing deployments.

Pin to a specific version in production. Read the CHANGELOG before upgrading across
minor versions. See [Releases](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/releases)
for release notes and Docker images.

## License

MCPWorks API is licensed under the [Business Source License 1.1](LICENSE).

- **Use**: Free for non-production use. Production use for internal business purposes is permitted
- **Change Date**: 2030-03-22
- **Change License**: Apache License 2.0

After the Change Date, the code automatically converts to Apache 2.0.

See [LICENSE](LICENSE) for full terms.

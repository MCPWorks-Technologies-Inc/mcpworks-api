# MCPWorks

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![CI](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/actions/workflows/ci.yml/badge.svg)](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/actions/workflows/ci.yml)

**Cut your AI agent token costs by 70-98%.**

AI tool calls return entire datasets into the context window. A 500-row query becomes 47,000 tokens. MCPWorks runs your code in a secure sandbox instead — data stays in the sandbox, only the answer comes back.

```
Before:  AI calls tool → 500 records enter context → 47,000 tokens → AI summarizes → 200 token answer
After:   AI writes code → runs in sandbox → data never enters context → 300 tokens total
```

Self-host with `docker compose up` or use [MCPWorks Cloud](https://mcpworks.io).

## Quick Start

```bash
git clone https://github.com/MCPWorks-Technologies-Inc/mcpworks-api.git
cd mcpworks-api
cp .env.self-hosted.example .env
# Edit .env: set BASE_DOMAIN, generate ENCRYPTION_KEK_B64

mkdir -p keys
openssl ecparam -genkey -name prime256v1 -noout -out keys/private.pem
openssl ec -in keys/private.pem -pubout -out keys/public.pem

docker compose -f docker-compose.self-hosted.yml up -d
```

Health check: `curl https://api.yourdomain.com/v1/health`

Full guide: [docs/SELF-HOSTING.md](docs/SELF-HOSTING.md)

## How It Works

```
Claude / GPT / any LLM
    |
    | "from functions import query_leads; result = query_leads(tier='hot')"
    v
MCPWorks Sandbox (nsjail)
    |  Data queried, filtered, summarized inside sandbox
    |  Only the result exits
    v
{"hot_leads": 12, "top": "Acme Corp"}  ← 85 tokens, not 47,000
```

The AI writes Python or TypeScript. MCPWorks executes it in an isolated sandbox with access to your functions. The full dataset never enters the AI context window.

## Features

| Feature | What it does |
|---------|-------------|
| **Secure Sandbox** | nsjail isolation: Linux namespaces, cgroups, seccomp. User code runs with zero privileges. |
| **Token Efficiency** | 70-98% fewer tokens per operation. Data stays in sandbox, only results return. |
| **Agent Runtime** | Autonomous agents with scheduling, persistent state, webhooks, and AI orchestration. BYOAI — use any provider. |
| **Function Hosting** | Organize Python/TypeScript functions into services. Each namespace gets its own MCP endpoint. |
| **Access Control** | Per-agent function and state restrictions with glob patterns. Deny-takes-precedence. |
| **Self-Hosted** | `docker compose up` with bundled PostgreSQL, Redis, and Caddy. No external dependencies. |
| **MCP Native** | Full Model Context Protocol support. Works with Claude Desktop, Cursor, and any MCP client. |

## Stack

Python 3.11 / FastAPI / SQLAlchemy (async) / PostgreSQL / Redis / nsjail

## Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
docker compose up -d postgres redis
alembic upgrade head
uvicorn mcpworks_api.main:app --reload --port 8000
pytest tests/ -v
```

## Project Structure

```
src/mcpworks_api/
    main.py           # FastAPI application
    mcp/              # MCP protocol handlers (create, run, agent)
    backends/         # Execution backends (nsjail sandbox)
    services/         # Business logic
    models/           # SQLAlchemy ORM models
    tasks/            # Agent orchestrator, scheduler
    middleware/       # Auth, rate limiting, routing
    core/             # Security, encryption, access control
    sandbox/          # Sandbox configuration, package registry
```

## Community

- [LinkedIn](https://www.linkedin.com/company/mcpworks/)
- [Bluesky](https://bsky.app/profile/mcpworks.io)
- [YouTube](https://www.youtube.com/@MCPWorks)
- [GitHub Discussions](https://github.com/MCPWorks-Technologies-Inc/mcpworks-api/discussions)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and PR process.

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) for responsible disclosure. Do not open public issues for security vulnerabilities.

## License

[Business Source License 1.1](LICENSE) — free for non-production use, production use for internal business purposes permitted. Converts to Apache 2.0 on 2030-03-22.

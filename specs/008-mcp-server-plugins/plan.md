# Implementation Plan: Third-Party MCP Server Integration

**Branch**: `008-mcp-server-plugins` | **Date**: 2026-03-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/008-mcp-server-plugins/spec.md`

## Summary

Namespace-scoped third-party MCP server integration with encrypted credentials, LLM-tunable settings, sandbox-callable tool wrappers via internal proxy, and console UI. RemoteMCP is a parallel concept to Services within a namespace — external MCP servers sit alongside native services, and their tools are callable from the code sandbox with the same token efficiency.

## Technical Context

**Language/Version**: Python 3.11+ (existing codebase)
**Primary Dependencies**: FastAPI (existing), MCP Python SDK (existing — `mcp[http]`), structlog (existing)
**Storage**: PostgreSQL (existing — new `namespace_mcp_servers` table with encrypted credentials + settings/env JSONB), Redis (existing — connection pool metadata)
**Testing**: pytest (existing)
**Target Platform**: Linux server (Docker container)
**Project Type**: Single backend project (extends existing mcpworks-api)
**Performance Goals**: Proxy latency < 50ms overhead; tool discovery < 5s; persistent connections with 5-min TTL
**Constraints**: MCP proxy runs in API server process (no sidecar); connection pool is in-memory per-worker; stdio transport restricted to self-hosted
**Scale/Scope**: Up to 20 MCP servers per namespace, up to 200 tools per server

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec complete with 5 clarifications resolved |
| II. Token Efficiency | PASS | Code-mode wrapping means data stays in sandbox. Tool wrappers ~15-20 tokens each. Full schemas only on demand. |
| III. Transaction Safety | PASS | Credential encryption uses existing KEK/DEK. Proxy validates execution is active before routing. Settings changes are atomic JSONB updates. |
| IV. Provider Abstraction | PASS | MCP protocol is the abstraction — any MCP-compliant server works. No provider-specific code. |
| V. API Contracts & Tests | PASS | 11 MCP tools with defined schemas. Unit + integration + E2E test plan in spec. |

| Quality Standard | Status | Notes |
|-----------------|--------|-------|
| Code Quality | PASS | Follows existing patterns (type hints, ruff, black) |
| Documentation | PASS | Console UI + docstring discovery + describe_mcp_server tool |
| Performance | PASS | Persistent connection pool, configurable limits per server |
| Security | PASS | Credentials encrypted, never in sandbox, proxy validates namespace scoping |

**Gate: PASSED** — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/008-mcp-server-plugins/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── mcp-tools.md     # MCP tool contracts
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── models/
│   └── namespace_mcp_server.py     # New: NamespaceMcpServer model
├── services/
│   └── mcp_server.py               # New: registry CRUD, discovery, settings, env vars
├── schemas/
│   └── mcp_server.py               # New: Pydantic schemas for responses
├── core/
│   ├── mcp_client.py               # Modified: refactor to read from NamespaceMcpServer
│   └── mcp_proxy.py                # New: internal proxy logic (bridge key → namespace → route)
├── mcp/
│   ├── create_handler.py           # Modified: add 11 new tool handlers
│   ├── tool_registry.py            # Modified: add MCP_SERVER_TOOLS group
│   └── code_mode.py                # Modified: inject mcp__ wrappers in functions package
├── api/v1/
│   └── mcp_proxy.py                # New: /v1/internal/mcp-proxy endpoint
├── static/
│   └── console.html                # Modified: add Remote MCP Servers section

alembic/versions/
└── YYYYMMDD_000001_add_namespace_mcp_servers.py

tests/
├── unit/
│   ├── test_mcp_server_service.py  # Registry CRUD, settings, env vars
│   └── test_mcp_proxy.py           # Proxy routing, namespace scoping, bridge key
└── integration/
    └── test_mcp_server_e2e.py      # Add server → discover tools → call from sandbox
```

**Structure Decision**: Extends existing layout. Core proxy logic separated from HTTP endpoint. Service layer handles all DB operations. `McpServerPool` refactored to read from new model instead of agent JSONB.

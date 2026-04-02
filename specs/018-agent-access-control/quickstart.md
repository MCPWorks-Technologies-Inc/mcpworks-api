# Quickstart: Per-Agent Access Control

## Overview

Per-agent access control lets namespace owners restrict which functions and state keys each agent can access. Rules use fnmatch glob patterns and follow deny-takes-precedence semantics.

## Key Files

| File | Purpose |
|------|---------|
| `src/mcpworks_api/core/agent_access.py` | Rule evaluation logic (new) |
| `src/mcpworks_api/models/agent.py` | Agent model — new `access_rules` JSONB column |
| `src/mcpworks_api/mcp/create_handler.py` | Management tools + state enforcement |
| `src/mcpworks_api/mcp/run_handler.py` | Function call enforcement |
| `src/mcpworks_api/mcp/tool_registry.py` | Tool definitions for new MCP tools |
| `alembic/versions/xxx_add_agent_access_rules.py` | Migration |
| `tests/unit/test_agent_access.py` | Unit tests for rule evaluation |

## Development Flow

```bash
# 1. Create migration
alembic revision --autogenerate -m "Add access_rules column to agents"

# 2. Run migration
alembic upgrade head

# 3. Run tests
pytest tests/unit/test_agent_access.py -v

# 4. Full test suite
pytest tests/unit/ -q
```

## Quick Test

After implementation, test via MCP create endpoint:

```
# Add an allow rule
configure_agent_access(agent_name="my-bot", rule={"type": "allow_services", "patterns": ["social", "content"]})

# Verify
list_agent_access_rules(agent_name="my-bot")

# Agent can now only call functions in "social" and "content" services
```

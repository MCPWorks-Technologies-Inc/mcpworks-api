# Quickstart: Execution Debugging

## Key Files

| File | Purpose |
|------|---------|
| `src/mcpworks_api/models/execution.py` | Execution model — add namespace_id, service_name, function_name, execution_time_ms |
| `src/mcpworks_api/mcp/run_handler.py` | Wire execution record creation into dispatch_tool |
| `src/mcpworks_api/api/v1/executions.py` | New REST endpoints for execution queries |
| `src/mcpworks_api/mcp/create_handler.py` | MCP tools: list_executions, describe_execution |
| `src/mcpworks_api/mcp/tool_registry.py` | Tool definitions |
| `src/mcpworks_api/services/execution.py` | New service for execution queries |
| `alembic/versions/xxx_add_execution_debugging.py` | Migration |
| `tests/unit/test_execution_service.py` | Unit tests |

## Development Flow

```bash
# 1. Create migration
alembic revision --autogenerate -m "Add execution debugging columns and indexes"

# 2. Run migration
alembic upgrade head

# 3. Run tests
pytest tests/unit/test_execution_service.py -v

# 4. Full suite
pytest tests/unit/ -q
```

## Quick Test

After implementation:

```bash
# Execute a function
curl -X POST https://api.example.com/mcp/run/myns -d '...'

# Query execution history
curl https://api.example.com/v1/executions?namespace=myns&status=failed

# Get execution detail
curl https://api.example.com/v1/executions/{execution_id}
```

Or via MCP tools:
```
list_executions(service="social", function="post-to-bluesky", status="failed")
describe_execution(execution_id="...")
```

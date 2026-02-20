# Quickstart: Environment Variable Passthrough

**Feature**: 002-env-passthrough

## For Users (Function Consumers)

### 1. Encode your env vars

```bash
export MCPWORKS_ACME_ENV=$(echo -n '{"OPENAI_API_KEY":"sk-proj-..."}' | base64 -w0)
```

### 2. Configure your MCP client

In `.mcp.json` (Claude Code) or `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "acme": {
      "type": "http",
      "url": "https://acme.run.mcpworks.io/mcp",
      "headers": {
        "Authorization": "Bearer ${MCPWORKS_API_KEY}",
        "X-MCPWorks-Env": "${MCPWORKS_ACME_ENV}"
      }
    }
  }
}
```

### 3. Use functions normally

Functions that need env vars just work. If something's missing, you get a clear error telling you exactly what to add.

## For Developers (Function Authors)

### 1. Declare env requirements when creating a function

```
make_function:
  service: tools
  name: search
  backend: code_sandbox
  required_env: ["OPENAI_API_KEY"]
  optional_env: ["DEBUG"]
  code: |
    import os
    import openai
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    result = client.chat.completions.create(...)
```

### 2. Access env vars in your code

```python
import os

api_key = os.environ["OPENAI_API_KEY"]     # Required - always present
debug = os.environ.get("DEBUG", "false")    # Optional - may be absent
```

### 3. Check status with _env_status

AI assistants can call `_env_status` to see what's configured and what's missing.

## For Implementers

### File change overview

| File | What changes |
|------|-------------|
| `src/mcpworks_api/mcp/env_passthrough.py` | NEW — header parsing, validation, blocklist |
| `src/mcpworks_api/mcp/transport.py` | Extract header in `call_tool()`, pass down |
| `src/mcpworks_api/mcp/run_handler.py` | Filter env vars, `_env_status` tool, description augmentation |
| `src/mcpworks_api/backends/base.py` | Add `sandbox_env` param to `execute()` |
| `src/mcpworks_api/backends/sandbox.py` | Write `.sandbox_env.json` to exec_dir |
| `src/mcpworks_api/models/function_version.py` | Add `required_env`/`optional_env` columns |
| `src/mcpworks_api/schemas/function.py` | Add env fields to create/response schemas |
| `deploy/nsjail/spawn-sandbox.sh` | Copy `.sandbox_env.json` into workspace |
| `deploy/nsjail/execute.py` | Read env file, inject `os.environ`, delete file |
| `alembic/versions/...` | Migration for new columns |

### Dev mode testing

```bash
# Set env and run API locally
export SANDBOX_DEV_MODE=true
uvicorn mcpworks_api.main:app --reload --port 8000

# Test with curl (base64-encode your env vars)
ENV=$(echo -n '{"TEST_KEY":"test_value"}' | base64 -w0)
curl -X POST https://acme.run.mcpworks.io/mcp \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-MCPWorks-Env: $ENV" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"tools.test","arguments":{}},"id":1}'
```

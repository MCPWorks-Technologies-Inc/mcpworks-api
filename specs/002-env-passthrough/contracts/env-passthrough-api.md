# API Contract: Environment Variable Passthrough

**Feature**: 002-env-passthrough
**Date**: 2026-02-19

## 1. Header Contract

### X-MCPWorks-Env Header

**Direction**: Client → Server (on every MCP HTTP request)
**Encoding**: Base64url-encoded JSON object
**Max decoded size**: 32 KB
**Optional**: Yes (absent header = empty env dict)

**Decoded payload schema**:
```json
{
  "type": "object",
  "additionalProperties": {
    "type": "string",
    "maxLength": 8192
  },
  "maxProperties": 64
}
```

**Key validation**:
- Pattern: `^[A-Z][A-Z0-9_]{0,127}$`
- Blocked exact: `PATH`, `HOME`, `USER`, `SHELL`, `LANG`, `LC_ALL`, `LC_CTYPE`, `TMPDIR`, `TMP`, `TEMP`, `DISPLAY`, `HOSTNAME`, `IFS`
- Blocked prefix: `LD_`, `PYTHON`, `NSJAIL`, `SSL_`, `MCPWORKS_INTERNAL_`
- Reserved prefix: `MCPWORKS_` (platform use only)

**Value validation**:
- Must be string type
- Max 8 KB per value
- No null bytes (`\x00`)

---

## 2. Function Declaration Contract

### Create/Update Function (via MCP create endpoint)

Existing `make_function` and `update_function` tools gain two optional fields:

```json
{
  "name": "make_function",
  "inputSchema": {
    "type": "object",
    "properties": {
      "service": { "type": "string" },
      "name": { "type": "string" },
      "backend": { "type": "string" },
      "code": { "type": "string" },
      "required_env": {
        "type": "array",
        "items": { "type": "string", "pattern": "^[A-Z][A-Z0-9_]{0,127}$" },
        "maxItems": 20,
        "description": "Environment variables required for execution"
      },
      "optional_env": {
        "type": "array",
        "items": { "type": "string", "pattern": "^[A-Z][A-Z0-9_]{0,127}$" },
        "maxItems": 20,
        "description": "Optional environment variables"
      }
    }
  }
}
```

### Function Version Response

Existing `describe_function` response gains env declarations:

```json
{
  "versions": [
    {
      "version": 3,
      "backend": "code_sandbox",
      "required_env": ["OPENAI_API_KEY"],
      "optional_env": ["DEBUG"],
      "created_at": "2026-02-19T12:00:00Z"
    }
  ]
}
```

---

## 3. Error Responses

### Invalid Header (400)

```json
{
  "error": "invalid_env_header",
  "message": "X-MCPWorks-Env header is not valid base64"
}
```

### Payload Too Large (400)

```json
{
  "error": "env_payload_too_large",
  "message": "Env payload too large (35000 bytes, max 32768)"
}
```

### Blocked Name (400)

```json
{
  "error": "env_name_blocked",
  "message": "Env var name 'PATH' is blocked (system variable)"
}
```

### Missing Required Env Var (tool error, not HTTP error)

Returned as MCP tool result with `isError: true`:

```json
{
  "error": "missing_env",
  "required": ["OPENAI_API_KEY"],
  "provided": [],
  "action": "Add OPENAI_API_KEY to your MCP server X-MCPWorks-Env header"
}
```

---

## 4. Diagnostic Tool Contract

### _env_status Tool

**Available on**: `*.run.mcpworks.io` (run endpoint only)
**Purpose**: Let AI assistants check env var configuration status

**Tool schema**:
```json
{
  "name": "_env_status",
  "description": "Check which environment variables are configured and which are missing for this namespace's functions",
  "inputSchema": {
    "type": "object",
    "properties": {}
  }
}
```

**Response (all configured)**:
```json
{
  "configured": ["OPENAI_API_KEY", "DATABASE_URL"],
  "missing_required": [],
  "missing_optional": ["DEBUG"],
  "functions": {
    "tools.search": {
      "required": ["OPENAI_API_KEY"],
      "optional": ["DEBUG"],
      "status": "ready"
    },
    "tools.hello": {
      "required": [],
      "optional": [],
      "status": "ready"
    }
  }
}
```

**Response (missing required vars)**:
```json
{
  "configured": [],
  "missing_required": ["OPENAI_API_KEY"],
  "missing_optional": ["DEBUG"],
  "functions": {
    "tools.search": {
      "required": ["OPENAI_API_KEY"],
      "optional": ["DEBUG"],
      "status": "missing_env"
    },
    "tools.hello": {
      "required": [],
      "optional": [],
      "status": "ready"
    }
  },
  "note": "Functions with status 'missing_env' will fail. Add missing variables to your MCP server X-MCPWorks-Env header."
}
```

---

## 5. tools/list Enhancement

### Tool Description Augmentation

When a function declares env requirements, they are appended to the tool description:

**Before**:
```json
{
  "name": "tools.search",
  "description": "Search the web using OpenAI embeddings"
}
```

**After**:
```json
{
  "name": "tools.search",
  "description": "Search the web using OpenAI embeddings\n\nRequired env: OPENAI_API_KEY\nOptional env: DEBUG"
}
```

Token overhead: ~15 tokens per function with declarations.

---

## 6. Internal Contracts (Not Client-Facing)

### Backend.execute() Signature Change

```python
async def execute(
    self,
    code: str | None,
    config: dict[str, Any] | None,
    input_data: dict[str, Any],
    account: Account,
    execution_id: str,
    timeout_ms: int = 30000,
    extra_files: dict[str, str] | None = None,
    sandbox_env: dict[str, str] | None = None,  # NEW
) -> ExecutionResult:
```

### Sandbox Env File Format

Written to `{workspace}/.sandbox_env.json`:

```json
{"OPENAI_API_KEY": "sk-proj-...", "DATABASE_URL": "postgres://..."}
```

- Encoding: UTF-8
- Owner: 65534:65534
- Mode: 0600
- Lifetime: Read once by `execute.py`, deleted, tmpfs unmounted on exit

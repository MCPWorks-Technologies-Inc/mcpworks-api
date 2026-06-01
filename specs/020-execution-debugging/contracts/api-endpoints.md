# API Contracts: Execution Debugging

## REST API

### GET /v1/executions

List execution records for the authenticated user's namespaces.

**Query Parameters**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `namespace` | string | No | Filter by namespace name |
| `service` | string | No | Filter by service name |
| `function` | string | No | Filter by function name |
| `status` | string | No | Filter by status (completed, failed, timed_out) |
| `since` | ISO datetime | No | Only executions after this time |
| `until` | ISO datetime | No | Only executions before this time |
| `limit` | int | No | Max results (default 20, max 100) |
| `offset` | int | No | Pagination offset |

**Response** (200):

```json
{
  "executions": [
    {
      "id": "exec-uuid",
      "namespace": "mcpworkssocial",
      "service": "social",
      "function": "post-to-bluesky",
      "version": 2,
      "status": "failed",
      "error_message": "Text is 313 graphemes, max 300",
      "execution_time_ms": 1250,
      "started_at": "2026-04-07T22:59:57Z",
      "completed_at": "2026-04-07T22:59:59Z"
    }
  ],
  "total": 45,
  "limit": 20,
  "offset": 0
}
```

### GET /v1/executions/{execution_id}

Get full execution detail.

**Response** (200):

```json
{
  "id": "exec-uuid",
  "namespace": "mcpworkssocial",
  "service": "social",
  "function": "post-to-bluesky",
  "version": 2,
  "backend": "code_sandbox",
  "status": "failed",
  "input_data": {"text": "..."},
  "result_data": null,
  "error_message": "Text is 313 graphemes, max 300",
  "error_code": null,
  "stdout": "Connecting to Bluesky API...\n",
  "stderr": "ValueError: Text is 313 graphemes, max 300\n",
  "execution_time_ms": 1250,
  "started_at": "2026-04-07T22:59:57Z",
  "completed_at": "2026-04-07T22:59:59Z",
  "created_at": "2026-04-07T22:59:57Z"
}
```

---

## MCP Tools (Create Endpoint)

### list_executions

**Scope**: read

```json
{
  "type": "object",
  "properties": {
    "service": {"type": "string", "description": "Filter by service name"},
    "function": {"type": "string", "description": "Filter by function name"},
    "status": {"type": "string", "enum": ["completed", "failed", "timed_out"], "description": "Filter by status"},
    "limit": {"type": "integer", "description": "Max results (default 20, max 100)"}
  }
}
```

### describe_execution

**Scope**: read

```json
{
  "type": "object",
  "properties": {
    "execution_id": {"type": "string", "description": "Execution UUID"}
  },
  "required": ["execution_id"]
}
```

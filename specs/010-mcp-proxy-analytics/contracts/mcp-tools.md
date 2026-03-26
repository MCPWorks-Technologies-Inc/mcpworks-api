# MCP Tool Contracts: Proxy Analytics

**Feature**: 010-mcp-proxy-analytics
**Tool Group**: ANALYTICS_TOOLS (new)
**Endpoint**: `{namespace}.create.mcpworks.io/mcp`

---

## get_mcp_server_stats

**Description**: Per-tool performance breakdown for an MCP server over a time period.

**Authorization**: Read access.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | yes | MCP server name |
| period | string | no | Time window: `1h`, `24h` (default), `7d`, `30d` |

**Success response** (~200 tokens):
```json
{
  "server": "google-workspace",
  "period": "24h",
  "total_calls": 156,
  "total_errors": 12,
  "error_rate": 0.077,
  "tools": [
    {
      "name": "search_gmail_messages",
      "calls": 47,
      "avg_latency_ms": 340,
      "avg_response_bytes": 85000,
      "avg_response_tokens_est": 21250,
      "error_count": 3,
      "timeout_count": 2,
      "truncation_count": 0,
      "injections_detected": 1
    }
  ]
}
```

---

## get_token_savings_report

**Description**: Namespace-wide token savings — data processed in sandbox vs returned to AI.

**Authorization**: Read access.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| period | string | no | Time window: `1h`, `24h` (default), `7d`, `30d` |

**Success response** (~150 tokens):
```json
{
  "period": "24h",
  "mcp_data_processed_bytes": 12500000,
  "mcp_data_processed_tokens_est": 3125000,
  "result_returned_bytes": 45000,
  "result_returned_tokens_est": 11250,
  "savings_percent": 99.6,
  "top_consumers": [
    {"server": "google-workspace", "tool": "search_gmail", "bytes": 8500000}
  ]
}
```

---

## suggest_optimizations

**Description**: Analyze stats and return actionable recommendations. Optionally probe specific tools for field-level analysis.

**Authorization**: Read access.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | no | Server name (all servers if omitted) |
| probe | array | no | Tool names to live-probe for field-level analysis. Only probe tools safe to call with empty/minimal args. |

**Success response** (~300 tokens):
```json
{
  "suggestions": [
    {
      "type": "redact_fields",
      "server": "google-workspace",
      "tool": "list_events",
      "reason": "Avg response 450KB. Probed fields: 'attendees' (62%), 'description' (18%).",
      "action": "add_mcp_server_rule(name='google-workspace', direction='response', rule={'type': 'redact_fields', 'tools': ['list_events'], 'fields': ['attendees', 'description']})",
      "estimated_savings_percent": 80
    },
    {
      "type": "increase_timeout",
      "server": "slack",
      "tool": "search_messages",
      "reason": "18% timeout rate at 30s. Avg successful latency 22s.",
      "action": "set_mcp_server_setting(name='slack', key='timeout_seconds', value=60)",
      "estimated_impact": "Reduce timeout errors by ~90%"
    }
  ]
}
```

---

## get_function_mcp_stats

**Description**: Per-function MCP usage — calls per execution, bytes consumed, tokens saved.

**Authorization**: Read access.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| service | string | yes | Service name |
| function | string | yes | Function name |
| period | string | no | Time window: `1h`, `24h` (default), `7d`, `30d` |

**Success response** (~100 tokens):
```json
{
  "function": "utils.process-leads",
  "period": "24h",
  "executions": 12,
  "avg_mcp_calls_per_execution": 8.3,
  "avg_mcp_bytes_per_execution": 340000,
  "avg_result_bytes": 1200,
  "avg_tokens_saved": 84700
}
```

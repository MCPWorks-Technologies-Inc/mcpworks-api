# Quickstart: Analytics Token Savings

## What Changed

1. **All executions now tracked** — every function execution records input size, output size, and token savings (previously only MCP-proxy executions were tracked)
2. **REST API endpoints** — analytics data available over HTTP at `/v1/analytics/*`
3. **Platform aggregate** — admin endpoint shows cross-namespace totals at `/v1/admin/analytics/token-savings`

## REST API Usage

### Get your namespace token savings

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.mcpworks.io/v1/analytics/token-savings?namespace=myns&period=30d"
```

Response:
```json
{
  "period": "30d",
  "total_executions": 4521,
  "input_bytes": 12450000,
  "input_tokens_est": 3112500,
  "mcp_data_processed_bytes": 8900000,
  "mcp_data_processed_tokens_est": 2225000,
  "result_returned_bytes": 450000,
  "result_returned_tokens_est": 112500,
  "tokens_saved_est": 3000000,
  "savings_percent": 96.4,
  "top_consumers": [
    {"server": "google-workspace", "tool": "search_gmail_messages", "bytes": 5200000}
  ]
}
```

### Get MCP server stats

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.mcpworks.io/v1/analytics/server-stats/google-workspace?namespace=myns"
```

### Get optimization suggestions

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.mcpworks.io/v1/analytics/suggestions?namespace=myns"
```

### Platform aggregate (admin only)

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "https://api.mcpworks.io/v1/admin/analytics/token-savings?period=30d"
```

## MCP Tools (unchanged)

The existing MCP tools on `/mcp/create/{ns}` continue to work as before:
- `get_token_savings_report` — same data, now includes `input_bytes` and `total_executions`
- `get_mcp_server_stats` — unchanged
- `get_function_mcp_stats` — unchanged
- `suggest_optimizations` — unchanged

## Database Migration

```bash
alembic upgrade head  # Adds input_bytes column to mcp_execution_stats
```

# Quickstart: MCP Proxy Analytics

## Check Server Performance

> "How is the google-workspace MCP server performing over the last 24 hours?"

The AI calls `get_mcp_server_stats` and gets per-tool breakdowns: call counts, latency, response sizes, error rates.

## View Token Savings

> "Show me the token savings report for this namespace"

Returns total data processed in sandbox vs tokens returned to AI, with top consumers listed.

## Get Optimization Suggestions

> "Suggest optimizations for the google-workspace server"

Returns actionable recommendations: redact large fields, increase timeouts, remove unused tools.

### With Live Probing

> "Suggest optimizations for google-workspace, probe the list_events and search_gmail tools"

Makes one real call to each probed tool to analyze response structure. Identifies which fields consume the most bytes and suggests specific `redact_fields` rules.

## Act on Suggestions

The AI can directly apply suggestions using existing tools:

```
"Add a redact_fields rule for list_events on google-workspace to strip attendees and description"
```

```
"Set the timeout for slack to 60 seconds"
```

## Per-Function Stats

> "How many MCP calls does the process-leads function make per execution?"

Returns avg calls per execution, bytes consumed, and tokens saved.

## Implementation Order

1. Database: `mcp_proxy_calls` + `mcp_execution_stats` tables (migration)
2. Models: `McpProxyCall` + `McpExecutionStat` SQLAlchemy models
3. Telemetry capture: async INSERT in `mcp_proxy.py` after each call
4. Execution stats: extend `ExecutionContext` with counters, flush on cleanup
5. Analytics service: aggregation queries + suggestion engine
6. MCP tools: 4 handlers in ANALYTICS_TOOLS group
7. Prometheus metrics: Counter + Histogram objects
8. Cleanup job: APScheduler daily task for 30-day retention
9. Tests

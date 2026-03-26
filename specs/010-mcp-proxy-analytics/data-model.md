# Data Model: MCP Proxy Analytics

**Feature**: 010-mcp-proxy-analytics
**Date**: 2026-03-26

## New Entities

### McpProxyCall

Per-call telemetry record captured asynchronously after each MCP proxy call.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | |
| namespace_id | UUID | FK → namespaces.id, ON DELETE CASCADE | |
| server_name | VARCHAR(63) | NOT NULL | MCP server name |
| tool_name | VARCHAR(255) | NOT NULL | Tool called |
| called_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Call timestamp |
| latency_ms | INTEGER | NOT NULL | Round-trip time to external server |
| response_bytes | INTEGER | NOT NULL | Response size before truncation |
| response_tokens_est | INTEGER | NOT NULL | response_bytes / 4 |
| status | VARCHAR(20) | NOT NULL | success, timeout, error, blocked |
| error_type | VARCHAR(100) | NULLABLE | Error classification |
| truncated | BOOLEAN | NOT NULL, DEFAULT false | Hit response_limit_bytes |
| injections_found | INTEGER | NOT NULL, DEFAULT 0 | Scanner hit count |

**Indexes:**
- `(namespace_id, called_at)` — time-range queries per namespace
- `(namespace_id, server_name, tool_name, called_at)` — per-tool aggregation

### McpExecutionStat

Per-execution summary capturing sandbox-level MCP usage and token savings.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | |
| namespace_id | UUID | FK → namespaces.id, ON DELETE CASCADE | |
| execution_id | VARCHAR(64) | NOT NULL | Sandbox execution ID |
| executed_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| mcp_calls_count | INTEGER | NOT NULL, DEFAULT 0 | Total MCP proxy calls |
| mcp_bytes_total | INTEGER | NOT NULL, DEFAULT 0 | Total response bytes from MCP |
| result_bytes | INTEGER | NOT NULL, DEFAULT 0 | Sandbox result size to AI |
| tokens_saved_est | INTEGER | NOT NULL, DEFAULT 0 | (mcp_bytes - result_bytes) / 4 |

**Indexes:**
- `(namespace_id, executed_at)` — time-range queries

## Modified Entity: ExecutionContext (in-memory)

| Field | Change | Description |
|-------|--------|-------------|
| mcp_calls_count | NEW, int, default 0 | Incremented by proxy on each call |
| mcp_bytes_total | NEW, int, default 0 | Accumulated by proxy on each call |

Flushed to `mcp_execution_stats` table on sandbox cleanup.

## Retention

Both tables: rows older than 30 days deleted by APScheduler daily task (03:00 UTC). Batch delete with LIMIT 10000 per iteration.

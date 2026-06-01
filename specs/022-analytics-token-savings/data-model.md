# Data Model: MCP Proxy Analytics — Token Savings

**Date**: 2026-04-08

## Entity Changes

### McpExecutionStat (MODIFIED)

**Table**: `mcp_execution_stats`
**Change**: Add `input_bytes` column

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| id | UUID | gen | Primary key |
| namespace_id | UUID FK | - | Parent namespace |
| execution_id | String(64) | - | Links to execution record |
| executed_at | DateTime(tz) | now() | Timestamp |
| **input_bytes** | **Integer** | **0** | **NEW: Size of input arguments/code in bytes** |
| mcp_calls_count | Integer | 0 | Number of MCP proxy calls in execution |
| mcp_bytes_total | Integer | 0 | Total bytes from MCP server responses |
| result_bytes | Integer | 0 | Size of result returned to AI |
| tokens_saved_est | Integer | 0 | Estimated tokens saved (derived) |

**Derivation**: `tokens_saved_est = max(0, (max(mcp_bytes_total, input_bytes) - result_bytes)) // 4`

**Index**: Existing `ix_mcp_execution_stats_ns_time` on `(namespace_id, executed_at)` covers all query patterns.

### McpProxyCall (UNCHANGED)

No changes. Existing model captures per-call MCP proxy telemetry.

### TokenSavingsResponse (MODIFIED)

**Schema**: `schemas/analytics.py`
**Change**: Add new fields to response model

| Field | Type | Description |
|-------|------|-------------|
| period | str | Time period queried |
| **total_executions** | **int** | **NEW: Number of executions in period** |
| **input_bytes** | **int** | **NEW: Total input bytes across all executions** |
| **input_tokens_est** | **int** | **NEW: Estimated input tokens (input_bytes // 4)** |
| mcp_data_processed_bytes | int | Total MCP proxy bytes |
| mcp_data_processed_tokens_est | int | MCP bytes as tokens |
| result_returned_bytes | int | Total result bytes |
| result_returned_tokens_est | int | Result bytes as tokens |
| **tokens_saved_est** | **int** | **NEW: Total estimated tokens saved** |
| savings_percent | float | Percentage saved |
| top_consumers | list | Top MCP tools by bytes |

### PlatformTokenSavingsResponse (NEW)

**Schema**: `schemas/analytics.py`

| Field | Type | Description |
|-------|------|-------------|
| period | str | Time period queried |
| total_executions | int | Platform-wide execution count |
| active_namespaces | int | Namespaces with executions in period |
| input_bytes | int | Total input bytes |
| input_tokens_est | int | Input bytes as tokens |
| mcp_data_processed_bytes | int | Total MCP proxy bytes |
| mcp_data_processed_tokens_est | int | MCP bytes as tokens |
| result_returned_bytes | int | Total result bytes |
| result_returned_tokens_est | int | Result bytes as tokens |
| tokens_saved_est | int | Total estimated tokens saved |
| savings_percent | float | Platform-wide savings percentage |
| top_namespaces | list | Top 10 namespaces by tokens saved |

## Migration

**File**: `alembic/versions/20260408_000001_add_input_bytes_to_execution_stats.py`
**Action**: `ALTER TABLE mcp_execution_stats ADD COLUMN input_bytes INTEGER NOT NULL DEFAULT 0`
**Rollback**: `ALTER TABLE mcp_execution_stats DROP COLUMN input_bytes`
**Risk**: Low — additive column with default value, no data migration needed.

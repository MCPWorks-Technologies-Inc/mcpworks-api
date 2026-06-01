# Research: Execution Debugging

## Decision 1: Use Existing Execution Model

**Decision**: Extend the existing `Execution` model in `models/execution.py` rather than creating a new table.

**Rationale**: The model already has the right fields (user_id, function_id, function_version_num, input_data, result_data, error_message, status, timing, backend_metadata). It's just not being used — run_handler.py doesn't create records. Adding a `namespace_id` column and wiring record creation into the dispatch path is simpler than building from scratch.

**Alternatives considered**:
- New `execution_log` table: Rejected — duplicates existing model structure.
- Append-only event log: Overkill for V1. Execution records with JSONB backend_metadata covers most needs.

## Decision 2: Persist stdout/stderr in backend_metadata

**Decision**: Store truncated stdout/stderr in the `backend_metadata` JSONB column.

**Rationale**: stdout/stderr is already captured in `ExecutionResult` from the sandbox backend but discarded after the response. Storing it in `backend_metadata` avoids schema changes and is naturally optional (NULL when not available). Truncate to 4KB per stream to avoid bloat.

**Alternatives considered**:
- Separate `execution_output` table: Overkill for truncated debug output.
- Dedicated `stdout`/`stderr` columns: Adds migration complexity for data that's supplementary.

## Decision 3: Namespace-scoped queries, not user-scoped

**Decision**: Execution queries are scoped to the namespace, not the user. The API endpoint checks namespace ownership.

**Rationale**: Functions belong to namespaces. "Show me failures for social.post-to-bluesky" is a namespace-level query. Adding `namespace_id` to the Execution model enables this without joins through function → namespace.

## Decision 4: MCP tools on create endpoint

**Decision**: Add `list_executions` and `describe_execution` as MCP tools on the create endpoint.

**Rationale**: Consistent with how all management/query tools are exposed. Developers interact through MCP clients, so debugging should be available there.

## Decision 5: Retention via background pruning

**Decision**: A periodic task prunes execution records older than 30 days.

**Rationale**: Without pruning, execution records grow unbounded. 30 days is enough for debugging while keeping storage manageable. Can be made configurable later.

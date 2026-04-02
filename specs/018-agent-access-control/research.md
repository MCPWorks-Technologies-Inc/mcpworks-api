# Research: Per-Agent Access Control

## Decision 1: Storage Strategy for Access Rules

**Decision**: Add a JSONB column `access_rules` on the `agents` table.

**Rationale**: The Agent model already has several JSONB columns (`mcp_servers`, `orchestration_limits`). A single JSONB column is simpler than a separate table and avoids joins for every function call. Rules are small (typically <1KB per agent) and read far more often than written.

**Alternatives considered**:
- Separate `agent_access_rules` table: More normalized but adds a join on every function call and state operation. Rejected for performance.
- Redis-cached separate table: Overcomplicated for the expected rule set size.

**Schema**:
```json
{
  "function_rules": [
    {"id": "r-abc123", "type": "allow_services", "patterns": ["social", "content"]},
    {"id": "r-def456", "type": "deny_functions", "patterns": ["billing.*", "admin.delete_*"]}
  ],
  "state_rules": [
    {"id": "r-ghi789", "type": "allow_keys", "patterns": ["content.*", "cache.*"]},
    {"id": "r-jkl012", "type": "deny_keys", "patterns": ["secrets.*"]}
  ]
}
```

## Decision 2: Enforcement Points

**Decision**: Two enforcement points — one in `RunMCPHandler` for function calls, one in `CreateMCPHandler` for state operations.

**Rationale**: 
- Function calls flow through `RunMCPHandler._execute_function()` (line ~280 in run_handler.py) — this is where we check before `backend.execute()`.
- State operations flow through `CreateMCPHandler._set_agent_state()`, `_get_agent_state()`, `_delete_agent_state()`, `_list_agent_state_keys()` (lines 1438-1489 in create_handler.py).
- The agent identity is available via `_load_agent_context()` which already looks up the Agent by namespace_id.

**Key insight**: The `RunMCPHandler` knows the namespace but doesn't directly know the agent name. It loads agent context via `_load_agent_context()`. For enforcement, we need to load the agent's `access_rules` at the same point and check before dispatch.

## Decision 3: Rule Evaluation Logic

**Decision**: Reuse the `fnmatch` pattern matching from `core/mcp_rules.py`. Create a new `core/agent_access.py` module with a simple evaluate function.

**Rationale**: The existing `mcp_rules.py` uses `fnmatch` for glob matching, which is exactly what we need. However, the rule structure is different enough (per-agent vs per-MCP-server, function/state vs tool) that a separate module is cleaner than extending mcp_rules.py.

**Evaluation order**:
1. If no rules exist → allow (backwards compatible)
2. Check deny rules first — if any match, deny
3. If allow rules exist, check if the resource matches any allow rule — if not, deny
4. If no allow rules exist, allow (only deny rules in effect)

## Decision 4: Agent Identity in RunMCPHandler

**Decision**: Extend `_load_agent_context()` to also return the agent's `access_rules`, or create a separate method `_load_agent_access_rules()`.

**Rationale**: The `_load_agent_context()` already queries the Agent model by namespace_id. We can piggyback on this query to also retrieve `access_rules`. For non-agent namespaces (returns None), no rules apply.

## Decision 5: Function Name Format for Matching

**Decision**: Match against `service_name.function_name` composite pattern for function-level rules, and just `service_name` for service-level rules.

**Rationale**: Functions are identified by service + name in the existing system. The `service.function` dot notation is consistent with how MCP server rules reference tools and is natural for fnmatch glob patterns.

## Decision 6: MCP Tools for Rule Management

**Decision**: Three new tools on the `/mcp/create/` endpoint: `configure_agent_access`, `list_agent_access_rules`, `remove_agent_access_rule`.

**Rationale**: Consistent with existing patterns (`add_mcp_server_rule`, `list_mcp_server_rules`, `remove_mcp_server_rule`). Management goes through the create handler, enforcement happens in the run handler and create handler (for state ops).

# Data Model: MCP Server Cards

## Schema Changes

### Namespace (modified)

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `discoverable` | boolean | `false` | Controls platform-level listing; does NOT affect per-namespace card |

No new tables. Server cards are generated dynamically from existing `namespaces`, `namespace_services`, `functions`, and `function_versions` tables.

## Response Entities (not persisted)

### Namespace Server Card

Generated per-request from database. Fields:

| Field | Source | Notes |
|-------|--------|-------|
| `schema_version` | Hardcoded | `"0.1.0"` — bumped when aligning with formal spec |
| `name` | `namespace.name` | |
| `description` | `namespace.description` | Nullable |
| `protocol_version` | Hardcoded | `"2024-11-05"` — current MCP protocol version |
| `transports` | Hardcoded | `[{"type": "https+sse"}]` |
| `endpoints.create` | Computed | `https://{name}.create.mcpworks.io/mcp` |
| `endpoints.run` | Computed | `https://{name}.run.mcpworks.io/mcp` |
| `tools` | Query | Array of public_safe functions with name, description, input_schema |
| `private_tool_count` | Query | Count of functions where `public_safe = false` |
| `service_count` | Query | Count of services in namespace |
| `total_tool_count` | Query | Total functions (public + private) |

### Platform Server Card

| Field | Source | Notes |
|-------|--------|-------|
| `schema_version` | Hardcoded | `"0.1.0"` |
| `platform` | Hardcoded | `"mcpworks"` |
| `description` | Hardcoded | Platform tagline |
| `namespaces` | Query | Array of discoverable namespaces |
| `namespaces[].name` | `namespace.name` | |
| `namespaces[].description` | `namespace.description` | |
| `namespaces[].server_card_url` | Computed | `https://{name}.create.mcpworks.io/.well-known/mcp.json` |
| `namespaces[].tool_count` | Query | Total function count per namespace |

## Query Patterns

1. **Namespace card**: Single query joining `namespaces` → `functions` → `function_versions` filtered by `namespace.name` and `public_safe = true` for tool details, plus a count query for private tools.
2. **Platform card**: Single query on `namespaces` where `discoverable = true`, with a subquery count of functions per namespace.

# Data Model: Third-Party MCP Server Integration

**Feature**: 008-mcp-server-plugins
**Date**: 2026-03-26

## New Entities

### NamespaceMcpServer

Namespace-level registry of external MCP servers. Parallel to NamespaceService (not a subtype).

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | |
| namespace_id | UUID | FK → namespaces.id, ON DELETE CASCADE | Owning namespace |
| name | VARCHAR(63) | NOT NULL | Server identifier, unique per namespace, DNS-safe |
| transport | VARCHAR(20) | NOT NULL, DEFAULT 'streamable_http' | `sse`, `streamable_http`, `stdio` |
| url | VARCHAR(500) | NULLABLE | Endpoint URL (plaintext). Required for sse/streamable_http. |
| command | VARCHAR(500) | NULLABLE | Binary path. Required for stdio. |
| command_args | JSONB | NULLABLE | Arguments for stdio command |
| headers_encrypted | BYTEA | NULLABLE | Auth headers (JSON), encrypted with DEK |
| headers_dek_encrypted | BYTEA | NULLABLE | DEK encrypted with KEK |
| settings | JSONB | NOT NULL, DEFAULT '{}' | LLM-tunable settings (see below) |
| env_vars | JSONB | NOT NULL, DEFAULT '{}' | User-defined key-value pairs |
| tool_schemas | JSONB | NOT NULL, DEFAULT '[]' | Cached tool list from discovery |
| tool_count | INTEGER | NOT NULL, DEFAULT 0 | Cached count |
| enabled | BOOLEAN | NOT NULL, DEFAULT true | LLM can disable without removing |
| last_connected_at | TIMESTAMPTZ | NULLABLE | Last successful connection |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes**:
- UNIQUE(namespace_id, name)
- INDEX on namespace_id

**Settings schema** (JSONB with defaults applied at read time):
```json
{
    "response_limit_bytes": 1048576,
    "timeout_seconds": 30,
    "max_calls_per_execution": 50,
    "retry_on_failure": true,
    "retry_count": 2
}
```

**Relationships**:
- Namespace has zero to many NamespaceMcpServer
- CASCADE delete: removing namespace removes all its MCP servers

### Modified: Agent

| Field | Change | Description |
|-------|--------|-------------|
| mcp_servers | DEPRECATED | Stop reading in orchestrator. Leave nullable. Drop in future migration. |
| mcp_server_names | NEW, ARRAY(VARCHAR) | List of NamespaceMcpServer names this agent can access |

## In-Memory Structures

### Execution Token Registry

Maps bridge key tokens to namespace context for proxy authorization.

```python
# Stored in Redis or in-memory dict (per-worker)
exec_token_registry: dict[str, ExecutionContext] = {}

@dataclass
class ExecutionContext:
    execution_id: str
    namespace_id: UUID
    namespace_name: str
    created_at: datetime
    # Auto-expires when sandbox exits (cleanup callback)
```

Set at sandbox creation time (in `_execute_nsjail`). Cleared at sandbox cleanup. The MCP proxy looks up `exec_token → ExecutionContext` to resolve the namespace.

### Connection Pool

```python
# Per-worker, keyed by (namespace_id, server_name)
mcp_connections: dict[tuple[UUID, str], PooledConnection] = {}

@dataclass
class PooledConnection:
    session: ClientSession
    connected_at: datetime
    last_used_at: datetime
    settings: dict  # Cached from DB at connect time
```

TTL: 5 minutes from `last_used_at`. Evicted lazily (checked on next access).

## Entity Relationship

```
Namespace (1) ──── (0..N) NamespaceMcpServer
    │                        │
    │                        ├── settings (JSONB)
    │                        ├── env_vars (JSONB)
    │                        ├── tool_schemas (JSONB, cached)
    │                        └── headers (encrypted)
    │
    ├──── (0..N) NamespaceService
    │               └──── (0..N) Function
    │                       └──── (0..N) FunctionVersion
    │
    └──── (0..N) Agent
                    └── mcp_server_names: ["slack", "google-workspace"]
                        (references NamespaceMcpServer by name)
```

## Tool Schema Cache Format

Stored in `NamespaceMcpServer.tool_schemas` JSONB:

```json
[
    {
        "name": "send_message",
        "description": "Send a message to a Slack channel",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel ID"},
                "text": {"type": "string", "description": "Message text"}
            },
            "required": ["channel", "text"]
        }
    },
    {
        "name": "list_channels",
        "description": "List all channels in the workspace",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]
```

Used by:
1. `generate_functions_package()` — to build wrapper function signatures
2. `describe_mcp_server` tool — to return tool list to user
3. `list_mcp_servers` tool — to return tool counts

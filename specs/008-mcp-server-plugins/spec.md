# Third-Party MCP Server Integration - Specification

**Version:** 0.1.0 (Draft)
**Created:** 2026-03-26
**Status:** Draft
**Spec Author:** Simon Carr
**Feature Branch:** `008-mcp-server-plugins`

---

## 1. Overview

### 1.1 Purpose

Allow MCPWorks namespaces to integrate any third-party MCP server (Google Workspace, Slack, GitHub, etc.) as a first-class resource. MCP server tools become callable from the code execution sandbox with the same token efficiency as native functions — the AI writes code that calls MCP tools, data stays in the sandbox, only the result returns.

### 1.2 User Value

Today, connecting an AI assistant to a third-party MCP server means the full tool responses flow through the AI's context window. A Slack `list_channels` call returns 200 channels × 500 tokens each = 100,000 tokens consumed. With MCPWorks, the AI writes `from functions import mcp__slack__list_channels; result = mcp__slack__list_channels()` — the data is processed in the sandbox and only the filtered result returns.

This also solves the "MCP server sprawl" problem: instead of configuring 10 MCP servers on every AI assistant, users configure them once on their MCPWorks namespace and access them through the single MCPWorks MCP connection.

### 1.3 Success Criteria

**This spec is successful when:**
- [ ] A user can add a third-party MCP server to their namespace with a single MCP tool call
- [ ] All tools from the added MCP server are discoverable and callable from the code execution sandbox
- [ ] MCP server credentials (API keys, OAuth tokens) are encrypted at rest and never exposed to sandbox code
- [ ] Token savings from code-mode wrapping apply to third-party MCP tool calls (data stays in sandbox)
- [ ] The existing per-agent `mcp_servers` JSONB column is migrated to the new encrypted per-namespace model

### 1.4 Scope

**In Scope:**
- Per-namespace MCP server registry (add, remove, list, update)
- Encrypted credential storage for MCP server auth (headers, tokens)
- Tool discovery: connect to MCP server, list tools, cache schemas
- Sandbox integration: generate callable wrappers in the `functions` package
- Internal MCP proxy endpoint for sandbox → API → MCP server routing
- Migration of existing `agent.mcp_servers` JSONB to new model
- Agent integration: agents select which namespace MCP servers to use
- Support for SSE, Streamable HTTP, and stdio transports

**Out of Scope:**
- OAuth flows for MCP servers (users provide tokens directly; OAuth integration is a future spec)
- MCP server hosting (MCPWorks doesn't run the MCP server, just connects to it)
- MCP resource support (only tools in this spec; resources are a future extension)
- MCP prompt support (only tools)
- Automatic tool schema updates (manual refresh via `refresh_mcp_server`)
- Billing/metering for MCP server calls (uses existing execution metering)

---

## 2. User Scenarios

### 2.1 Primary Scenario: Add a Slack MCP Server

**Actor:** Developer using Claude Code with MCPWorks
**Goal:** Make Slack tools available to all functions and agents in their namespace
**Context:** Developer has a Slack MCP server running at `https://slack-mcp.example.com/mcp` with an API token

**Workflow:**
1. Developer asks: "Add the Slack MCP server to my namespace at `https://slack-mcp.example.com/mcp` with token `xoxb-...`"
2. AI calls `add_mcp_server` with name `slack`, URL, and token
3. MCPWorks connects to the MCP server, discovers 15 tools, encrypts the token, stores the config
4. MCPWorks returns: "Added MCP server 'slack' with 15 tools: send_message, list_channels, ..."
5. Developer writes code that uses Slack tools:
   ```python
   from functions import mcp__slack__list_channels
   channels = mcp__slack__list_channels()
   result = [c for c in channels if c['is_private']]
   ```
6. The sandbox calls back to MCPWorks, which authenticates to Slack, returns the channel list
7. The sandbox filters locally, returns only private channels — Slack's full response never enters AI context

**Success:** Developer can call any Slack tool from sandbox code. Token usage is the code + result, not the full Slack API response.
**Failure:** Connection fails with clear error. Invalid token caught at add time, not at first call.

### 2.2 Secondary Scenario: Use MCP Server Tools in an Agent

**Actor:** Developer configuring an autonomous agent
**Goal:** Agent can use Google Workspace MCP tools during its runs
**Context:** Namespace already has a Google Workspace MCP server configured

**Workflow:**
1. Developer asks: "Configure my report-generator agent to use the google-workspace MCP server"
2. AI calls `configure_agent_mcp` with agent name and server list `["google-workspace"]`
3. During agent orchestration runs, the agent's tool list includes all Google Workspace tools (prefixed with `mcp__google_workspace__`)
4. The agent can call `mcp__google_workspace__search_drive_files` as part of its reasoning
5. The orchestrator routes the call through the proxy, authenticating with the namespace's stored credentials

**Success:** Agent has access to Google Workspace tools without storing credentials on the agent record.

### 2.3 Tertiary Scenario: Sandbox Function Calls Multiple MCP Servers

**Actor:** Developer building a cross-service automation
**Goal:** Single function that reads from Google Sheets and posts to Slack
**Context:** Namespace has both `google-workspace` and `slack` MCP servers configured

**Workflow:**
1. Developer writes a function that combines data from multiple MCP servers:
   ```python
   from functions import mcp__google_workspace__read_sheet_values
   from functions import mcp__slack__send_message

   data = mcp__google_workspace__read_sheet_values(
       spreadsheet_id="abc123", range="A1:D50"
   )
   summary = f"Updated: {len(data['values'])} rows processed"
   mcp__slack__send_message(channel="C01234567", text=summary)
   result = {"rows_processed": len(data['values']), "notified": True}
   ```
2. Two MCP server calls happen inside the sandbox, each proxied through MCPWorks
3. The 50-row spreadsheet data stays in the sandbox — only the 2-field result returns to the AI

**Success:** Cross-MCP-server automation with token efficiency. The AI sent ~100 tokens of code, received ~30 tokens of result. The spreadsheet data (potentially thousands of tokens) never entered context.

---

## 3. Functional Requirements

### 3.1 Namespace MCP Server Registry

**REQ-MCP-001: Add MCP Server**
- **Description:** MCP tool `add_mcp_server` registers an external MCP server on the namespace
- **Priority:** Must Have
- **Parameters:** `name` (unique per namespace), `url` (HTTPS endpoint), `transport` (`sse` | `streamable_http` | `stdio`; default `streamable_http`), `auth_token` (optional, for Authorization header), `headers` (optional, additional headers as key-value pairs)
- **Behavior:**
  1. Connect to the MCP server using provided credentials
  2. Call `tools/list` to discover available tools
  3. Encrypt credentials with envelope encryption (KEK/DEK)
  4. Store server config + cached tool schemas in DB
  5. Return server name, tool count, and tool list
- **Validation:** Connection must succeed and `tools/list` must return at least one tool. Reject if connection fails.
- **Authorization:** Namespace owner only

**REQ-MCP-002: Remove MCP Server**
- **Description:** MCP tool `remove_mcp_server` unregisters an MCP server from the namespace
- **Priority:** Must Have
- **Parameters:** `name`
- **Behavior:** Delete server config and cached tool schemas. Agents referencing this server lose access on next run.
- **Authorization:** Namespace owner only

**REQ-MCP-003: List MCP Servers**
- **Description:** MCP tool `list_mcp_servers` returns all configured MCP servers for the namespace
- **Priority:** Must Have
- **Returns:** Server name, URL (credentials redacted), transport type, tool count, last connected timestamp
- **Authorization:** Read access

**REQ-MCP-004: Refresh MCP Server**
- **Description:** MCP tool `refresh_mcp_server` reconnects to an MCP server and updates cached tool schemas
- **Priority:** Should Have
- **Parameters:** `name`
- **Behavior:** Reconnect, re-discover tools, update cached schemas. Reports added/removed tools.
- **Authorization:** Namespace owner only

### 3.2 Credential Storage

**REQ-CRED-001: Encrypted Credential Storage**
- **Description:** MCP server authentication credentials must be encrypted at rest using the existing envelope encryption (AES-256-GCM with KEK/DEK)
- **Priority:** Must Have
- **Details:** Auth headers (including bearer tokens, API keys) are serialized to JSON, encrypted with a per-record DEK, DEK encrypted with the instance KEK. The URL is stored in plaintext (needed for display and connection routing).

**REQ-CRED-002: Credential Isolation**
- **Description:** MCP server credentials must never be exposed to sandbox code, agent system prompts, or MCP tool responses
- **Priority:** Must Have
- **Details:** The sandbox calls the internal proxy with the bridge key. The proxy looks up and decrypts credentials server-side. Credentials flow only between the MCPWorks API process and the external MCP server.

**REQ-CRED-003: Migration from Agent JSONB**
- **Description:** Existing `agent.mcp_servers` JSONB configs must be migrated to the new per-namespace encrypted model
- **Priority:** Must Have
- **Details:** Extract server configs from all agents, deduplicate by URL within each namespace, encrypt credentials, populate new table. Update agents to reference servers by name instead of storing full configs.

### 3.3 Sandbox Integration

**REQ-SAND-001: Function Package Injection**
- **Description:** When a namespace has MCP servers configured, their tools must be injected into the `functions` package as callable Python wrappers
- **Priority:** Must Have
- **Details:** Extend `generate_functions_package()` to:
  1. Query namespace MCP servers and their cached tool schemas
  2. Generate a wrapper function for each MCP tool: `mcp__{server}__{tool}(**kwargs)`
  3. The wrapper calls the internal MCP proxy endpoint via HTTP (same pattern as TypeScript bridge)
  4. Wrappers are included in the `functions/__init__.py` docstring for discovery

**REQ-SAND-002: Internal MCP Proxy Endpoint**
- **Description:** A new internal API endpoint that proxies MCP tool calls from the sandbox to external MCP servers
- **Priority:** Must Have
- **Endpoint:** `POST /v1/internal/mcp-proxy`
- **Authentication:** Bridge key (same `__MCPWORKS_BRIDGE_KEY__` used by TypeScript bridge)
- **Request body:** `{"server": "slack", "tool": "send_message", "arguments": {...}}`
- **Behavior:**
  1. Validate bridge key
  2. Look up MCP server config for the namespace
  3. Decrypt credentials
  4. Connect to MCP server (or reuse pooled connection)
  5. Call the tool with provided arguments
  6. Return the result
- **Response:** Tool result as JSON (text content extracted, same as `McpServerPool.call_tool`)

**REQ-SAND-003: Connection Pooling**
- **Description:** MCP server connections should be pooled per-namespace to avoid reconnecting on every sandbox call
- **Priority:** Should Have
- **Details:** A connection pool keyed by `(namespace_id, server_name)` with configurable TTL (default 5 minutes). Connections are established on first call and reused for subsequent calls within the TTL. Pool is cleaned up on server removal.

**REQ-SAND-004: Tool Discovery in Sandbox**
- **Description:** Sandbox code must be able to discover available MCP server tools via the functions package
- **Priority:** Must Have
- **Details:** `import functions; print(functions.__doc__)` includes MCP tools in the catalog:
  ```
  Available functions in the 'analytics' namespace:

    [utils]
      hello(name) — Greet someone

    [mcp: slack]
      mcp__slack__send_message(channel, text) — Send a message to a Slack channel
      mcp__slack__list_channels() — List all channels
  ```

### 3.4 Agent Integration

**REQ-AGENT-001: Agent MCP Server Selection**
- **Description:** Agents specify which namespace MCP servers they can access by name (not by storing full configs)
- **Priority:** Must Have
- **Details:** Replace `agent.mcp_servers` JSONB with a list of server name references. The orchestrator resolves names to configs from the namespace registry at run time.
- **Migration:** Existing JSONB configs become namespace-level servers; agents get a name list.

**REQ-AGENT-002: Orchestrator Integration**
- **Description:** The agent orchestrator must use the namespace MCP server registry for tool discovery and calls
- **Priority:** Must Have
- **Details:** `McpServerPool` reads configs from the namespace registry (decrypting credentials) instead of from the agent's JSONB column. Tool prefixing (`mcp__{name}__{tool}`) remains unchanged.

### 3.5 Security Requirements

**REQ-SEC-001: No Credentials in Sandbox**
- **Description:** MCP server credentials (tokens, API keys, auth headers) must never be accessible to sandbox code
- **Priority:** Must Have
- **Details:** Credentials exist only in the API server process memory during proxied calls. The sandbox communicates via the bridge key to the proxy endpoint.

**REQ-SEC-002: Proxy Authorization**
- **Description:** The internal MCP proxy must validate that the calling execution is authorized to access the requested MCP server
- **Priority:** Must Have
- **Details:** The proxy extracts the namespace from the bridge key context. Only MCP servers configured on that namespace are accessible. Requesting a server from a different namespace returns 403.

**REQ-SEC-003: Credential Rotation**
- **Description:** Users must be able to update MCP server credentials without removing and re-adding the server
- **Priority:** Should Have
- **Details:** `update_mcp_server` tool allows updating auth_token/headers without changing the server name or URL. Existing cached tool schemas are preserved.

**REQ-SEC-004: stdio Transport Restrictions**
- **Description:** stdio transport (running a local command) must be restricted to self-hosted instances
- **Priority:** Must Have
- **Details:** stdio requires executing a binary on the server. On MCPWorks Cloud, only SSE and Streamable HTTP transports are allowed. Self-hosted instances can enable stdio via configuration flag.

---

## 4. Non-Functional Requirements

### 4.1 Performance

- **Tool discovery:** < 5 seconds to connect and discover tools from a new MCP server
- **Proxy latency:** < 50ms added latency per proxied call (excluding external MCP server response time)
- **Connection pool:** Connections reused for 5 minutes (configurable), avoiding per-call connection overhead
- **Token efficiency:** MCP tool wrapper definitions in functions package < 50 tokens per tool. Full tool schemas only loaded via `describe_function` on demand.

### 4.2 Scalability

- **MCP servers per namespace:** Up to 20 (configurable limit)
- **Tools per MCP server:** Up to 200 (cached; larger servers may be slow to discover)
- **Concurrent proxy calls:** Pool supports concurrent calls to same MCP server (MCP session multiplexing)

### 4.3 Reliability

- **Connection failure handling:** If an MCP server is unreachable during sandbox execution, the proxy returns a clear error. Other MCP servers remain available.
- **Graceful degradation:** If tool discovery fails at add time, the server is not added (fail fast). If discovery fails at refresh time, cached schemas are preserved.
- **Stale connection recovery:** If a pooled connection drops, the proxy reconnects transparently on next call.

---

## 5. Constraints & Assumptions

### 5.1 Technical Constraints

- MCP proxy runs in the API server process (same container) — no separate sidecar
- Connection pool is in-memory (not Redis) — connections are per-worker, not shared across workers. Acceptable for single-server deployment; needs redesign for multi-worker.
- stdio transport requires the command binary to be present on the API server. Not available on MCPWorks Cloud.
- MCP server tool schemas are cached in DB at add/refresh time. Schema drift between refreshes is the user's responsibility.

### 5.2 Assumptions

- Third-party MCP servers implement the standard MCP protocol (tools/list, tools/call)
- Auth tokens provided by users have sufficient permissions for the tools they intend to call
- MCP servers are reachable from the MCPWorks API server (not from the sandbox — the proxy handles routing)
- Users understand that adding an MCP server makes its tools available to all functions and agents in the namespace (namespace-scoped, not function-scoped)
- **Risk if wrong:** If users expect per-function MCP server access control, this spec doesn't support it. All functions in the namespace see all configured MCP servers.

---

## 6. Error Scenarios & Edge Cases

### 6.1 Error: MCP Server Unreachable at Add Time

**Trigger:** User provides a URL that doesn't respond or returns non-MCP protocol
**Expected Behavior:** Return error: "Could not connect to MCP server at {url}: {detail}". Server is not added.
**Recovery:** User fixes the URL or server, tries again.

### 6.2 Error: MCP Server Unreachable During Proxy Call

**Trigger:** Sandbox calls a tool, but the MCP server is down
**Expected Behavior:** Proxy returns error to sandbox: `{"error": "MCP server 'slack' is unreachable"}`. The sandbox code can handle this with try/except.
**Recovery:** Automatic — next call will attempt to reconnect.

### 6.3 Error: Expired Credentials

**Trigger:** User's auth token expires or is revoked
**Expected Behavior:** MCP server returns 401/403. Proxy surfaces this: `{"error": "MCP server 'slack' authentication failed — update credentials with update_mcp_server"}`.
**Recovery:** User calls `update_mcp_server` with new token.

### 6.4 Edge Case: MCP Server with 0 Tools

**Trigger:** MCP server's tools/list returns empty
**Expected Behavior:** Server is added with 0 tools. Warning in response: "Server added but has no tools. Refresh later if tools are added."
**Rationale:** Server might be configured before tools are deployed.

### 6.5 Edge Case: Tool Name Collisions

**Trigger:** Two MCP servers expose a tool with the same name (e.g., both have `search`)
**Expected Behavior:** No collision — tools are namespaced: `mcp__slack__search` vs `mcp__github__search`
**Rationale:** The `mcp__{server}__{tool}` prefix ensures uniqueness.

### 6.6 Edge Case: MCP Server Name Conflicts with Service Names

**Trigger:** Namespace has a service named "slack" and an MCP server named "slack"
**Expected Behavior:** No conflict — namespace functions are `from functions import hello` (by function name), MCP tools are `from functions import mcp__slack__search` (prefixed).
**Rationale:** The `mcp__` prefix prevents collisions with native functions.

### 6.7 Edge Case: Large MCP Server (200+ tools)

**Trigger:** MCP server exposes many tools (e.g., Google Workspace with 150+ tools)
**Expected Behavior:** All tools are cached and wrapper functions generated. The functions package docstring may be large; consider truncation for very large tool lists.
**Mitigation:** Only include tool name + one-line description in docstring. Full schemas available via `describe_function`.

---

## 7. Token Efficiency Analysis

### 7.1 Comparison: Direct MCP vs MCPWorks-Wrapped

**Scenario:** AI needs to read 50 rows from a Google Sheet and summarize them.

| Approach | Tool Definitions | Call | Data in Context | Response | Total |
|----------|-----------------|------|-----------------|----------|-------|
| Direct Google Workspace MCP | ~3,000 tokens (150+ tool schemas) | ~100 tokens | ~12,000 tokens (50 rows) | ~200 tokens | **~15,300** |
| MCPWorks code-mode wrapping | ~200 tokens (execute tool) | ~80 tokens (code) | 0 tokens (data in sandbox) | ~100 tokens (summary) | **~380** |

**97.5% token savings** — tool schemas aren't loaded (progressive disclosure), data never enters context.

### 7.2 Tool Wrapper Token Cost

Each MCP tool wrapper in the functions docstring costs ~15-20 tokens:
```
mcp__slack__send_message(channel, text) — Send a message to a Slack channel
```

A namespace with 3 MCP servers averaging 15 tools each = ~45 tools × 18 tokens = ~810 tokens in the catalog docstring. This is a one-time context cost, amortized across all function calls.

---

## 8. Security Analysis

### 8.1 Threat Model

**Threat:** Sandbox code attempts to extract MCP server credentials
**Impact:** Confidentiality — stolen tokens could access external services
**Mitigation:** Credentials never enter the sandbox. The proxy endpoint decrypts and uses them server-side. The sandbox only has the bridge key, which is execution-scoped and short-lived.
**Residual Risk:** Low — bridge key grants access to namespace MCP servers, but only through the proxy (not raw credentials)

**Threat:** Malicious function calls excessive MCP server operations
**Impact:** Availability — could spam external services or exhaust rate limits
**Mitigation:** Execution time limits (nsjail timeout) cap total call duration. Future: per-server rate limiting on the proxy.
**Residual Risk:** Medium — within a single execution, many proxy calls are possible. Rate limiting is deferred.

**Threat:** Bridge key leaked from sandbox via network
**Impact:** Integrity — key could be used to make proxy calls from outside the sandbox
**Mitigation:** Bridge key is tied to a specific execution ID and expires when the sandbox exits. The proxy validates the execution is still active.
**Residual Risk:** Low — window of exploitation is the sandbox timeout (max 120 seconds)

### 8.2 PII/Sensitive Data

- MCP server credentials stored with AES-256-GCM envelope encryption
- Proxy logs include server name and tool name, never credentials or arguments
- External MCP server responses may contain PII — stays in sandbox, never logged by MCPWorks

---

## 9. Data Model

### 9.1 New Entity: NamespaceMcpServer

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | PK |
| namespace_id | UUID | FK → namespaces.id |
| name | VARCHAR(63) | Unique per namespace, DNS-safe |
| transport | VARCHAR(20) | `sse`, `streamable_http`, `stdio` |
| url | VARCHAR(500) | Endpoint URL (plaintext) |
| command | VARCHAR(500) | For stdio transport only |
| args | JSONB | For stdio transport only |
| headers_encrypted | BYTEA | Auth headers, encrypted |
| headers_dek_encrypted | BYTEA | DEK |
| tool_schemas | JSONB | Cached tool list from discovery |
| tool_count | INTEGER | Cached count |
| last_connected_at | TIMESTAMPTZ | Last successful connection |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**Indexes:** UNIQUE(namespace_id, name)

### 9.2 Modified Entity: Agent

| Change | Details |
|--------|---------|
| Deprecate `mcp_servers` JSONB | Replace with `mcp_server_names` (ARRAY of VARCHAR) referencing NamespaceMcpServer by name |
| Migration | Extract configs from JSONB, create NamespaceMcpServer records, update agent to name list |

---

## 10. Observability Requirements

### 10.1 Metrics

- `mcpworks_mcp_proxy_calls_total` (counter) — labels: namespace, server, tool, status
- `mcpworks_mcp_proxy_duration_seconds` (histogram) — labels: namespace, server
- `mcpworks_mcp_server_connections_active` (gauge) — labels: namespace, server

### 10.2 Logging

- `mcp_server_added` — server name, tool count (never credentials)
- `mcp_proxy_call` — server, tool, duration_ms, status (never arguments or response body)
- `mcp_proxy_error` — server, tool, error type (never credentials)
- `mcp_connection_pool_hit` / `mcp_connection_pool_miss`

---

## 11. Testing Requirements

### 11.1 Unit Tests

- Wrapper generation produces valid Python for various tool schemas
- Credential encryption/decryption round-trip
- Proxy request validation (bridge key, namespace scoping)
- Tool name prefixing and collision avoidance

### 11.2 Integration Tests

- Add MCP server → discover tools → call tool via proxy → verify result
- Sandbox execution with MCP tool wrappers → proxy call → result in sandbox
- Agent run with namespace MCP servers → orchestrator uses proxy
- Credential rotation → existing connections use new credentials

### 11.3 E2E Tests

- Configure Google Workspace MCP → write function that reads Sheet → verify data stays in sandbox
- Multi-server: read from one MCP server, write to another, verify token efficiency

---

## 12. Future Considerations

### 12.1 Phase 2: OAuth Integration

- `add_mcp_server_oauth` tool triggers OAuth device flow for supported providers
- Token refresh handled automatically by MCPWorks
- Eliminates need for users to manually generate PATs

### 12.2 Phase 2: MCP Resource Support

- Expose MCP server resources (not just tools) to sandbox code
- `mcp__slack__resource://channels` pattern

### 12.3 Phase 2: Per-Function Access Control

- Allow restricting which functions can access which MCP servers
- `function.allowed_mcp_servers: ["slack"]` field

### 12.4 Phase 3: MCP Server Marketplace

- Pre-configured MCP server templates (one-click add for popular servers)
- Community-contributed server configs with default schemas

---

## 13. Spec Completeness Checklist

**Before moving to Plan phase:**

- [x] Clear user value proposition stated
- [x] Success criteria defined and measurable
- [x] All functional requirements enumerated
- [x] All constraints documented
- [x] Error scenarios identified
- [x] Security requirements specified
- [x] Performance requirements quantified
- [x] Token efficiency requirements stated
- [x] Testing requirements defined
- [x] Observability requirements defined
- [x] Reviewed for Constitution compliance
- [ ] Logic checked (internally consistent)
- [ ] Peer reviewed

---

## 14. Approval

**Status:** Draft

**Approvals:**
- [ ] CTO (Simon Carr)

**Approved Date:** —
**Next Review:** —

---

## Changelog

**v0.1.0 (2026-03-26):**
- Initial draft

# Research: MCP Server Cards (.well-known Discovery)

## R1: .well-known Path Convention

**Decision**: Use `/.well-known/mcp.json` as the discovery path.

**Rationale**: The `.well-known` URI prefix (RFC 8615) is the standard mechanism for site-wide metadata. `mcp.json` is concise and follows the pattern of `openid-configuration`, `security.txt`, etc. The formal MCP Server Card spec (targeted June 2026) may use a different path; the schema version field allows migration.

**Alternatives considered**:
- `/.well-known/mcp-server-card` — more descriptive but longer; may conflict with eventual spec
- `/.well-known/mcp-server.json` — reasonable but `mcp.json` is simpler
- `/mcp.json` at root — doesn't follow RFC 8615 convention

## R2: Server Card Schema Design

**Decision**: Custom v0 schema inspired by MCP `ServerInfo` and OpenAPI info objects. Include `schema_version: "0.1.0"` for future migration.

**Rationale**: No formal spec exists yet. The MCP protocol's `ServerInfo` (returned in `initialize` response) contains `name`, `version`, and `protocolVersion`. We extend this with tools, transports, and endpoints — the data a client needs before connecting.

**Alternatives considered**:
- Wait for formal spec — delays value delivery; the v0 format can be replaced later
- Use OpenAPI format — wrong abstraction; MCP tools aren't REST endpoints
- Use MCP `initialize` response format directly — doesn't include transport/endpoint info needed for pre-connection discovery

## R3: Subdomain vs Path-Based Serving

**Decision**: Mount `.well-known/mcp.json` on the main app. The subdomain middleware already skips `.well-known/*` paths (subdomain.py line 91-93), so no middleware changes needed. The handler reads the `Host` header to determine which namespace is being queried.

**Rationale**: The existing OAuth `.well-known` endpoint uses this same pattern (main.py line 300). It's the simplest approach and doesn't require subdomain routing changes.

**Alternatives considered**:
- Mount within subdomain routing — requires modifying middleware, adds complexity for no benefit
- Separate discovery service — over-engineering for a simple JSON response

## R4: Platform vs Namespace Card Differentiation

**Decision**: Use `Host` header inspection. If the host is `api.mcpworks.io`, serve the platform card. If it's `{ns}.create.mcpworks.io`, serve that namespace's card. All other hosts return 404.

**Rationale**: Single endpoint handler with host-based dispatch. Matches existing routing patterns and requires no new URL paths.

**Alternatives considered**:
- Separate routes (`/platform/.well-known/mcp.json`) — creates non-standard paths
- Query parameter (`?type=platform`) — ugly, not discoverable

## R5: Discoverable Flag Implementation

**Decision**: Add `discoverable` boolean column to `namespaces` table (default `false`). Expose via existing MCP create handler as a namespace setting.

**Rationale**: Minimal schema change. The flag only affects platform-level listing. Per-namespace cards are always served (per clarification). Default off ensures no existing namespace is exposed without owner consent.

**Alternatives considered**:
- Separate discovery_config table — over-engineering for a single boolean
- JSONB settings column — namespace model doesn't have one; adding a column is simpler
- Allowlist in config file — doesn't scale with self-hosting users

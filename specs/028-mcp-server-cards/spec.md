# Feature Specification: MCP Server Cards (.well-known Discovery)

**Feature Branch**: `028-mcp-server-cards`  
**Created**: 2026-04-15  
**Status**: Draft  
**Input**: User description: "#36 — MCP Server Cards (.well-known discovery). Implement a .well-known/mcp.json discovery endpoint for mcpworks namespaces so MCP clients, crawlers, and registries can discover namespace capabilities without establishing a live MCP connection."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Discover namespace capabilities via .well-known endpoint (Priority: P1)

An MCP client developer wants to discover what tools a mcpworks namespace offers before establishing a live MCP session. They send an HTTP GET to the namespace's `.well-known/mcp.json` endpoint and receive a structured JSON document describing the server's name, description, available tools, supported transports, and connection endpoints — all without authentication.

**Why this priority**: This is the core value proposition. Discovery without connection is what Server Cards enable. Without this, the feature has no purpose.

**Independent Test**: Can be fully tested by sending an HTTP GET to `https://{namespace}.create.mcpworks.io/.well-known/mcp.json` and verifying a valid JSON response with namespace metadata.

**Acceptance Scenarios**:

1. **Given** a namespace "busybox" with 3 services and 10 functions, **When** a client GETs `https://busybox.create.mcpworks.io/.well-known/mcp.json`, **Then** the response is a JSON document containing the namespace name, description, tool count, and connection endpoints.
2. **Given** a namespace with functions marked `public_safe: true`, **When** a client GETs the server card, **Then** only public-safe functions appear in the tools list (private functions are counted but not enumerated).
3. **Given** a non-existent namespace, **When** a client GETs `https://nonexistent.create.mcpworks.io/.well-known/mcp.json`, **Then** the response is a 404 with a standard error body.

---

### User Story 2 - Platform-level discovery endpoint (Priority: P2)

A registry crawler or AI platform wants to discover all publicly available mcpworks namespaces from a single entry point. They send an HTTP GET to `https://api.mcpworks.io/.well-known/mcp.json` and receive a platform-level server card that lists all namespaces with links to their individual server cards.

**Why this priority**: Platform-level discovery enables bulk indexing and is how registries would find mcpworks namespaces. Less critical than per-namespace discovery since individual namespace URLs can be shared directly.

**Independent Test**: Can be fully tested by sending an HTTP GET to `https://api.mcpworks.io/.well-known/mcp.json` and verifying a JSON response listing available namespaces with their server card URLs.

**Acceptance Scenarios**:

1. **Given** the mcpworks platform with 7 namespaces, **When** a crawler GETs `https://api.mcpworks.io/.well-known/mcp.json`, **Then** the response lists the platform name, version, and an array of namespace entries with name, description, and server card URL.
2. **Given** a namespace that has not opted in to discovery, **When** the platform card is requested, **Then** that namespace does NOT appear in the listing.
3. **Given** a discoverable namespace with no public-safe functions, **When** the platform card is requested, **Then** that namespace still appears in the listing (discovery is about awareness, not access).

---

### User Story 3 - Cache-friendly responses for crawlers (Priority: P3)

A registry crawler indexes mcpworks namespaces periodically. The server card responses include appropriate cache headers so the crawler doesn't need to re-fetch unchanged metadata on every pass, reducing load on both sides.

**Why this priority**: Performance optimization for crawlers. Not required for basic functionality but important for production readiness.

**Independent Test**: Can be tested by checking response headers for Cache-Control directives and verifying that repeated requests within the cache window return consistent data.

**Acceptance Scenarios**:

1. **Given** a server card request, **When** the response is returned, **Then** it includes a Cache-Control header with a reasonable max-age (e.g., 5 minutes).
2. **Given** a namespace whose functions changed since last request, **When** the server card is re-requested after cache expiry, **Then** the response reflects the updated tool count and list.

---

### Edge Cases

- What happens when a namespace exists but has zero functions? Server card should still be returned with an empty tools list.
- What happens when the .well-known path is requested on a `.run` subdomain instead of `.create`? Should return 404 — server cards are served from the management endpoint only.
- What happens when a namespace has hundreds of functions? The tools list should only enumerate public-safe functions; private functions are represented as a count only, keeping the response bounded.
- What happens when a non-discoverable namespace's server card URL is accessed directly? The per-namespace card (P1) should still be served — the `discoverable` flag only controls platform-level listing, not direct access.
- What happens when the database is unreachable? Return a 503 with a standard error, not a broken JSON document.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST serve a JSON document at `/.well-known/mcp.json` on each namespace's `.create` subdomain, without requiring authentication.
- **FR-002**: The namespace server card MUST include: server name, description, protocol version, transport type, connection endpoints (create and run URLs), and a tools summary.
- **FR-003**: The tools summary MUST enumerate functions marked as `public_safe: true` with their name, description, and input schema. Private functions MUST be represented only as a count (e.g., `"private_tool_count": 8`).
- **FR-004**: System MUST serve a platform-level server card at `https://api.mcpworks.io/.well-known/mcp.json` listing only namespaces that have opted in to discovery (via a `discoverable` flag) with their name, description, and individual server card URL.
- **FR-010**: Namespace owners MUST be able to control whether their namespace appears in the platform-level server card via a `discoverable` setting. Default MUST be off (opt-in).
- **FR-005**: Server card responses MUST include Cache-Control headers with a max-age appropriate for metadata that changes infrequently.
- **FR-006**: System MUST return 404 for `.well-known/mcp.json` requests on non-existent namespaces.
- **FR-007**: System MUST return valid JSON conforming to a documented schema for all successful server card responses.
- **FR-008**: The server card format MUST include a schema version field to support future migration when the formal MCP Server Card spec is finalized.
- **FR-009**: The `.well-known/mcp.json` path MUST be exempt from rate limiting and authentication middleware (it is a public discovery endpoint).

### Key Entities

- **Namespace Server Card**: A JSON document describing a single namespace — its identity, capabilities (tools), and connection information. Generated dynamically from existing namespace, service, and function data.
- **Platform Server Card**: A JSON document describing the mcpworks platform as a whole — listing all namespaces that can be discovered individually.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Any HTTP client can discover a namespace's available tools in a single unauthenticated GET request, receiving a response within 500ms.
- **SC-002**: The server card accurately reflects the current state of the namespace — adding or removing a public function is reflected in subsequent server card requests (after cache expiry).
- **SC-003**: A registry crawler can enumerate all mcpworks namespaces and their server card URLs from the platform-level endpoint in a single request.
- **SC-004**: The server card response size stays under 50KB even for namespaces with many functions, by only enumerating public-safe functions.
- **SC-005**: The server card format includes a version identifier, enabling future migration to the formal MCP Server Card spec with no breaking changes to existing consumers.

## Clarifications

### Session 2026-04-15

- Q: Should the platform-level card list all namespaces or only those that opted in? → A: Only namespaces that have opted in via a `discoverable` flag (default off).
- Q: Should namespace owners be able to disable their per-namespace server card? → A: No — per-namespace cards are always served. The card only exposes public_safe functions which are already public by definition.

## Assumptions

- The `.well-known/mcp.json` path follows the convention used by other web standards (`.well-known/openid-configuration`, `.well-known/security.txt`). The formal MCP spec may use a different path (e.g., `.well-known/mcp-server-card`); the version field will allow migration.
- Only `public_safe` functions are enumerated in the tools list. This is a privacy-by-default choice — namespace owners can mark functions as public to include them in discovery.
- The subdomain middleware already skips `.well-known/*` paths, so this endpoint can be mounted on the main router without subdomain routing conflicts.
- Server cards are generated dynamically from the database on each request (with HTTP caching). No separate storage or materialized views are needed given the expected low request volume.

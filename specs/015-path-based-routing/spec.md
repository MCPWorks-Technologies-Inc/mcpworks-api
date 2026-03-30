# Feature Specification: Path-Based Routing

**Feature Branch**: `015-path-based-routing`
**Created**: 2026-03-30
**Status**: Draft
**Input**: Architecture change — move from subdomain-based namespace routing (`{ns}.{endpoint}.mcpworks.io`) to path-based routing (`api.mcpworks.io/mcp/{endpoint}/{namespace}`)

## Motivation

The current architecture requires wildcard DNS records and wildcard TLS certificates for every endpoint type (`*.create.mcpworks.io`, `*.run.mcpworks.io`, `*.agent.mcpworks.io`). This is a hard requirement for self-hosters because:

1. **DNS complexity** — wildcard DNS requires control over a domain's DNS zone; local installs have no domain at all
2. **TLS complexity** — wildcard certs require DNS-01 ACME challenges, which need API credentials for the DNS provider
3. **Local development friction** — developers currently need query parameters (`?namespace=acme&endpoint=create`) as a workaround on localhost
4. **Network restrictions** — corporate firewalls and NATs often block or complicate wildcard subdomain resolution

Path-based routing eliminates all of this. A self-hoster runs `docker compose up` and connects at `http://localhost:8000/mcp/create/myns` — no DNS, no certs, no workarounds.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Self-Hosted MCP Connection (Priority: P1)

A developer self-hosting MCPWorks on their local machine or LAN server configures their AI assistant (Claude Code, Cursor, etc.) to connect to a namespace via a single HTTP URL with no DNS or TLS configuration.

**Independent Test**: Start the API on localhost:8000. Configure an MCP client to connect to `http://localhost:8000/mcp/create/testns`. Verify the client can initialize, list tools, and call tools against the `testns` namespace.

**Acceptance Scenarios**:

1. **Given** the API is running at `localhost:8000`, **When** a client POSTs a JSON-RPC `initialize` request to `/mcp/create/testns`, **Then** the server responds with MCP capabilities for the `testns` namespace in create mode.
2. **Given** the API is running at `localhost:8000`, **When** a client POSTs a `tools/call` request to `/mcp/run/testns`, **Then** the function executes in the `testns` namespace sandbox.
3. **Given** a self-hoster has no domain name, **When** they configure their MCP client URL to `http://192.168.1.50:8000/mcp/create/myns`, **Then** it works identically to the cloud version.

---

### User Story 2 - Cloud MCP Connection (Priority: P1)

A cloud user connects to MCPWorks Cloud at `api.mcpworks.io`. The path-based URLs work identically to the self-hosted version.

**Independent Test**: Configure an MCP client to connect to `https://api.mcpworks.io/mcp/run/acme`. Verify the client can initialize and execute functions.

**Acceptance Scenarios**:

1. **Given** the API is deployed at `api.mcpworks.io`, **When** a client POSTs to `/mcp/create/acme`, **Then** the server responds with MCP capabilities for the `acme` namespace.
2. **Given** the API is deployed at `api.mcpworks.io`, **When** a client POSTs to `/mcp/run/acme`, **Then** the function executes in the `acme` namespace.
3. **Given** the API is deployed at `api.mcpworks.io`, **When** a client POSTs to `/mcp/agent/mybot`, **Then** the server responds in agent mode for the `mybot` namespace.

---

### User Story 3 - Backward Compatibility (Priority: P2)

Existing users who have configured their MCP clients using the subdomain URLs (`acme.create.mcpworks.io`) continue to work during a transition period. The subdomain middleware remains functional but is no longer the primary routing mechanism.

**Independent Test**: With the API running behind the existing Caddy config, verify that a request to `acme.create.mcpworks.io/mcp` still routes correctly.

**Acceptance Scenarios**:

1. **Given** a client configured with `acme.create.mcpworks.io/mcp`, **When** the client sends requests, **Then** they are handled identically to `/mcp/create/acme`.
2. **Given** subdomain-based routing is used, **When** the server responds, **Then** a deprecation header (`X-MCPWorks-Deprecated: subdomain-routing`) is included in the response.

---

### User Story 4 - Agent Webhooks via Path (Priority: P1)

Agent webhooks currently rely on `{agent}.agent.mcpworks.io/webhook/{path}`. These must work via path-based routing as well.

**Independent Test**: Send a POST to `/mcp/agent/mybot/webhook/github/push` with a webhook payload. Verify the agent receives and processes it.

**Acceptance Scenarios**:

1. **Given** an agent `mybot` with a webhook configured for `github/push`, **When** a POST is sent to `/mcp/agent/mybot/webhook/github/push`, **Then** the webhook is processed.
2. **Given** an agent `mybot` with a public chat token, **When** a POST is sent to `/mcp/agent/mybot/chat/{token}`, **Then** the chat message is processed.
3. **Given** an agent `mybot` with a scratchpad view token, **When** a GET is sent to `/mcp/agent/mybot/view/{token}/`, **Then** the scratchpad HTML is served.

---

### Edge Cases

- **Namespace with slashes or special chars**: Namespace names are already validated as `[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?` — no change needed. FastAPI path parameter captures the segment between slashes.
- **Trailing slashes**: `/mcp/create/acme` and `/mcp/create/acme/` should both work (FastAPI's `redirect_slashes` handles this).
- **Invalid endpoint type**: `/mcp/invalid/acme` returns 404 with a clear error message listing valid types.
- **Missing namespace**: `/mcp/create/` or `/mcp/create` returns 404.
- **Root MCP path**: `GET /mcp` returns discovery info (protocol version, supported endpoints).
- **SSE transport**: The MCP Streamable HTTP transport at `/mcp/{endpoint}/{namespace}` must support both POST (JSON-RPC) and GET (SSE stream reconnection) per the MCP spec.

## Requirements *(mandatory)*

### Functional Requirements

**Path-Based MCP Routing:**

- **FR-001**: The API MUST accept MCP requests at `/mcp/{endpoint}/{namespace}` where `endpoint` is one of `create`, `run`, or `agent`.
  - Priority: P1
  - Acceptance: MCP clients can connect using path-based URLs for all three endpoint types.

- **FR-002**: The path parameters MUST populate `request.state.namespace` and `request.state.endpoint_type` identically to how `SubdomainMiddleware` does today, so downstream handlers require zero changes.
  - Priority: P1
  - Acceptance: `mcp/transport.py`, `mcp/router.py`, `middleware/billing.py`, and all other consumers of `request.state` work without modification.

- **FR-003**: The `url_builder` module MUST generate path-based URLs by default, with a config toggle (`ROUTING_MODE=path|subdomain`) for backward compatibility.
  - Priority: P1
  - Acceptance: `url_builder.create_url("acme")` returns `https://api.mcpworks.io/mcp/create/acme` when `ROUTING_MODE=path`.

- **FR-004**: Agent sub-paths (webhooks, chat, scratchpad view) MUST work under the path-based scheme: `/mcp/agent/{namespace}/webhook/{path}`, `/mcp/agent/{namespace}/chat/{token}`, `/mcp/agent/{namespace}/view/{token}/`.
  - Priority: P1
  - Acceptance: All existing agent webhook, chat, and view functionality works via path-based URLs.

- **FR-005**: The existing `SubdomainMiddleware` MUST remain functional for backward compatibility during a transition period. It can be disabled via `ROUTING_MODE=path`.
  - Priority: P2
  - Acceptance: Setting `ROUTING_MODE=subdomain` preserves current behavior exactly.

**URL Generation:**

- **FR-006**: All URLs returned in API responses, tool descriptions, quickstart docs, and onboarding flows MUST use the path-based format when `ROUTING_MODE=path`.
  - Priority: P1
  - Acceptance: No subdomain-pattern URLs appear in any response when routing mode is `path`.

**Discovery:**

- **FR-007**: `GET /mcp` MUST return protocol discovery info including available endpoint types and URL patterns.
  - Priority: P2
  - Acceptance: Clients can discover the URL pattern from the root MCP endpoint.

### Non-Functional Requirements

**NFR-001: Zero Performance Regression**
- Path-based routing MUST NOT add measurable latency vs. subdomain routing. Both are O(1) string operations — path param extraction vs. regex match.

**NFR-002: Self-Host Simplicity**
- A self-hoster MUST be able to connect with just an IP address and port. No DNS, no TLS, no domain name required.

**NFR-003: Single Origin**
- All MCP traffic MUST be servable from a single origin (`api.mcpworks.io` for cloud, `localhost:8000` for local). This eliminates wildcard CORS, wildcard DNS, and wildcard TLS requirements.

## Infrastructure Impact

### Caddy Configuration (Cloud)

**Before:**
```
*.create.mcpworks.io, *.run.mcpworks.io, *.agent.mcpworks.io {
    tls { dns cloudflare ... }
    reverse_proxy server0:8000
}
```

**After:**
```
api.mcpworks.io {
    reverse_proxy server0:8000
}
# Keep wildcard block during transition (can be removed later)
```

### DNS (Cloud)

**Before:** Three wildcard A records (`*.create`, `*.run`, `*.agent`)
**After:** Single A record (`api`) — wildcards can be removed after transition period

### Self-Hosted docker-compose

No Caddy needed for local. Just the API container on port 8000. MCP clients connect directly to `http://localhost:8000/mcp/create/myns`.

## Constraints & Assumptions

### Technical Constraints

- The MCP Streamable HTTP transport middleware (`MCPTransportMiddleware`) currently intercepts `/mcp` requests. It must be updated to intercept `/mcp/{endpoint}/{namespace}` instead.
- FastAPI path parameters handle URL decoding automatically.
- The agent webhook, chat, and view routes currently live in separate router files (`webhooks.py`, `public_chat.py`, `scratchpad_view.py`) and rely on subdomain middleware for namespace extraction. These must also support path-based extraction.

### Assumptions

- MCP clients (Claude Code, Cursor, etc.) connect to a single URL — they don't need to resolve different subdomains for create vs. run. Confirmed: MCP clients use a single `url` field.
- The transition period for subdomain support is 90 days from deployment.
- No existing self-hosters are using subdomain routing (the feature hasn't been released yet in self-hosted mode).

## Security Analysis

### Threat: Namespace Enumeration via Path

**Impact**: Low — namespace names are not secret (they're visible in DNS today)
**Mitigation**: Same auth enforcement. API key is still required for all MCP operations.

### Threat: Path Traversal

**Impact**: Medium — malicious namespace like `../../admin`
**Mitigation**: FastAPI path parameters are URL-decoded but do not traverse directories. Additionally, the existing namespace validation regex (`[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?`) rejects any traversal attempts.

## Token Efficiency Analysis

No impact. URL routing is infrastructure — it doesn't affect MCP response payloads.

## Observability

- **Metric**: Existing `mcpworks_mcp_tool_calls_total` continues to work (labels from `request.state`, unchanged).
- **Logging**: Request logging middleware already logs namespace and endpoint_type from `request.state`.
- **New metric**: `mcpworks_routing_mode_requests_total{mode="path|subdomain"}` to track migration progress.

## Spec Completeness Checklist

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

## Approval

**Status:** Draft

**Approvals:**
- [ ] CTO (Simon Carr)

---

## Changelog

**v0.1.0 (2026-03-30):**
- Initial draft

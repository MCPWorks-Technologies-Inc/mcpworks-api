# Feature Specification: OAuth for MCP Server Proxy

**Feature ID**: 026-oauth-mcp-proxy
**Created**: 2026-04-12
**Status**: Draft
**GitHub Issue**: TBD

## Problem Statement

MCPWorks can proxy tool calls to external MCP servers (e.g., Google Workspace, Slack, GitHub) registered on a namespace. Today, auth is limited to static bearer tokens and custom headers. This works for API-key-authenticated services but breaks for OAuth 2.0 services that issue short-lived access tokens requiring periodic refresh — or that require interactive user consent before any token exists.

The core challenge is that OAuth consent is inherently interactive (user opens browser, clicks "Allow"), but MCPWorks operates headlessly through MCP protocol. This creates a **human-in-the-loop authentication** problem: when an AI agent tries to call a Google Workspace tool and no valid token exists, the system must pause, surface an authorization URL to the human user through the LLM, wait for the human to complete consent in a browser, and then resume.

### Concrete Use Case

A user has the `mcpworks-busybox-run` endpoint connected. One of their namespace's proxied MCP servers is `google_workspace`. In code-mode, the AI writes:

```python
from functions import google_workspace__list_recent_emails
result = google_workspace__list_recent_emails({"max_results": 10})
```

The proxy must:
1. Check for a valid OAuth access token for `google_workspace`
2. If expired, silently refresh using the stored refresh token
3. If no token exists or refresh token is revoked, return a structured auth-required response that the LLM can surface to the user
4. Attach the valid token to the outbound request to the Google Workspace MCP server
5. All of this happens behind the user's normal mcpworks API key — OAuth is a second layer of auth between mcpworks and the external service

## User Scenarios & Testing

### US1 - First-Time OAuth Setup (Priority: P0)

A namespace owner registers an OAuth-protected MCP server and completes the initial authorization flow.

**Why P0**: Nothing works without initial token acquisition.

**Flow**:
1. Owner calls `add_mcp_server(name="google_workspace", url="...", auth_type="oauth2", oauth_config={...})`
2. System stores OAuth client config (client_id, client_secret, scopes, auth/token endpoints) encrypted
3. Owner (or AI agent on behalf of owner) triggers first tool call
4. Proxy detects no access token → returns structured `AUTH_REQUIRED` response with authorization URL
5. Human opens URL in browser → Google consent screen → approves
6. Google redirects to mcpworks callback (`/v1/oauth/mcp-callback/{namespace}/{server_name}`)
7. mcpworks exchanges authorization code for access + refresh tokens, stores encrypted
8. Subsequent tool calls succeed

**Acceptance Scenarios**:

1. **Given** an MCP server registered with `auth_type="oauth2"` and valid oauth_config, **When** the first tool call is made, **Then** the proxy returns `{"auth_required": true, "auth_url": "https://accounts.google.com/o/oauth2/auth?...", "message": "User authorization required. Open this URL in a browser to grant access."}` instead of a tool error.
2. **Given** the authorization URL is opened and consent granted, **When** Google redirects to the callback, **Then** access and refresh tokens are stored encrypted and the callback returns a success page.
3. **Given** tokens are stored, **When** the next tool call is made, **Then** the proxy attaches the access token and the call succeeds.

### US2 - Silent Token Refresh (Priority: P0)

Access tokens expire (typically 1 hour for Google). The proxy must refresh them transparently.

**Why P0**: Without refresh, every OAuth integration breaks after ~1 hour.

**Acceptance Scenarios**:

1. **Given** a stored access token that has expired, **When** a tool call is made, **Then** the proxy uses the refresh token to obtain a new access token before making the call.
2. **Given** a successful token refresh, **When** the new tokens are received, **Then** the encrypted stored tokens are updated in the database.
3. **Given** a token refresh that fails with `invalid_grant` (refresh token revoked), **Then** the proxy returns the `AUTH_REQUIRED` response with a fresh authorization URL (same as US1 step 4).
4. **Given** a refresh in progress, **When** concurrent tool calls arrive for the same server, **Then** only one refresh is performed (not N concurrent refreshes).

### US3 - HITL Auth Surfacing Through LLM (Priority: P0)

When the proxy returns an `AUTH_REQUIRED` response, the AI agent must be able to surface this to the human user in a way that makes sense in conversation.

**Why P0**: This is what makes the feature usable. Without it, the user sees a cryptic error.

**Acceptance Scenarios**:

1. **Given** an `AUTH_REQUIRED` response from the proxy, **When** the AI receives it as a tool result, **Then** the response is structured clearly enough that the AI can say "You need to authorize Google Workspace. Open this link: [URL]" — not a raw JSON error.
2. **Given** the user completes authorization, **When** they tell the AI "done" or "I authorized it", **Then** the AI can retry the tool call and it succeeds.
3. **Given** the user is in code-mode, **When** the sandbox code calls an unauthorized MCP tool, **Then** the execution returns a result (not a crash) that includes the auth URL, so the AI can surface it.

### US4 - OAuth Config via MCP Tools (Priority: P1)

Namespace owners configure OAuth settings through the existing `add_mcp_server` / `update_mcp_server` tools.

**Acceptance Scenarios**:

1. **Given** a namespace owner, **When** they call `add_mcp_server` with `auth_type="oauth2"` and `oauth_config`, **Then** the client_id, client_secret, and other OAuth params are stored encrypted.
2. **Given** a configured OAuth MCP server, **When** the owner calls `update_mcp_server` to change scopes, **Then** stored tokens are invalidated (scopes changed, re-auth required).
3. **Given** a configured OAuth MCP server, **When** the owner removes it, **Then** stored tokens are deleted (not orphaned).

### US5 - Multiple OAuth Providers per Namespace (Priority: P2)

A namespace can have multiple OAuth-protected MCP servers (Google Workspace, Slack, GitHub) each with their own independent OAuth tokens.

**Acceptance Scenarios**:

1. **Given** a namespace with `google_workspace` and `slack` MCP servers both using OAuth, **When** tool calls are made to each, **Then** each uses its own stored tokens independently.
2. **Given** `google_workspace` needs re-auth but `slack` tokens are valid, **When** a Google tool call is made, **Then** only Google returns `AUTH_REQUIRED`; Slack continues working.

## Design Decisions

### Auth response format

The `AUTH_REQUIRED` response must be distinguishable from tool errors and tool results. Proposed format:

```json
{
  "auth_required": true,
  "provider": "google_workspace",
  "auth_url": "https://accounts.google.com/o/oauth2/auth?client_id=...&redirect_uri=...&scope=...&state=...",
  "message": "Authorization required for google_workspace. Open the URL in a browser to grant access, then retry.",
  "expires_in": 600
}
```

The `state` parameter encodes namespace + server_name + CSRF token for the callback to route correctly.

### Token storage

Extend `namespace_mcp_servers` table:

| Column | Type | Notes |
|--------|------|-------|
| auth_type | varchar(20) | "bearer" (existing), "oauth2" (new), "none" |
| oauth_config_encrypted | bytea | Encrypted: client_id, client_secret, scopes, auth_endpoint, token_endpoint |
| oauth_config_dek | bytea | DEK for oauth_config |
| oauth_tokens_encrypted | bytea | Encrypted: access_token, refresh_token, expires_at |
| oauth_tokens_dek | bytea | DEK for oauth_tokens |

This follows the existing envelope encryption pattern used for `headers_encrypted`.

### Callback endpoint

`GET /v1/oauth/mcp-callback` — receives the authorization code from the OAuth provider, exchanges for tokens, stores encrypted, returns a simple HTML success page. The `state` parameter routes to the correct namespace + server.

### Proactive vs reactive refresh

**Proactive**: Check `expires_at` before making the call. If expired or within 60s of expiry, refresh first. This avoids a wasted round-trip to the external server with an expired token.

**Reactive fallback**: If the external server returns 401, attempt refresh and retry once.

Both are needed — proactive for efficiency, reactive for edge cases where the token was revoked between check and use.

### Concurrency: refresh lock

Multiple concurrent tool calls to the same OAuth server must not trigger N parallel refresh requests. Use a Redis lock (`oauth_refresh:{namespace_id}:{server_name}`, 30s TTL) to serialize refreshes. Waiters retry after the lock holder completes.

### Code-mode integration

In code-mode, MCP server tools are already proxied through the sandbox. The proxy is the point of interception — no sandbox changes needed. The `AUTH_REQUIRED` response flows back as a function result, which the AI sees as output.

### Security considerations

- Client secrets stored with envelope encryption (same as existing headers)
- Refresh tokens stored with envelope encryption
- OAuth state parameter includes CSRF token (random, stored in Redis with 10-min TTL)
- Callback validates state before exchanging code
- Tokens are per-namespace-per-server (not shared across namespaces)
- Token refresh never exposes tokens in logs (structlog scrubbing)

## Non-Requirements (Out of Scope)

- **OAuth provider discovery / .well-known** — User must supply auth_endpoint and token_endpoint explicitly
- **PKCE** — Not required for server-side OAuth (confidential client). Could add later for public client support.
- **Device authorization flow** — Alternative to browser redirect for CLI-only users. Deferred.
- **Token sharing across namespaces** — Each namespace manages its own tokens
- **Automatic MCP server registration from OAuth provider** — User registers the server manually, then authenticates
- **OAuth for mcpworks user auth** — Already exists separately (US1 in 002-oauth-email-system)

## Data Model Changes

### Modified Table: `namespace_mcp_servers`

| Column | Type | Notes |
|--------|------|-------|
| auth_type | varchar(20), default "bearer" | New: "bearer", "oauth2", "none" |
| oauth_config_encrypted | bytea, nullable | New: encrypted OAuth client config |
| oauth_config_dek | bytea, nullable | New: DEK for oauth_config |
| oauth_tokens_encrypted | bytea, nullable | New: encrypted access + refresh tokens |
| oauth_tokens_dek | bytea, nullable | New: DEK for oauth_tokens |
| oauth_tokens_expires_at | timestamptz, nullable | New: access token expiry (plaintext for proactive refresh check) |

### New Redis Keys

| Key | TTL | Purpose |
|-----|-----|---------|
| `oauth_state:{state_token}` | 600s | CSRF protection for callback |
| `oauth_refresh:{namespace_id}:{server_name}` | 30s | Refresh lock to prevent concurrent refreshes |

## Open Questions

1. **Should the callback redirect back to the AI conversation?** Hard to do generically (Claude Desktop, Cursor, web chat all have different UIs). Probably just show "Authorization successful. You can close this tab." and let the user tell the AI to retry.

2. **What happens if the user never completes consent?** The `AUTH_REQUIRED` response has `expires_in: 600` (the state token TTL). After that, the AI would need to generate a fresh auth URL. No cleanup needed — state expires from Redis naturally.

3. **Should we support OAuth 2.0 device flow as an alternative?** This would let CLI-only users authorize without a browser redirect. Lower priority but worth considering for the spec.

4. **Per-user vs per-namespace tokens?** Currently scoped per-namespace (the namespace owner authorizes). If multiple users share a namespace, they share the same Google credentials. Is this correct, or should tokens be per-user-per-server?

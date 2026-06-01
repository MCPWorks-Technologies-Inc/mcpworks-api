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

### US1 - First-Time OAuth Setup via Device Flow (Priority: P0)

A namespace owner registers an OAuth-protected MCP server and completes the initial authorization via device flow.

**Why P0**: Nothing works without initial token acquisition.

**Flow**:
1. Owner calls `add_mcp_server(name="google_workspace", url="...", auth_type="oauth2", oauth_config={...})`
2. System stores OAuth client config (client_id, client_secret, scopes, device_authorization_endpoint, token_endpoint) encrypted
3. Owner (or AI agent on behalf of owner) triggers first tool call
4. Proxy detects no access token → requests device code from provider → returns `AUTH_REQUIRED` with user code and verification URL
5. Proxy starts background polling for token completion
6. Human goes to verification URL on any device, enters user code, approves on provider's consent screen
7. Background poller detects approval, exchanges device code for tokens, stores encrypted
8. Next tool call (retry) succeeds — tokens are ready

**Acceptance Scenarios**:

1. **Given** an MCP server registered with `auth_type="oauth2"` and valid oauth_config, **When** the first tool call is made, **Then** the proxy returns `{"auth_required": true, "verification_uri": "https://www.google.com/device", "user_code": "WDJB-MJHT", ...}` instead of a tool error.
2. **Given** the user enters the code and approves, **When** the background poller detects success, **Then** access and refresh tokens are stored encrypted.
3. **Given** tokens are stored, **When** the next tool call is made, **Then** the proxy attaches the access token and the call succeeds.
4. **Given** the device code expires (user never approves), **When** the next tool call is made, **Then** a fresh device code is generated.

### US2 - Silent Token Refresh (Priority: P0)

Access tokens expire (typically 1 hour for Google). The proxy must refresh them transparently.

**Why P0**: Without refresh, every OAuth integration breaks after ~1 hour.

**Acceptance Scenarios**:

1. **Given** a stored access token that has expired, **When** a tool call is made, **Then** the proxy uses the refresh token to obtain a new access token before making the call.
2. **Given** a successful token refresh, **When** the new tokens are received, **Then** the encrypted stored tokens are updated in the database.
3. **Given** a token refresh that fails with `invalid_grant` (refresh token revoked), **Then** the proxy returns the `AUTH_REQUIRED` response with a fresh authorization URL (same as US1 step 4).
4. **Given** a refresh in progress, **When** concurrent tool calls arrive for the same server, **Then** only one refresh is performed (not N concurrent refreshes).

### US3 - HITL Auth Surfacing Through LLM (Priority: P0)

When the proxy returns an `AUTH_REQUIRED` response with a device code, the AI agent must surface the verification URL and user code to the human in a natural conversational way.

**Why P0**: This is what makes the feature usable. Without it, the user sees a cryptic error.

**Acceptance Scenarios**:

1. **Given** an `AUTH_REQUIRED` device flow response, **When** the AI receives it as a tool result, **Then** the response is structured clearly enough that the AI says "To authorize Google Workspace, go to google.com/device and enter code WDJB-MJHT" — not a raw JSON dump.
2. **Given** the user completes authorization, **When** they tell the AI "done" or simply retry, **Then** the background poller has already stored the tokens and the retry succeeds.
3. **Given** the user is in code-mode, **When** the sandbox code calls an unauthorized MCP tool, **Then** the execution returns a structured result (not a crash) that includes the verification URI and user code.
4. **Given** the background poller is running, **When** the AI retries the tool call before the user has approved, **Then** the proxy returns the same user code and verification URI (not a new one) with a message indicating polling is still active.

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

### Primary auth method: OAuth 2.0 Device Authorization Flow (RFC 8628)

Device flow is the primary authorization method. It's a better fit for an agentic platform than browser redirects because:
- No callback URL required — works behind NATs, firewalls, and self-hosted instances without public DNS
- "Enter this code" is cleaner than "click this URL" in terminal-based MCP clients (Claude Code, CLI tools)
- The AI can naturally say "Go to google.com/device and enter code WDJB-MJHT" in conversation
- Works from any MCP client regardless of UI capabilities
- The mcpworks server polls for completion — no user action needed beyond entering the code

**Flow:**
1. Proxy detects no valid token → requests device code from provider's device_authorization_endpoint
2. Provider returns `device_code`, `user_code`, `verification_uri`, `interval` (poll frequency)
3. Proxy returns structured `AUTH_REQUIRED` response to the AI with the user code and URL
4. AI surfaces to user: "Go to google.com/device and enter code WDJB-MJHT"
5. User opens browser on any device, enters code, approves on provider's consent screen
6. Meanwhile, proxy polls the provider's token endpoint every `interval` seconds using the `device_code`
7. Once user approves, provider returns access + refresh tokens → stored encrypted
8. Subsequent tool calls succeed

**Fallback: Authorization Code Flow** — For providers that don't support device flow (uncommon but possible), fall back to the standard browser redirect with callback URL at `/v1/oauth/mcp-callback/{namespace}/{server_name}`. The `oauth_config` specifies which flow to use.

### Auth response format

The `AUTH_REQUIRED` response must be distinguishable from tool errors and tool results.

**Device flow response (primary):**
```json
{
  "auth_required": true,
  "provider": "google_workspace",
  "verification_uri": "https://www.google.com/device",
  "user_code": "WDJB-MJHT",
  "message": "Authorization required for google_workspace. Go to https://www.google.com/device and enter code WDJB-MJHT to grant access. The system will detect authorization automatically — just retry after approving.",
  "expires_in": 600,
  "flow": "device"
}
```

**Authorization code fallback response:**
```json
{
  "auth_required": true,
  "provider": "google_workspace",
  "auth_url": "https://accounts.google.com/o/oauth2/auth?client_id=...&redirect_uri=...&scope=...&state=...",
  "message": "Authorization required for google_workspace. Open the URL in a browser to grant access, then retry.",
  "expires_in": 600,
  "flow": "authorization_code"
}
```

### Device code polling

When the proxy returns `AUTH_REQUIRED` with device flow, it also spawns a background polling task:
- Polls provider's token endpoint every `interval` seconds (typically 5s) with the `device_code`
- Handles `authorization_pending` (keep polling), `slow_down` (increase interval), `expired_token` (stop)
- On success: stores tokens encrypted, cancels polling
- On expiry: polling stops naturally, next tool call generates a fresh device code
- Polling is fire-and-forget via `asyncio.create_task()`, keyed by `{namespace_id}:{server_name}` to prevent duplicates

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

### Callback endpoint (authorization code fallback only)

`GET /v1/oauth/mcp-callback` — used only when a provider doesn't support device flow. Receives the authorization code, exchanges for tokens, stores encrypted, returns a simple HTML page: "Authorization successful for [provider]. You are granting this namespace access — all users and agents with namespace access can use these credentials. You can close this tab." The `state` parameter routes to the correct namespace + server and includes a CSRF token validated against Redis.

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
| `oauth_device:{namespace_id}:{server_name}` | 600s | Active device code + user code (prevents duplicate generation) |
| `oauth_poll:{namespace_id}:{server_name}` | 600s | Flag indicating background poller is active |
| `oauth_refresh:{namespace_id}:{server_name}` | 30s | Refresh lock to prevent concurrent refreshes |
| `oauth_state:{state_token}` | 600s | CSRF protection for auth code callback (fallback only) |

## Resolved Questions

### Q4: Per-user vs per-namespace tokens → Per-namespace

**Decision**: Tokens are scoped per-namespace, not per-user.

**Rationale**: The namespace is the identity boundary on mcpworks. When you register `google_workspace` on a namespace and authorize it, you're granting the namespace — and everything operating within it (users, agents, cron triggers) — access to that external service. This is the same model as a service account: the credential belongs to the workspace, not an individual.

Per-user tokens would create problems for agent autonomy: when an agent runs on a cron trigger at 3am, whose token does it use? The namespace owner's? A "service user"? Per-namespace sidesteps this entirely — the agent has the same credentials regardless of trigger source.

If an organization needs per-person access control within Google Workspace, that's Google's IAM — delegate to the provider, don't replicate it in the proxy layer.

**Required disclosure**: When a namespace owner completes OAuth consent, the callback success page and the `AUTH_REQUIRED` response must clearly state: "You are granting this namespace access to [provider]. All users and agents with access to this namespace can use these credentials." Informed consent, not a surprise.

## Resolved Questions

### Q1: Callback redirect → No redirect needed (device flow is primary)

With device flow as the primary method, the callback question is mostly moot. The background poller detects authorization — no redirect back to the conversation needed. The user approves on the provider's site, the poller picks it up, and the next tool call just works.

For the authorization code fallback: show a static HTML success page with the informed consent disclosure. No redirect back to the conversation — impossible to do generically across MCP clients.

### Q2: User never completes consent → Self-healing

Device code expires naturally (typically 10 minutes, set by the provider). Background poller detects `expired_token` and stops. No orphaned data. Redis polling key expires with TTL. Next tool call generates a fresh device code. Idempotent by design.

Rate limit: one active device code per namespace+server. If the AI retries while a code is active, return the existing code (don't generate a new one).

### Q3: Device flow → Primary method, not deferred

Device flow (RFC 8628) is the primary authorization method. Authorization code flow is the fallback for providers that don't support it. See "Primary auth method" section above for full rationale.

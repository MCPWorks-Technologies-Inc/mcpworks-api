# Research: OAuth for MCP Server Proxy

**Feature**: 026-oauth-mcp-proxy | **Date**: 2026-04-12

## R1: OAuth 2.0 Device Authorization Flow (RFC 8628)

**Decision**: Use device flow as the primary authorization method for MCP server OAuth.

**Rationale**: Device flow doesn't require a callback URL (works behind NATs, self-hosted), produces a clean "enter this code" UX for terminal MCP clients, and the background polling model fits the agentic pattern where the AI retries after the user approves.

**Alternatives considered**:
- Authorization code flow (standard browser redirect) — requires public callback URL, awkward in CLI contexts. Kept as fallback.
- Client credentials flow — no user consent, only works for service-to-service. Not applicable when accessing user data (e.g., Google Workspace emails).

## R2: Authlib Device Flow Support

**Decision**: Use Authlib 1.3+ (already a dependency) for the OAuth client. Authlib supports device authorization via standard HTTP calls to device_authorization_endpoint and token_endpoint.

**Rationale**: Authlib is already configured for social login (Google, GitHub). The device flow is standard RFC 8628 — two HTTP calls: POST to device_authorization_endpoint, then POST to token_endpoint with `grant_type=urn:ietf:params:oauth:grant-type:device_code`.

**Alternatives considered**:
- Raw httpx calls — works but reinvents token parsing, error handling, and JWT validation that Authlib provides.
- python-social-auth — additional dependency, no advantage over Authlib already in use.

## R3: Token Storage Pattern

**Decision**: Use the existing envelope encryption pattern (AES-256-GCM) from `core/encryption.py`. Add 5 new columns to `namespace_mcp_servers`.

**Rationale**: Same pattern used for `headers_encrypted`. No new crypto infrastructure needed. `encrypt_value()` / `decrypt_value()` handle JSON serialization, per-value random DEKs, and KEK wrapping.

**Alternatives considered**:
- Separate `mcp_oauth_tokens` table — unnecessary normalization, joins add latency to every proxy call.
- Store tokens in `settings` JSONB — not encrypted at rest, violates security standards.

## R4: Token Refresh Strategy

**Decision**: Proactive refresh via background task, with reactive 401-handling as fallback.

**Rationale**: Proactive refresh (check `expires_at`, refresh 5 min before expiry) avoids adding latency to tool calls. The background poller pattern already exists for agent schedules (`tasks/scheduler.py`). Reactive fallback catches edge cases where tokens are revoked between refresh and use.

**Alternatives considered**:
- Lazy refresh only (on 401) — simpler but adds 1-2s latency to the first call after expiry. Unacceptable for code-mode where multiple MCP calls may chain.
- Separate refresh service/worker — overkill; a single async loop in the existing lifespan is sufficient.

## R5: Device Code Polling Architecture

**Decision**: On-demand background task per device flow initiation, not a persistent polling loop.

**Rationale**: Unlike the scheduler (which runs continuously), device flow polling is ephemeral — it starts when a user initiates auth and stops when they approve (or the code expires). Spawning `asyncio.create_task()` per initiation, keyed in Redis to prevent duplicates, is cleaner than a persistent loop that checks "is anyone currently authorizing?"

**Implementation**:
- First tool call with no token → request device code → store in Redis → spawn poller task → return AUTH_REQUIRED
- Poller polls token endpoint every `interval` seconds (from provider response, typically 5s)
- On success: encrypt + store tokens in DB, delete Redis state, cancel task
- On expiry: delete Redis state, task exits naturally
- On duplicate request (poller already running): return existing user_code from Redis

## R6: Per-Namespace Token Scope

**Decision**: OAuth tokens are per-namespace, not per-user. See spec Q4 resolution.

**Rationale**: The namespace is the identity boundary. Agent cron triggers need tokens without a user context. Per-user would require solving "whose token does the agent use at 3am?"

## R7: Provider Support Matrix

**Decision**: Support any OAuth 2.0 provider that implements device flow or authorization code flow. No provider-specific logic beyond endpoint URLs and scopes.

**Rationale**: The proxy should be provider-agnostic. Users supply `device_authorization_endpoint`, `token_endpoint`, `client_id`, `client_secret`, and `scopes`. The proxy doesn't need to know it's talking to Google vs Slack vs GitHub — it just speaks RFC 8628 / RFC 6749.

**Known provider support for device flow**:
- Google: YES (device flow supported)
- GitHub: YES (device flow supported)
- Microsoft/Azure AD: YES (device flow supported)
- Slack: NO (authorization code only — use fallback)
- Linear: NO (authorization code only — use fallback)

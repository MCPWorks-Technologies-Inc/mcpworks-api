# Implementation Plan: OAuth for MCP Server Proxy

**Branch**: `026-oauth-mcp-proxy` | **Date**: 2026-04-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/026-oauth-mcp-proxy/spec.md`

## Summary

Add OAuth 2.0 support to the MCP server proxy so external MCP servers (Google Workspace, Slack, GitHub) can be authenticated with user consent. Primary method is RFC 8628 Device Authorization Flow (enter-a-code UX), with Authorization Code Flow as fallback. Tokens are per-namespace, encrypted at rest, refreshed proactively, and surfaced to users via structured HITL responses that the AI can present conversationally.

## Technical Context

**Language/Version**: Python 3.11+ (existing codebase)
**Primary Dependencies**: FastAPI 0.109+ (existing), Authlib 1.3+ (existing), httpx (existing), SQLAlchemy 2.0+ (existing)
**Storage**: PostgreSQL 15+ (5 new columns on `namespace_mcp_servers`), Redis 7+ (ephemeral device flow state)
**Testing**: pytest with async fixtures; mock httpx for OAuth endpoint responses
**Target Platform**: Linux server (existing mcpworks-api container)
**Project Type**: Single backend API
**Performance Goals**: Token refresh <500ms; zero added latency when tokens are fresh (plaintext `expires_at` check only)
**Constraints**: Never store tokens unencrypted; never log tokens; device flow polling must not block request handling
**Scale/Scope**: Up to 50 OAuth-protected MCP servers per namespace; 1 active device flow per server

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First Development | PASS | Spec complete with all questions resolved before planning |
| II. Token Efficiency & Streaming | PASS | AUTH_REQUIRED response is <200 tokens; no impact on normal tool call responses |
| III. Transaction Safety & Security | PASS | Tokens encrypted at rest (AES-256-GCM envelope); CSRF protection on callbacks; refresh lock prevents concurrent refreshes; informed consent disclosure |
| IV. Provider Abstraction & Observability | PASS | Provider-agnostic (any RFC 8628 / RFC 6749 provider); Prometheus metrics for auth events; structlog for token operations |
| V. API Contracts & Test Coverage | PASS | No breaking changes to existing MCP tools; `auth_type` defaults to "bearer" (backward compatible); unit tests for all flows |

| Quality Standard | Status | Notes |
|-----------------|--------|-------|
| Code Quality | PASS | ruff enforced; type hints on all new functions |
| Documentation | PASS | quickstart.md with examples for device flow and auth code fallback |
| Performance | PASS | Proactive refresh avoids latency on tool calls; plaintext expires_at check |
| Security | PASS | AES-256-GCM envelope encryption; no tokens in logs; CSRF on callbacks |

**No violations.**

## Project Structure

### Documentation (this feature)

```text
specs/026-oauth-mcp-proxy/
├── spec.md              # Feature specification (complete)
├── plan.md              # This file
├── research.md          # Research decisions (complete)
├── data-model.md        # Data model changes (complete)
├── quickstart.md        # Usage examples (complete)
└── tasks.md             # Implementation tasks (next: /speckit.tasks)
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── services/
│   └── mcp_oauth.py           # NEW: OAuth token management (device flow, refresh, storage)
├── tasks/
│   └── device_flow_poller.py   # NEW: Background polling for device code approval
├── api/v1/
│   └── mcp_oauth.py            # NEW: Callback endpoint for auth code fallback
├── models/
│   └── namespace_mcp_server.py # MODIFY: Add 5 OAuth columns
├── core/
│   └── mcp_proxy.py            # MODIFY: Token refresh before proxy call
│   └── mcp_pool.py             # MODIFY: Evict on token refresh
├── main.py                     # MODIFY: Register callback router
├── middleware/
│   └── observability.py        # MODIFY: Add oauth_* Prometheus metrics
└── config.py                   # MODIFY: Optional MCP OAuth settings

alembic/versions/
└── 20260413_000001_add_mcp_oauth.py  # NEW: Migration for 5 columns

tests/unit/
├── test_mcp_oauth_service.py   # NEW: Token lifecycle tests
├── test_device_flow_poller.py  # NEW: Poller behavior tests
└── test_mcp_proxy_oauth.py     # NEW: Proxy integration with OAuth
```

**Structure Decision**: All new code fits within existing directories. Three new files (service, poller, callback endpoint), plus modifications to existing proxy/pool/model/config. No new packages or structural changes.

## Implementation Phases

### Phase 1: Data Model + OAuth Service (Foundation)

**Deliverables**: Migration, model changes, core OAuth service

1. Add 5 columns to `namespace_mcp_servers` model + Alembic migration
2. Create `services/mcp_oauth.py`:
   - `initiate_device_flow(server, db)` → requests device code, stores in Redis, returns AUTH_REQUIRED response
   - `initiate_auth_code_flow(server, db)` → generates auth URL with state, returns AUTH_REQUIRED response
   - `exchange_device_code(server, device_code, db)` → exchanges for tokens, encrypts, stores in DB
   - `exchange_auth_code(server, code, db)` → exchanges for tokens, encrypts, stores in DB
   - `refresh_token_if_needed(server, db)` → checks expires_at, refreshes proactively, returns fresh headers
   - `get_oauth_headers(server, db)` → decrypt tokens, return as Authorization header dict
3. Unit tests for all service methods (mock httpx responses)

### Phase 2: Proxy Integration + Device Flow Poller

**Deliverables**: Token refresh in proxy, background poller, auth code callback

1. Modify `core/mcp_proxy.py`:
   - Before `get_or_connect()`: if `server.auth_type == "oauth2"`, call `refresh_token_if_needed()`
   - If no tokens exist, call `initiate_device_flow()` or `initiate_auth_code_flow()`, return AUTH_REQUIRED as ProxyResult
   - On 401 from external server: attempt refresh, retry once
   - On refresh failure: return AUTH_REQUIRED
2. Create `tasks/device_flow_poller.py`:
   - `poll_device_code(namespace_id, server_name)` — async task, polls token endpoint at provider interval
   - Handles: `authorization_pending` (continue), `slow_down` (increase interval), `expired_token` (stop), success (store tokens)
   - Redis-keyed to prevent duplicate pollers
3. Create `api/v1/mcp_oauth.py`:
   - `GET /v1/oauth/mcp-callback` — auth code callback (fallback flow only)
   - Validates state from Redis, exchanges code for tokens, stores encrypted
   - Returns HTML success page with informed consent disclosure
4. Register callback router in `main.py`
5. Unit tests for proxy OAuth path + poller + callback

### Phase 3: MCP Tool Integration + Observability

**Deliverables**: add_mcp_server changes, describe output, Prometheus metrics

1. Update `add_mcp_server` tool handler to accept `auth_type` and `oauth_config`
2. Update `update_mcp_server` to handle scope changes (invalidate tokens)
3. Update `describe_mcp_server` to include `oauth_status`, `oauth_scopes`, `oauth_expires_at`
4. Update `remove_mcp_server` to clean up OAuth tokens and Redis state
5. Add Prometheus metrics:
   - `mcpworks_oauth_token_refreshes_total` [namespace, server, status]
   - `mcpworks_oauth_device_flows_total` [namespace, server, status]
   - `mcpworks_oauth_auth_required_total` [namespace, server, flow]
6. Update self-hosting docs with OAuth configuration section

## Complexity Tracking

No constitution violations to justify.

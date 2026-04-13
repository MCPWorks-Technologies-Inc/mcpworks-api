# Data Model: OAuth for MCP Server Proxy

**Feature**: 026-oauth-mcp-proxy | **Date**: 2026-04-12

## Modified Entity: NamespaceMcpServer

### New Columns

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| auth_type | varchar(20) | NO | "bearer" | "bearer", "oauth2", "none" |
| oauth_config_encrypted | bytea | YES | NULL | Encrypted: client_id, client_secret, scopes, device_authorization_endpoint, token_endpoint, auth_endpoint (fallback) |
| oauth_config_dek | bytea | YES | NULL | DEK for oauth_config |
| oauth_tokens_encrypted | bytea | YES | NULL | Encrypted: access_token, refresh_token, token_type, scope |
| oauth_tokens_dek | bytea | YES | NULL | DEK for oauth_tokens |
| oauth_tokens_expires_at | timestamptz | YES | NULL | Access token expiry (plaintext for proactive refresh check without decryption) |

### Encryption Details

`oauth_config_encrypted` stores (via `encrypt_value()`):
```json
{
  "client_id": "...",
  "client_secret": "...",
  "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
  "device_authorization_endpoint": "https://oauth2.googleapis.com/device/code",
  "token_endpoint": "https://oauth2.googleapis.com/token",
  "auth_endpoint": "https://accounts.google.com/o/oauth2/auth",
  "flow": "device"
}
```

`oauth_tokens_encrypted` stores (via `encrypt_value()`):
```json
{
  "access_token": "ya29.a0...",
  "refresh_token": "1//0e...",
  "token_type": "Bearer",
  "scope": "https://www.googleapis.com/auth/gmail.readonly"
}
```

`oauth_tokens_expires_at` stored in plaintext so `proxy_mcp_call()` can check expiry without decrypting (performance: avoid decrypt on every call when token is fresh).

### Validation Rules

- `auth_type` must be one of: "bearer", "oauth2", "none"
- If `auth_type = "oauth2"`, `oauth_config_encrypted` must not be NULL
- If `auth_type = "oauth2"` and `flow = "device"`, `device_authorization_endpoint` must be in config
- `oauth_tokens_expires_at` updated on every token refresh
- Setting `auth_type` to something other than "oauth2" clears all oauth_* columns

### State Transitions

```
No Token → AUTH_REQUIRED (device code issued)
AUTH_REQUIRED → Polling (background task active)
Polling → Tokens Stored (user approved)
Polling → Expired (user never approved, code expired)
Expired → AUTH_REQUIRED (next tool call generates fresh code)

Tokens Stored → Token Refresh (access_token expired, refresh_token valid)
Token Refresh → Tokens Stored (refresh succeeded, new tokens)
Token Refresh → AUTH_REQUIRED (refresh_token revoked/expired)
```

## Redis State (Ephemeral)

| Key Pattern | Value | TTL | Purpose |
|-------------|-------|-----|---------|
| `mcp_oauth_device:{ns_id}:{server}` | JSON: `{device_code, user_code, verification_uri, interval, expires_at}` | Provider-specified (typically 600s) | Active device code — prevents duplicate generation |
| `mcp_oauth_polling:{ns_id}:{server}` | `"1"` | Same as device code | Flag: background poller is active for this server |
| `mcp_oauth_refresh:{ns_id}:{server}` | `"1"` | 30s | Lock: prevent concurrent refresh requests |

## Relationships

```
Namespace (1) → (N) NamespaceMcpServer
  └── auth_type: "bearer" → uses headers_encrypted (existing)
  └── auth_type: "oauth2" → uses oauth_config_encrypted + oauth_tokens_encrypted (new)
  └── auth_type: "none" → no auth headers attached
```

No new tables. No new relationships. All changes are additive columns on existing `namespace_mcp_servers`.

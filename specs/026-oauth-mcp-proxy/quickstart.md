# Quickstart: OAuth MCP Server Proxy

## Register an OAuth-protected MCP Server

```
add_mcp_server(
  name="google_workspace",
  url="https://google-workspace-mcp.example.com/mcp",
  transport="streamable_http",
  auth_type="oauth2",
  oauth_config={
    "client_id": "123456789.apps.googleusercontent.com",
    "client_secret": "GOCSPX-...",
    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
    "device_authorization_endpoint": "https://oauth2.googleapis.com/device/code",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "flow": "device"
  }
)
```

## First Tool Call — HITL Authorization

When the AI calls a tool on an unauthorized OAuth server:

```python
from functions import google_workspace__list_emails
result = google_workspace__list_emails({"max_results": 5})
```

The proxy returns:

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

The AI surfaces this to the user:

> To use Google Workspace, go to **google.com/device** and enter code **WDJB-MJHT**. Let me know when you've approved it.

After the user approves, the background poller detects it and stores the tokens. The AI retries and the call succeeds.

## Subsequent Calls — Transparent

All future tool calls to `google_workspace` work without any user interaction. Token refresh happens silently in the background.

## Authorization Code Fallback

For providers that don't support device flow (e.g., Slack):

```
add_mcp_server(
  name="slack",
  url="https://slack-mcp.example.com/mcp",
  transport="streamable_http",
  auth_type="oauth2",
  oauth_config={
    "client_id": "12345.67890",
    "client_secret": "abc...",
    "scopes": ["chat:write", "channels:read"],
    "auth_endpoint": "https://slack.com/oauth/v2/authorize",
    "token_endpoint": "https://slack.com/api/oauth.v2.access",
    "flow": "authorization_code"
  }
)
```

The proxy returns an `auth_url` instead of a `user_code`:

```json
{
  "auth_required": true,
  "provider": "slack",
  "auth_url": "https://slack.com/oauth/v2/authorize?client_id=...&scope=...&state=...",
  "message": "Authorization required for slack. Open this URL to grant access, then retry.",
  "expires_in": 600,
  "flow": "authorization_code"
}
```

## Check OAuth Status

```
describe_mcp_server(name="google_workspace")
```

Response includes:

```json
{
  "name": "google_workspace",
  "auth_type": "oauth2",
  "oauth_status": "authorized",
  "oauth_scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
  "oauth_expires_at": "2026-04-12T05:30:00Z"
}
```

Possible `oauth_status` values: `"not_configured"`, `"pending_authorization"`, `"authorized"`, `"expired"` (refresh token revoked).

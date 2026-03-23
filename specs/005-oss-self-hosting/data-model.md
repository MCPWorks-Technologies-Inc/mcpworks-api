# Data Model: Open-Source Self-Hosting Readiness

**Date**: 2026-03-22
**Branch**: `005-oss-self-hosting`

## Overview

This feature does not introduce new database tables. It adds configuration settings and a URL builder utility. The data model changes are at the application configuration layer.

## New Configuration Settings

### Settings Class Additions

| Setting | Type | Default | Env Var | Description |
|---------|------|---------|---------|-------------|
| `base_domain` | str | `"mcpworks.io"` | `BASE_DOMAIN` | Root domain for all URL generation |
| `base_scheme` | str | `"https"` | `BASE_SCHEME` | URL scheme (https or http) |
| `allow_registration` | bool | `True` | `ALLOW_REGISTRATION` | Whether public registration is enabled |
| `smtp_host` | str | `""` | `SMTP_HOST` | SMTP server hostname |
| `smtp_port` | int | `587` | `SMTP_PORT` | SMTP server port |
| `smtp_username` | str | `""` | `SMTP_USERNAME` | SMTP authentication username |
| `smtp_password` | str | `""` | `SMTP_PASSWORD` | SMTP authentication password |
| `smtp_from_email` | str | `""` | `SMTP_FROM_EMAIL` | SMTP sender address |
| `smtp_use_tls` | bool | `True` | `SMTP_USE_TLS` | Whether to use STARTTLS |

### Derived Settings (computed from base_domain)

| Property | Derivation | Example |
|----------|-----------|---------|
| `api_domain` | `f"api.{base_domain}"` | `api.selfhost.dev` |
| `jwt_issuer` | `f"{base_scheme}://api.{base_domain}"` | `https://api.selfhost.dev` |
| `jwt_audience` | `f"{base_scheme}://{base_domain}"` | `https://selfhost.dev` |
| `admin_domains` | `{f"api.{base_domain}"}` | `{"api.selfhost.dev"}` |
| `default_cors_origins` | Computed from `base_domain` | `["https://api.selfhost.dev", ...]` |
| `resend_from_email` | `f"noreply@{base_domain}"` (if not explicitly set) | `noreply@selfhost.dev` |

## URL Builder Utility

### Module: `src/mcpworks_api/url_builder.py`

Centralized URL construction replacing all hardcoded domain references.

| Function | Signature | Output Example |
|----------|-----------|---------------|
| `create_url` | `(namespace: str) -> str` | `https://demo.create.selfhost.dev` |
| `run_url` | `(namespace: str) -> str` | `https://demo.run.selfhost.dev` |
| `agent_url` | `(agent_name: str) -> str` | `https://bot.agent.selfhost.dev` |
| `mcp_url` | `(namespace: str, endpoint: str) -> str` | `https://demo.run.selfhost.dev/mcp` |
| `api_url` | `(path: str) -> str` | `https://api.selfhost.dev/v1/health` |
| `view_url` | `(agent_name: str, token: str) -> str` | `https://bot.agent.selfhost.dev/view/abc123/` |
| `chat_url` | `(agent_name: str, token: str) -> str` | `https://bot.agent.selfhost.dev/chat/abc123` |
| `valid_suffixes` | `() -> list[str]` | `[".create.selfhost.dev", ".run.selfhost.dev", ".agent.selfhost.dev"]` |

All functions read from `get_settings().base_domain` and `get_settings().base_scheme`.

## Email Provider Selection Logic

```
Priority order:
1. If RESEND_API_KEY set → ResendProvider
2. If SMTP_HOST set → SmtpProvider
3. Otherwise → ConsoleProvider (logs only)
```

## Billing Mode Detection

```
If STRIPE_SECRET_KEY is set and non-empty → billing enabled (normal operation)
If STRIPE_SECRET_KEY is empty/unset → billing disabled:
  - BillingMiddleware.dispatch() returns early (no checks)
  - /v1/account/usage returns {tier: "self-hosted", billing_enabled: false}
  - /v1/subscriptions returns 404 with {detail: "Billing not configured"}
```

## Files Changed (by category)

### Config Layer (1 file)
- `src/mcpworks_api/config.py` — Add `base_domain`, `base_scheme`, `allow_registration`, SMTP settings

### New Files (3 files)
- `src/mcpworks_api/url_builder.py` — Centralized URL construction
- `src/mcpworks_api/services/smtp_provider.py` — SMTP email provider
- `LICENSE` — BSL 1.1 license text

### Domain Refactor (13 files)
- `src/mcpworks_api/middleware/subdomain.py` — Use `settings.base_domain`
- `src/mcpworks_api/models/namespace.py` — Use `url_builder` for properties
- `src/mcpworks_api/mcp/code_mode.py` — Use `url_builder.run_url()`
- `src/mcpworks_api/mcp/code_mode_ts.py` — Use `url_builder.run_url()`
- `src/mcpworks_api/mcp/run_handler.py` — Use `url_builder` (2 locations)
- `src/mcpworks_api/mcp/create_handler.py` — Use `url_builder` (2 locations)
- `src/mcpworks_api/services/agent_service.py` — Use `url_builder.chat_url()`
- `src/mcpworks_api/services/scratchpad.py` — Use `url_builder.view_url()`
- `src/mcpworks_api/api/v1/health.py` — Use `url_builder.valid_suffixes()`
- `src/mcpworks_api/api/v1/llm.py` — Use `url_builder` for examples
- `src/mcpworks_api/api/v1/scratchpad_view.py` — Use `url_builder`
- `src/mcpworks_api/api/v1/public_chat.py` — Use `url_builder`
- `src/mcpworks_api/api/v1/webhooks.py` — Use `url_builder`

### Admin & Auth (2 files)
- `src/mcpworks_api/main.py` — Derive `_admin_domains` from settings
- `src/mcpworks_api/api/v1/auth.py` — Check `allow_registration`

### Billing (2 files)
- `src/mcpworks_api/middleware/billing.py` — Add billing-disabled bypass
- `src/mcpworks_api/api/v1/account.py` — Self-hosted status response

### Email (2 files)
- `src/mcpworks_api/services/email.py` — Add SMTP to provider selection, pass `base_url` to templates
- `src/mcpworks_api/templates/emails/base.html` — Use `{{ base_url }}` variable

### Deployment (5 new files)
- `docker-compose.self-hosted.yml`
- `Caddyfile.self-hosted`
- `.env.self-hosted.example`
- `scripts/seed_admin.py`
- `docs/SELF-HOSTING.md`

### Existing Files Updated (2 files)
- `README.md` — License badge, self-hosting link
- `Caddyfile` — No changes (production remains as-is)

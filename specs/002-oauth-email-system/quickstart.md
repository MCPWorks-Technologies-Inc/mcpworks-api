# Quickstart: OAuth Social Login & Transactional Email System

**Branch**: `002-oauth-email-system` | **Date**: 2026-02-25

## Prerequisites

1. **OAuth Provider Apps** (project owner must create before implementation):
   - **Google**: [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → Create OAuth 2.0 Client ID
   - **GitHub**: [Developer Settings](https://github.com/settings/developers) → New OAuth App
   - **Microsoft**: [Azure AD App Registrations](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps) → New Registration

2. **Callback URLs** to register with each provider:
   ```
   https://api.mcpworks.io/v1/auth/oauth/google/callback
   https://api.mcpworks.io/v1/auth/oauth/github/callback
   https://api.mcpworks.io/v1/auth/oauth/microsoft/callback
   ```

3. **Resend Account**: [resend.com](https://resend.com) → Sign up, get API key, verify `mcpworks.io` domain (SPF + DKIM DNS records).

## Environment Variables

Add to `.env` (local) and Docker Compose prod environment:

```bash
# OAuth - Google
OAUTH_GOOGLE_CLIENT_ID=
OAUTH_GOOGLE_CLIENT_SECRET=

# OAuth - GitHub
OAUTH_GITHUB_CLIENT_ID=
OAUTH_GITHUB_CLIENT_SECRET=

# OAuth - Microsoft
OAUTH_MICROSOFT_CLIENT_ID=
OAUTH_MICROSOFT_CLIENT_SECRET=

# OAuth state CSRF secret (generate with: python -c "import secrets; print(secrets.token_hex(32))")
OAUTH_STATE_SECRET=

# Email - Resend
RESEND_API_KEY=
RESEND_FROM_EMAIL=noreply@mcpworks.io
```

## New Dependencies

```
authlib>=1.3.0
```

httpx is already a dependency. No other new packages needed.

## Database Migrations

After implementation, run:

```bash
alembic upgrade head
```

This applies three migrations:
1. User model changes (nullable password_hash, new status values, rejection_reason)
2. `oauth_accounts` table
3. `email_logs` table

## New Files

| File | Purpose |
|------|---------|
| `src/mcpworks_api/models/oauth_account.py` | OAuthAccount SQLAlchemy model |
| `src/mcpworks_api/models/email_log.py` | EmailLog SQLAlchemy model |
| `src/mcpworks_api/services/email.py` | Email provider abstraction + ResendProvider |
| `src/mcpworks_api/services/oauth.py` | OAuth flow logic (create/link accounts) |
| `src/mcpworks_api/api/v1/oauth.py` | OAuth router (login redirect + callback) |
| `src/mcpworks_api/templates/emails/` | HTML email templates |
| `alembic/versions/20260225_000001_*.py` | Migration: user model changes |
| `alembic/versions/20260225_000002_*.py` | Migration: oauth_accounts table |
| `alembic/versions/20260225_000003_*.py` | Migration: email_logs table |

## Modified Files

| File | Change |
|------|--------|
| `src/mcpworks_api/config.py` | Add OAuth + Resend settings |
| `src/mcpworks_api/models/user.py` | Add PENDING_APPROVAL, REJECTED statuses; nullable password_hash; rejection_reason |
| `src/mcpworks_api/models/__init__.py` | Export OAuthAccount, EmailLog |
| `src/mcpworks_api/services/auth.py` | Set pending_approval for email/password registrations; status-specific login errors |
| `src/mcpworks_api/dependencies.py` | Add require_active_status dependency |
| `src/mcpworks_api/api/v1/admin.py` | Add pending-approvals, approve, reject endpoints |
| `src/mcpworks_api/main.py` | Register OAuth router; initialize Authlib OAuth |
| `src/mcpworks_api/static/onboarding.html` | Add OAuth provider buttons |
| `src/mcpworks_api/static/admin.html` | Add pending approvals section |
| `docker-compose.prod.yml` | Add OAuth + Resend env vars |

## Testing

```bash
# Unit tests
pytest tests/unit/test_oauth_service.py -v
pytest tests/unit/test_email_service.py -v
pytest tests/unit/test_admin_approval.py -v

# Integration tests (requires running postgres + redis)
pytest tests/integration/test_oauth_flow.py -v
pytest tests/integration/test_email_delivery.py -v
```

## Verification

After deployment:

1. Visit `https://api.mcpworks.io/login` — should show OAuth provider buttons
2. Click "Sign in with Google" — should redirect to Google consent screen
3. Complete Google login — should return to dashboard with JWT
4. Register with email/password — should show "pending approval" message
5. Visit `https://api.mcpworks.io/admin` — should show pending approvals section
6. Approve the pending user — user should receive approval email

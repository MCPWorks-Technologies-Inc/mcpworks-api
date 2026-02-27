# Research: OAuth Social Login & Transactional Email System

**Branch**: `002-oauth-email-system` | **Date**: 2026-02-25

## R-001: OAuth Library Choice

**Decision**: Authlib (Starlette integration)

**Rationale**: Authlib is a mature, well-maintained library with native Starlette/FastAPI support. It handles the full OAuth 2.0 + OpenID Connect flow: state generation, CSRF protection, PKCE, token exchange, and ID token parsing. The alternative (httpx-oauth / fastapi-users) would require replacing the existing AuthService, which is undesirable.

**Alternatives considered**:
- `fastapi-users` + `httpx-oauth`: Would replace the entire auth system. Too disruptive.
- `fastapi-sso`: Lightweight but less configurable. No PKCE support.
- Raw `httpx` calls: Maximum control but significant boilerplate for three providers.

## R-002: OAuth State Storage

**Decision**: Use Redis cache (existing infrastructure), not SessionMiddleware.

**Rationale**: Authlib accepts a `cache` object with `get`/`set`/`delete` async methods. A thin `RedisOAuthCache` adapter (~10 lines) plugs into the existing Redis instance already used for rate limiting. This avoids adding `SessionMiddleware`, avoids 4KB cookie size limits, and keeps state server-side.

**Alternatives considered**:
- `SessionMiddleware` with `itsdangerous`: Adds a dependency, stores state in cookies (client-visible), 4KB limit.
- In-memory dict: Not production-safe (lost on restart, no multi-instance support).

## R-003: Provider Configuration

**Decision**: Use OIDC discovery for Google and Microsoft. Use explicit URLs for GitHub.

| Provider  | Protocol | Discovery URL | Tenant |
|-----------|----------|---------------|--------|
| Google    | OIDC     | `https://accounts.google.com/.well-known/openid-configuration` | N/A |
| Microsoft | OIDC     | `https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration` | `common` (personal + work) |
| GitHub    | OAuth 2.0 | N/A (no OIDC support) | N/A |

**Microsoft `common` tenant**: Allows both personal and work/school Microsoft accounts. Requires skipping issuer validation in ID token because the issuer varies by tenant. Pass `claims_options={"iss": {"essential": True, "values": None}}` during token exchange.

**GitHub email quirk**: The `/user` endpoint returns `email: null` when the user's email is private (common case). Must call `/user/emails` separately to get the primary verified email. The `user:email` scope grants access.

**PKCE**: Enable `code_challenge_method: "S256"` for Google and Microsoft. Recommended by both providers for additional security.

## R-004: Email Provider

**Decision**: Resend (direct httpx integration, no SDK).

**Rationale**: Resend's API is a single POST endpoint (`https://api.resend.com/emails`) accepting a flat JSON body. Since httpx is already a dependency, we call it directly with native async support. No need for the `resend` PyPI package (which is synchronous). 3,000 emails/month free tier covers current scale.

**Alternatives considered**:
- SendGrid: No free tier (killed May 2025). $19.95/mo minimum. Sync SDK only.
- Postmark: Best deliverability but 100/mo free tier is impractical. 10MB attachment limit.
- AWS SES: Cheapest per-email but introduces AWS dependency, sandbox escape delay, bounce/complaint management via SNS.

## R-005: User Status Flow

**Decision**: Add `pending_approval` and `rejected` to `UserStatus` enum. Modify registration to set `pending_approval` for email/password signups. OAuth signups remain `active`.

**Current state** (`models/user.py:28-33`): `ACTIVE`, `SUSPENDED`, `DELETED`

**New transitions**:
```
[email/password registration] → pending_approval → active (admin approves)
                                                  → rejected (admin rejects)
[OAuth registration] → active (bypasses approval)
```

**Login enforcement**: The existing `AuthService.login_user()` at `services/auth.py:376-379` already blocks non-active users but returns a generic "User account is not active" message. This needs to be split into status-specific messages for `pending_approval` and `rejected`.

**Token issuance**: Currently `register_user()` issues JWTs immediately at line 328. For `pending_approval` users, tokens must NOT be issued. Return a confirmation response without tokens instead.

## R-006: Dependency Enforcement

**Decision**: The existing `get_current_user_id()` does NOT check user status (no DB lookup). Add a new `require_active_status()` dependency that checks the user's status, following the `require_admin()` pattern.

**Alternative considered**: Adding status to JWT claims. Rejected because status can change (admin approval) and we don't want to invalidate tokens. A DB check on protected endpoints is more reliable.

## R-007: Provider Abstraction for Email

**Decision**: Abstract email sending behind an `EmailProvider` protocol class. Initial implementation: `ResendProvider` using direct httpx calls. The provider is selected via `settings.email_provider` config.

**Pattern**: Follows the existing provider abstraction principle (Constitution IV) and mirrors the codebase's pattern of abstracting external services.

## R-008: Alembic Migration Convention

**Decision**: Follow existing convention: `YYYYMMDD_000NNN_description.py`. Latest migration: `20260219_000001`. Next: `20260225_000001`.

**Migrations needed**:
1. Add `pending_approval` and `rejected` to user status, make `password_hash` nullable, add `rejection_reason` column.
2. Create `oauth_accounts` table.
3. Create `email_logs` table.

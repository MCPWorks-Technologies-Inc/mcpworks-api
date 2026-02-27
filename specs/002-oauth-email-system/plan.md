# Implementation Plan: OAuth Social Login & Transactional Email System

**Branch**: `002-oauth-email-system` | **Date**: 2026-02-25 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-oauth-email-system/spec.md`

## Summary

Add OAuth 2.0 social login (Google, GitHub, Microsoft) using Authlib with Redis-backed state storage, implement admin-gated email/password registration with new `pending_approval`/`rejected` user statuses, and build an async transactional email system using Resend (via direct httpx calls) with a pluggable provider abstraction. All three subsystems integrate with the existing audit log and security event pipeline.

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, Authlib 1.3+ (new), httpx (existing)
**Storage**: PostgreSQL 15+ (existing), Redis 7+ (existing, also used for OAuth state storage)
**Testing**: pytest + pytest-asyncio (existing)
**Target Platform**: Linux server (DigitalOcean droplet, Docker Compose)
**Project Type**: Single project (API server)
**Performance Goals**: OAuth callback < 2s server-side; email dispatch < 100ms (async, non-blocking)
**Constraints**: No new infrastructure dependencies; must integrate with existing ES256 JWT system
**Scale/Scope**: ~12 current users, growing. 3 OAuth providers. 5 email types at launch.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec complete, all clarifications resolved. Plan follows spec. |
| II. Token Efficiency | PASS | OAuth callback returns minimal JWT response (~200 tokens). Admin endpoints return references. |
| III. Transaction Safety | PASS | OAuth account creation + user creation in single DB transaction. Email is fire-and-forget (non-blocking). |
| IV. Provider Abstraction | PASS | Email provider abstracted behind `EmailProvider` protocol. OAuth uses Authlib (provider-agnostic). |
| V. API Contracts & Coverage | PASS | OpenAPI contracts defined. Unit + integration test strategy covers all flows. |

**Post-design re-check**: All gates still pass. No violations detected.

## Project Structure

### Documentation (this feature)

```text
specs/002-oauth-email-system/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: technology decisions
├── data-model.md        # Phase 1: entity definitions and migrations
├── quickstart.md        # Phase 1: setup guide
├── contracts/           # Phase 1: OpenAPI definitions
│   └── oauth-endpoints.yaml
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── models/
│   ├── user.py              # Modified: new statuses, nullable password_hash, rejection_reason
│   ├── oauth_account.py     # New: OAuth identity model
│   ├── email_log.py         # New: outbound email audit model
│   └── __init__.py          # Modified: export new models
├── services/
│   ├── auth.py              # Modified: pending_approval flow, status-specific errors
│   ├── oauth.py             # New: OAuth account creation/linking logic
│   └── email.py             # New: EmailProvider abstraction + ResendProvider
├── api/v1/
│   ├── auth.py              # Modified: registration returns pending status
│   ├── oauth.py             # New: OAuth login + callback routes
│   └── admin.py             # Modified: pending-approvals, approve, reject endpoints
├── core/
│   └── oauth_cache.py       # New: RedisOAuthCache adapter for Authlib
├── templates/
│   └── emails/              # New: HTML email templates
│       ├── base.html
│       ├── welcome.html
│       ├── registration_pending.html
│       ├── admin_new_registration.html
│       ├── account_approved.html
│       └── account_rejected.html
├── static/
│   ├── onboarding.html      # Modified: add OAuth buttons
│   └── admin.html           # Modified: add pending approvals section
├── config.py                # Modified: OAuth + Resend settings
├── dependencies.py          # Modified: add require_active_status
└── main.py                  # Modified: register OAuth router, init Authlib

alembic/versions/
├── 20260225_000001_oauth_user_status_changes.py
├── 20260225_000002_create_oauth_accounts.py
└── 20260225_000003_create_email_logs.py

tests/
├── unit/
│   ├── test_oauth_service.py
│   ├── test_email_service.py
│   └── test_admin_approval.py
└── integration/
    ├── test_oauth_flow.py
    └── test_email_delivery.py
```

**Structure Decision**: Extends the existing single-project structure. New models, services, and routes follow established patterns. No new top-level directories introduced.

## Key Technical Decisions

### 1. OAuth State via Redis (not SessionMiddleware)

Authlib accepts a `cache` object for OAuth state storage. A thin `RedisOAuthCache` adapter plugs into the existing Redis instance. This avoids adding `SessionMiddleware`, keeps state server-side, and reuses existing infrastructure.

### 2. Direct httpx for Resend (no SDK)

Resend's API is a single POST endpoint. Since httpx is already a dependency, calling it directly gives native async with zero new packages. The `resend` PyPI SDK is synchronous and would require `asyncio.to_thread()` wrapping.

### 3. Email as Fire-and-Forget

Email dispatch uses `asyncio.create_task()` — the same pattern as existing security events (`fire_security_event()`). Primary requests (OAuth callback, registration, approval) are never blocked by email delivery. Retry logic runs within the background task.

### 4. Status Enforcement via Dependency

A new `require_active_status` dependency checks user status on protected endpoints. This follows the existing `require_admin()` pattern and does a DB lookup. Status is NOT embedded in JWT claims because status can change (admin approval) after token issuance.

### 5. GitHub Email Workaround

GitHub's `/user` endpoint often returns `email: null`. The callback handler makes a second API call to `/user/emails` to get the primary verified email. This is a well-documented GitHub quirk.

### 6. Microsoft Multi-Tenant

Using the `common` tenant to accept both personal and work/school Microsoft accounts. Requires skipping issuer validation in ID token parsing (`claims_options={"iss": {"essential": True, "values": None}}`).

## Complexity Tracking

No Constitution violations. No complexity justifications needed.

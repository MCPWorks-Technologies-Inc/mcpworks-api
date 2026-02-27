# Data Model: OAuth Social Login & Transactional Email System

**Branch**: `002-oauth-email-system` | **Date**: 2026-02-25

## Entity Changes

### User (modified)

**File**: `src/mcpworks_api/models/user.py`

| Field | Type | Change | Notes |
|-------|------|--------|-------|
| `password_hash` | String(255) | `nullable=False` → `nullable=True` | OAuth-only users have no password |
| `status` | String(20) | Add enum values | Add `pending_approval`, `rejected` |
| `rejection_reason` | String(500), nullable | **New** | Admin-provided reason when rejecting account |

**Updated UserStatus enum**:
```
ACTIVE = "active"
PENDING_APPROVAL = "pending_approval"
REJECTED = "rejected"
SUSPENDED = "suspended"
DELETED = "deleted"
```

**Updated state transitions**:
```
[email/password] → pending_approval → active       (admin approves)
                                    → rejected      (admin rejects)
[OAuth]          → active
active           → suspended → active
                             → deleted
active           → deleted
```

### OAuthAccount (new)

**File**: `src/mcpworks_api/models/oauth_account.py`

| Field | Type | Nullable | Notes |
|-------|------|----------|-------|
| `id` | UUID | No | Primary key (UUIDMixin) |
| `user_id` | UUID (FK → users.id) | No | Owning user |
| `provider` | String(50) | No | `google`, `github`, `microsoft` |
| `provider_user_id` | String(255) | No | Provider's unique user identifier |
| `provider_email` | String(255) | No | Email from provider at time of linking |
| `created_at` | DateTime(tz) | No | TimestampMixin |
| `updated_at` | DateTime(tz) | No | TimestampMixin |

**Constraints**:
- Unique: `(provider, provider_user_id)` — one identity per provider
- Unique: `(user_id, provider)` — one provider link per user
- Index: `provider_user_id` for fast lookup during OAuth callback

**Relationships**:
- `OAuthAccount.user` → `User` (many-to-one)
- `User.oauth_accounts` → `[OAuthAccount]` (one-to-many)

### EmailLog (new)

**File**: `src/mcpworks_api/models/email_log.py`

| Field | Type | Nullable | Notes |
|-------|------|----------|-------|
| `id` | UUID | No | Primary key (UUIDMixin) |
| `recipient` | String(255) | No | Recipient email address |
| `email_type` | String(50) | No | `welcome`, `registration_pending`, `admin_new_registration`, `account_approved`, `account_rejected` |
| `subject` | String(500) | No | Email subject line |
| `status` | String(20) | No | `sent`, `failed`, `retrying` |
| `provider_message_id` | String(255) | Yes | ID from Resend API response |
| `error_message` | String(1000) | Yes | Error detail on failure |
| `retry_count` | Integer | No | Default 0, max 3 |
| `created_at` | DateTime(tz) | No | TimestampMixin |
| `updated_at` | DateTime(tz) | No | TimestampMixin |

**Constraints**:
- Index: `(email_type, created_at)` for audit queries
- Index: `(recipient, created_at)` for per-user email history

## Migration Plan

### Migration 1: `20260225_000001_oauth_user_status_changes`

```
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE users ADD COLUMN rejection_reason VARCHAR(500);
-- Status enum values are strings, no DDL change needed for new values
```

### Migration 2: `20260225_000002_create_oauth_accounts`

```
CREATE TABLE oauth_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    provider_user_id VARCHAR(255) NOT NULL,
    provider_email VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_user_id),
    UNIQUE (user_id, provider)
);
CREATE INDEX idx_oauth_accounts_provider_user_id ON oauth_accounts(provider_user_id);
CREATE INDEX idx_oauth_accounts_user_id ON oauth_accounts(user_id);
```

### Migration 3: `20260225_000003_create_email_logs`

```
CREATE TABLE email_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient VARCHAR(255) NOT NULL,
    email_type VARCHAR(50) NOT NULL,
    subject VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'sent',
    provider_message_id VARCHAR(255),
    error_message VARCHAR(1000),
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_email_logs_type_created ON email_logs(email_type, created_at);
CREATE INDEX idx_email_logs_recipient_created ON email_logs(recipient, created_at);
```

# Auth Data Model (MVP)

**Source:** Adapted from mcpworks-auth specs/001-oauth-server/data-model.md
**Date:** 2025-12-16

## Entity Relationship Diagram

```
┌─────────────────┐       ┌──────────────────┐
│      User       │       │     APIKey       │
├─────────────────┤       ├──────────────────┤
│ id (PK)         │◄──────│ user_id (FK)     │
│ email           │       │ id (PK)          │
│ email_verified  │       │ key_hash         │
│ password_hash   │       │ key_prefix       │
│ name            │       │ name             │
│ tier            │       │ scopes           │
│ created_at      │       │ last_used_at     │
│ updated_at      │       │ expires_at       │
└────────┬────────┘       │ revoked_at       │
         │                │ created_at       │
         │ 1:N            └──────────────────┘
         ▼                         │
┌─────────────────────┐           │ 1:N
│   RefreshToken      │           ▼
├─────────────────────┤   ┌──────────────────────┐
│ token_hash (PK)     │   │      AuditEvent      │
│ user_id (FK)        │   ├──────────────────────┤
│ api_key_id (FK)     │   │ id (PK)              │
│ scope               │   │ event_type           │
│ expires_at          │   │ user_id              │
│ revoked_at          │   │ ip_address_hash      │
│ created_at          │   │ user_agent           │
└─────────────────────┘   │ details              │
                          │ created_at           │
┌─────────────────────┐   └──────────────────────┘
│    SigningKey       │
├─────────────────────┤
│ kid (PK)            │
│ private_key_enc     │
│ public_key          │
│ algorithm           │
│ active              │
│ created_at          │
│ activated_at        │
│ deactivated_at      │
└─────────────────────┘
```

---

## Entities

### 1. User

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | VARCHAR(26) | PK | ULID with `usr_` prefix |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL | User's email |
| `email_verified` | BOOLEAN | DEFAULT FALSE | Verification status |
| `password_hash` | VARCHAR(255) | NULL | Argon2id hash |
| `name` | VARCHAR(255) | NULL | Display name |
| `tier` | VARCHAR(20) | DEFAULT 'free' | free, pro, enterprise |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | Last modification |

**Validation:**
- Email: RFC 5322 format
- Tier: `free`, `pro`, `enterprise`
- Password: 12+ characters

---

### 2. APIKey

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | VARCHAR(26) | PK | ULID with `key_` prefix |
| `user_id` | VARCHAR(26) | FK → User | Owner |
| `key_hash` | VARCHAR(64) | NOT NULL | SHA-256 of full key |
| `key_prefix` | VARCHAR(20) | NOT NULL | Display prefix (sk_live_k1_) |
| `name` | VARCHAR(255) | NULL | User-assigned name |
| `scopes` | VARCHAR(1024) | NULL | Space-separated scopes |
| `last_used_at` | TIMESTAMP | NULL | Last API call |
| `expires_at` | TIMESTAMP | NULL | Expiration (NULL = never) |
| `revoked_at` | TIMESTAMP | NULL | Revocation time |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Creation time |

**Key Format:** `sk_{env}_{keyID}_{random}`
- env: `live` or `test`
- keyID: `k1`, `k2`, etc. (for rotation)
- random: 32 bytes Base62

---

### 3. RefreshToken

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `token_hash` | VARCHAR(64) | PK | SHA-256 of token |
| `user_id` | VARCHAR(26) | FK → User | Token owner |
| `api_key_id` | VARCHAR(26) | FK → APIKey | Source key (optional) |
| `scope` | VARCHAR(1024) | NULL | Granted scopes |
| `expires_at` | TIMESTAMP | NOT NULL | 7 days from creation |
| `revoked_at` | TIMESTAMP | NULL | Revocation time |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Creation time |

**Behavior:**
- Single-use (new token issued on refresh)
- Old token invalidated after use

---

### 4. SigningKey

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `kid` | VARCHAR(50) | PK | Key identifier |
| `private_key_encrypted` | BYTEA | NOT NULL | AES-256-GCM encrypted |
| `public_key` | TEXT | NOT NULL | PEM-encoded |
| `algorithm` | VARCHAR(10) | NOT NULL | ES256 |
| `active` | BOOLEAN | DEFAULT FALSE | Currently signing |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Generation time |
| `activated_at` | TIMESTAMP | NULL | Signing start |
| `deactivated_at` | TIMESTAMP | NULL | Signing end |

**Naming:** `mcpworks-api-{year}-{seq}` (e.g., `mcpworks-api-2025-001`)

**Key Rotation:**
- New key added 7 days before activation
- Old key retained 7 days after deactivation

---

### 5. AuditEvent

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BIGSERIAL | PK | Auto-incrementing |
| `event_type` | VARCHAR(50) | NOT NULL | Event category |
| `user_id` | VARCHAR(26) | NULL | Related user |
| `ip_address_hash` | VARCHAR(64) | NULL | SHA-256 of IP |
| `user_agent` | VARCHAR(512) | NULL | Truncated UA |
| `details` | JSONB | NULL | Event metadata |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Event time |

**Event Types:**
- `token_issued` - JWT created
- `token_refreshed` - Refresh used
- `token_revoked` - Token invalidated
- `login_success` - Authentication success
- `login_failed` - Authentication failed
- `key_created` - API key created
- `key_rotated` - API key rotated
- `key_revoked` - API key revoked

---

## Indexes

```sql
-- User lookups
CREATE UNIQUE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_tier ON users(tier);

-- API key lookups
CREATE INDEX idx_api_keys_user ON api_keys(user_id);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);

-- Refresh token cleanup
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_expires ON refresh_tokens(expires_at);

-- Active signing key (only one)
CREATE UNIQUE INDEX idx_signing_keys_active ON signing_keys(active) WHERE active = TRUE;

-- Audit queries
CREATE INDEX idx_audit_created ON audit_events(created_at);
CREATE INDEX idx_audit_user ON audit_events(user_id);
CREATE INDEX idx_audit_type ON audit_events(event_type);
```

---

## Data Volume Estimates

| Entity | Initial (1K users) | Target (10K users) |
|--------|--------------------|--------------------|
| Users | 1,000 | 10,000 |
| API Keys | 3,000 | 30,000 |
| Refresh Tokens (live) | 5,000 | 50,000 |
| Audit Events (90 days) | 300K | 3M |
| Signing Keys | 2-3 | 2-3 |

# Data Model: API Gateway MVP

**Feature**: 001-api-gateway-mvp
**Date**: 2025-12-16
**Database**: PostgreSQL 15+

## Entity Relationship Diagram

```
┌─────────────┐       ┌─────────────┐       ┌──────────────────┐
│    User     │───────│   APIKey    │       │   Subscription   │
│             │ 1   n │             │       │                  │
│ id (PK)     │       │ id (PK)     │       │ id (PK)          │
│ email       │       │ user_id(FK) │       │ user_id (FK, UQ) │
│ password    │       │ key_hash    │       │ tier             │
│ name        │       │ key_prefix  │       │ status           │
│ tier        │       │ scopes      │       │ stripe_*         │
│ status      │       │ expires_at  │       │ period_*         │
│ created_at  │       │ revoked_at  │       │ created_at       │
└──────┬──────┘       └─────────────┘       └──────────────────┘
       │
       │ 1
       │
       ▼ 1
┌─────────────┐       ┌──────────────────────┐
│   Credit    │───────│  CreditTransaction   │
│             │ 1   n │                      │
│ user_id(PK) │       │ id (PK)              │
│ available   │       │ user_id (FK)         │
│ held        │       │ type                 │
│ lifetime_*  │       │ amount               │
│ updated_at  │       │ balance_before/after │
└─────────────┘       │ hold_id              │
                      │ execution_id         │
                      │ metadata             │
                      │ created_at           │
                      └──────────────────────┘

┌─────────────┐       ┌─────────────┐
│   Service   │       │  AuditLog   │
│             │       │             │
│ id (PK)     │       │ id (PK)     │
│ name (UQ)   │       │ user_id(FK) │
│ url         │       │ action      │
│ health_url  │       │ resource_*  │
│ credit_cost │       │ ip_address  │
│ tier_req    │       │ metadata    │
│ status      │       │ created_at  │
└─────────────┘       └─────────────┘
```

---

## Entities

### User

Account holder who can authenticate and use platform services.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, default gen_random_uuid() | Unique identifier |
| email | VARCHAR(255) | UNIQUE, NOT NULL | Login email |
| password_hash | VARCHAR(255) | NOT NULL | Argon2id hash |
| name | VARCHAR(255) | | Display name |
| tier | VARCHAR(20) | NOT NULL, CHECK(free/starter/pro/enterprise), default 'free' | Subscription tier |
| status | VARCHAR(20) | NOT NULL, CHECK(active/suspended/deleted), default 'active' | Account status |
| email_verified | BOOLEAN | default FALSE | Email verification status |
| verification_token | VARCHAR(255) | | Token for email verification |
| created_at | TIMESTAMPTZ | default NOW() | Creation timestamp |
| updated_at | TIMESTAMPTZ | default NOW() | Last update timestamp |

**Indexes**:
- `idx_users_email` on (email)
- `idx_users_status` on (status)

**State Transitions**:
```
[new] → active → suspended → active
                          → deleted
       active → deleted
```

---

### APIKey

Credential for programmatic access to the API.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, default gen_random_uuid() | Unique identifier |
| user_id | UUID | FK → users(id) ON DELETE CASCADE, NOT NULL | Owner |
| key_hash | VARCHAR(255) | UNIQUE, NOT NULL | Argon2id hash of full key |
| key_prefix | VARCHAR(20) | NOT NULL | First 12 chars for identification |
| name | VARCHAR(100) | | Human-readable label |
| scopes | TEXT[] | default ['read','write','execute'] | Permissions |
| last_used_at | TIMESTAMPTZ | | Last usage timestamp |
| created_at | TIMESTAMPTZ | default NOW() | Creation timestamp |
| expires_at | TIMESTAMPTZ | | Expiration (null = never) |
| revoked_at | TIMESTAMPTZ | | Revocation timestamp (null = active) |

**Indexes**:
- `idx_api_keys_user` on (user_id)
- `idx_api_keys_hash` on (key_hash)
- `idx_api_keys_prefix` on (key_prefix)

**Validation Rules**:
- key_prefix format: `sk_{env}_k{n}_` (e.g., `sk_live_k1_a`)
- scopes must be subset of ['read', 'write', 'execute', 'admin']
- expires_at must be in future at creation time

---

### Credit

Balance tracking for a user. One row per user.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| user_id | UUID | PK, FK → users(id) ON DELETE CASCADE | User reference |
| available_balance | DECIMAL(10,2) | NOT NULL, CHECK >= 0, default 0 | Spendable credits |
| held_balance | DECIMAL(10,2) | NOT NULL, CHECK >= 0, default 0 | Reserved credits |
| lifetime_earned | DECIMAL(10,2) | NOT NULL, default 0 | Total credits ever received |
| lifetime_spent | DECIMAL(10,2) | NOT NULL, default 0 | Total credits ever charged |
| updated_at | TIMESTAMPTZ | default NOW() | Last modification |

**Computed**:
- `total_balance` = available_balance + held_balance (can be computed column or application logic)

**Invariants**:
- available_balance >= 0 (enforced by CHECK constraint)
- held_balance >= 0 (enforced by CHECK constraint)
- lifetime_earned >= lifetime_spent (business logic)

---

### CreditTransaction

Audit trail for all credit operations.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, default gen_random_uuid() | Unique identifier |
| user_id | UUID | FK → users(id) ON DELETE CASCADE, NOT NULL | User reference |
| type | VARCHAR(20) | NOT NULL, CHECK(hold/commit/release/purchase/grant/refund) | Transaction type |
| amount | DECIMAL(10,2) | NOT NULL | Credit amount (positive for credit, negative for debit) |
| balance_before | DECIMAL(10,2) | NOT NULL | Balance before transaction |
| balance_after | DECIMAL(10,2) | NOT NULL | Balance after transaction |
| hold_id | UUID | FK → credit_transactions(id) | Reference to original HOLD (for commit/release) |
| execution_id | UUID | | External reference to workflow execution |
| metadata | JSONB | | Additional context (stripe_payment_id, reason, etc.) |
| created_at | TIMESTAMPTZ | default NOW() | Transaction timestamp |

**Indexes**:
- `idx_credit_txn_user` on (user_id)
- `idx_credit_txn_hold` on (hold_id) WHERE hold_id IS NOT NULL
- `idx_credit_txn_created` on (created_at DESC)
- `idx_credit_txn_type` on (type)

**Transaction Types**:
| Type | Amount Sign | Description |
|------|-------------|-------------|
| hold | negative | Credits moved from available to held |
| commit | negative | Credits deducted from held (charge user) |
| release | positive | Credits returned from held to available |
| purchase | positive | Credits added via payment |
| grant | positive | Credits added via subscription or promo |
| refund | positive | Credits returned due to error/dispute |

---

### Subscription

Stripe subscription state for a user. One row per user (or null).

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, default gen_random_uuid() | Unique identifier |
| user_id | UUID | FK → users(id) ON DELETE CASCADE, UNIQUE, NOT NULL | User reference |
| tier | VARCHAR(20) | NOT NULL, CHECK(free/starter/pro/enterprise) | Subscription tier |
| status | VARCHAR(20) | NOT NULL, CHECK(active/cancelled/past_due/trialing) | Subscription status |
| stripe_subscription_id | VARCHAR(255) | UNIQUE | Stripe subscription ID |
| stripe_customer_id | VARCHAR(255) | | Stripe customer ID |
| current_period_start | TIMESTAMPTZ | NOT NULL | Billing period start |
| current_period_end | TIMESTAMPTZ | NOT NULL | Billing period end |
| cancel_at_period_end | BOOLEAN | default FALSE | Pending cancellation |
| created_at | TIMESTAMPTZ | default NOW() | Creation timestamp |
| updated_at | TIMESTAMPTZ | default NOW() | Last update timestamp |

**Indexes**:
- `idx_subscriptions_user` on (user_id)
- `idx_subscriptions_stripe` on (stripe_subscription_id)

**Tier Credits**:
| Tier | Monthly Credits |
|------|-----------------|
| free | 500 |
| starter | 2,900 |
| pro | 9,900 |
| enterprise | Custom |

---

### Service

Registry of backend services for routing.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, default gen_random_uuid() | Unique identifier |
| name | VARCHAR(100) | UNIQUE, NOT NULL | Service identifier (e.g., 'math', 'agent') |
| display_name | VARCHAR(255) | | Human-readable name |
| description | TEXT | | Service description |
| url | VARCHAR(255) | NOT NULL | Base URL for routing |
| health_check_url | VARCHAR(255) | | Health check endpoint |
| credit_cost | DECIMAL(10,2) | NOT NULL, default 0 | Credits per call |
| tier_required | VARCHAR(20) | NOT NULL, CHECK(free/starter/pro/enterprise), default 'free' | Minimum tier |
| status | VARCHAR(20) | NOT NULL, CHECK(active/inactive/degraded), default 'active' | Health status |
| last_health_check | TIMESTAMPTZ | | Last health check timestamp |
| created_at | TIMESTAMPTZ | default NOW() | Creation timestamp |
| updated_at | TIMESTAMPTZ | default NOW() | Last update timestamp |

**Indexes**:
- `idx_services_name` on (name)
- `idx_services_status` on (status)

---

### AuditLog

Security and compliance audit trail.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, default gen_random_uuid() | Unique identifier |
| user_id | UUID | FK → users(id) ON DELETE SET NULL | User who performed action (null for system) |
| action | VARCHAR(50) | NOT NULL | Action type (e.g., 'login', 'api_key_created') |
| resource_type | VARCHAR(50) | | Affected resource type |
| resource_id | UUID | | Affected resource ID |
| ip_address | INET | | Client IP address |
| user_agent | TEXT | | Client user agent |
| metadata | JSONB | | Additional context |
| created_at | TIMESTAMPTZ | default NOW() | Event timestamp |

**Indexes**:
- `idx_audit_user` on (user_id)
- `idx_audit_action` on (action)
- `idx_audit_created` on (created_at DESC)
- `idx_audit_resource` on (resource_type, resource_id)

**Common Actions**:
- `user_registered`, `user_login`, `user_logout`
- `api_key_created`, `api_key_revoked`
- `credit_hold`, `credit_commit`, `credit_release`
- `subscription_created`, `subscription_cancelled`
- `service_routed`, `service_error`

---

## Database Constraints

### Check Constraints

```sql
-- Credit balance must never go negative
ALTER TABLE credits ADD CONSTRAINT chk_available_non_negative
    CHECK (available_balance >= 0);

ALTER TABLE credits ADD CONSTRAINT chk_held_non_negative
    CHECK (held_balance >= 0);

-- Valid tier values
ALTER TABLE users ADD CONSTRAINT chk_user_tier
    CHECK (tier IN ('free', 'starter', 'pro', 'enterprise'));

-- Valid status values
ALTER TABLE users ADD CONSTRAINT chk_user_status
    CHECK (status IN ('active', 'suspended', 'deleted'));
```

### Foreign Keys

All foreign keys use `ON DELETE CASCADE` to ensure data integrity when users are deleted.

### Unique Constraints

- `users.email` - One account per email
- `subscriptions.user_id` - One subscription per user
- `services.name` - Service names must be unique
- `api_keys.key_hash` - Key hashes must be unique

---

## Migration Strategy

Migrations managed via Alembic with these conventions:

1. **Naming**: `YYYYMMDD_HHMM_description.py` (e.g., `20251216_1430_create_users_table.py`)
2. **Reversibility**: All migrations must have `downgrade()` function
3. **Data migrations**: Separate from schema migrations
4. **Zero-downtime**: Use `ADD COLUMN` with defaults, avoid `ALTER COLUMN` type changes

### Initial Migration Order

1. Create `users` table
2. Create `api_keys` table (depends on users)
3. Create `credits` table (depends on users)
4. Create `credit_transactions` table (depends on users, self-reference)
5. Create `subscriptions` table (depends on users)
6. Create `services` table (standalone)
7. Create `audit_logs` table (depends on users)
8. Seed initial services (math, agent)

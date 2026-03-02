# Plan: Stripe Billing — Value Ladder + Annual Billing + Promotions

## Context

The mcpworks-api has a working Stripe integration built for the old Founder pricing (`founder`=$29, `founder_pro`=$59, `enterprise`=$129). The approved Value Ladder pricing (PRICING.md v5.0.0) uses different tier names, prices, and limits. This plan updates the entire billing apparatus to match, adds annual billing, Customer Portal, Stripe Tax, promotion codes, and admin tier overrides.

**Tier mapping:**

| | Old Name | New Name | Old Price | New Price | Old Exec/mo | New Exec/mo |
|-|----------|----------|-----------|-----------|-------------|-------------|
| Free | free | free | $0 | $0 | 100 | 100 |
| Paid 1 | founder | **builder** | $29 | **$49** | 1,000 | **2,500** |
| Paid 2 | founder_pro | **pro** | $59 | **$149** | 10,000 | **15,000** |
| Paid 3 | enterprise | enterprise | $129 | **$499** | 100,000 | 100,000 |

Annual: pay 10, get 12 → $490 / $1,490 / $4,990 per year.

## Pre-deploy: Stripe Dashboard Setup

Before any code deploys, the following must be configured in the Stripe Dashboard:

1. **Create Products + Prices** — 6 price objects (monthly+annual per paid tier). Record the `price_xxx` IDs for `.env`.
2. **Enable Stripe Tax** — Settings → Tax → Enable, add tax registrations for applicable jurisdictions.
3. **Configure Customer Portal** — Settings → Billing → Customer Portal → Enable. Allow: cancel, upgrade/downgrade between builder/pro/enterprise prices, invoice history, payment method updates.
4. **Create initial coupons** (optional) — e.g., `LAUNCH` (100% off 1 month), `EARLYBIRD` (50% off 3 months).

## Changes

### 1. Alembic Migration — tier rename + new columns

**New file:** `alembic/versions/20260301_000003_value_ladder_tiers.py`

The initial schema (20251217_000001) created CHECK constraints with `('free', 'starter', 'pro', 'enterprise')`. The app code later used `founder`/`founder_pro` but no migration updated the constraints. All users are currently `free` tier (Stripe prices are still placeholders), so no data actually violates constraints. This migration:

- Drops and recreates CHECK constraints on `users.tier`, `subscriptions.tier`, `services.tier_required` with `('free', 'builder', 'pro', 'enterprise')`
- Renames any legacy tier values (`founder`→`builder`, `founder_pro`→`pro`, `starter`→`builder`) as safety net
- Adds `interval` column to `subscriptions` table (VARCHAR(10), nullable, default `'monthly'`)
- Adds `tier_override` column to `users` table (VARCHAR(20), nullable) with CHECK constraint
- Adds `tier_override_reason` column to `users` table (VARCHAR(255), nullable)
- Adds `tier_override_expires_at` column to `users` table (TIMESTAMPTZ, nullable)

```sql
-- upgrade
-- 1. Drop old CHECK constraints
ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_user_tier;
ALTER TABLE subscriptions DROP CONSTRAINT IF EXISTS chk_subscription_tier;
ALTER TABLE services DROP CONSTRAINT IF EXISTS chk_service_tier;

-- 2. Rename legacy tier values (safety net)
UPDATE users SET tier = 'builder' WHERE tier IN ('founder', 'starter');
UPDATE users SET tier = 'pro' WHERE tier = 'founder_pro';
UPDATE subscriptions SET tier = 'builder' WHERE tier IN ('founder', 'starter');
UPDATE subscriptions SET tier = 'pro' WHERE tier = 'founder_pro';
UPDATE services SET tier_required = 'builder' WHERE tier_required IN ('founder', 'starter');
UPDATE services SET tier_required = 'pro' WHERE tier_required = 'founder_pro';

-- 3. Create new CHECK constraints
ALTER TABLE users ADD CONSTRAINT chk_user_tier
    CHECK (tier IN ('free', 'builder', 'pro', 'enterprise'));
ALTER TABLE subscriptions ADD CONSTRAINT chk_subscription_tier
    CHECK (tier IN ('free', 'builder', 'pro', 'enterprise'));
ALTER TABLE services ADD CONSTRAINT chk_service_tier
    CHECK (tier_required IN ('free', 'builder', 'pro', 'enterprise'));

-- 4. Add new columns
ALTER TABLE subscriptions ADD COLUMN interval VARCHAR(10) DEFAULT 'monthly';
ALTER TABLE users ADD COLUMN tier_override VARCHAR(20);
ALTER TABLE users ADD COLUMN tier_override_reason VARCHAR(255);
ALTER TABLE users ADD COLUMN tier_override_expires_at TIMESTAMPTZ;

-- 5. CHECK constraint on tier_override
ALTER TABLE users ADD CONSTRAINT chk_user_tier_override
    CHECK (tier_override IS NULL OR tier_override IN ('free', 'builder', 'pro', 'enterprise'));

-- 6. Enforce reason when override is set
ALTER TABLE users ADD CONSTRAINT chk_tier_override_reason
    CHECK (tier_override IS NULL OR tier_override_reason IS NOT NULL);

-- downgrade reverses all
```

### 2. Models

**`src/mcpworks_api/models/subscription.py`** — `SubscriptionTier` enum:
- `FOUNDER` → `BUILDER = "builder"`
- `FOUNDER_PRO` → `PRO = "pro"`
- Update docstring prices ($49/$149/$499)
- `monthly_executions`: builder=2,500, pro=15,000, enterprise=100,000
- Add `interval` mapped column (String(10), nullable, default "monthly")

**`src/mcpworks_api/models/user.py`** — `UserTier` enum:
- `FOUNDER` → `BUILDER = "builder"`
- `FOUNDER_PRO` → `PRO = "pro"`
- Add `tier_override` mapped column (String(20), nullable)
- Add `tier_override_reason` mapped column (String(255), nullable)
- Add `tier_override_expires_at` mapped column (DateTime(timezone=True), nullable)
- Add `effective_tier` property: returns `tier_override` if set and not expired, else `tier`

### 3. Sandbox Backend — `src/mcpworks_api/backends/sandbox.py`

- `ExecutionTier`: `FOUNDER`→`BUILDER`, `FOUNDER_PRO`→`PRO`
- `TIER_CONFIG` keys: `ExecutionTier.BUILDER`, `ExecutionTier.PRO`
- **`DEFAULT_TIER = ExecutionTier.FREE`** (was FOUNDER — bug fix, prevents free users getting paid-tier resources)
- Pro timeout: 60s → **90s** (per PRICING.md)

### 4. Config — `src/mcpworks_api/config.py`

Replace 3 Stripe price fields with 6 (monthly+annual per tier):
```
stripe_price_builder_monthly / stripe_price_builder_annual
stripe_price_pro_monthly / stripe_price_pro_annual
stripe_price_enterprise_monthly / stripe_price_enterprise_annual
```

Replace execution limits:
```
tier_executions_builder: int = 2_500     (was founder: 1_000)
tier_executions_pro: int = 15_000        (was founder_pro: 10_000)
```

### 5. Stripe Service — `src/mcpworks_api/services/stripe.py`

- **`get_tier_price_map()`** → returns `dict[str, dict[str, str]]` with `{"monthly": "price_...", "annual": "price_..."}` per tier
- **`create_checkout_session()`**:
  - Add `interval` param (`monthly`|`annual`), select correct price from nested map
  - Add `automatic_tax={"enabled": True}`
  - Add `billing_address_collection="required"` (needed for Stripe Tax)
  - Add `allow_promotion_codes=True` (enables coupon/promo code entry at checkout)
  - Store `interval` in checkout session metadata
- **`TIER_EXECUTIONS`** — update to 2,500 / 15,000 / 100,000 (enterprise was -1, now 100,000 per ORDER-019)
- **New: `create_portal_session(stripe_customer_id, return_url)`** — creates Stripe Customer Portal session
- **New: `create_promo_checkout_session(user_id, tier, interval, promotion_code, success_url, cancel_url)`** — checkout with pre-applied promotion code (for shareable promo links)
- Tier validation: accept `builder`, `pro`, `enterprise`
- **Fix: `_handle_checkout_completed()`** — read `interval` from metadata and persist to subscription record
- **Fix: `_handle_subscription_updated()`** — reverse-map Stripe Price ID → tier name, update `subscription.tier` and `user.tier`. Critical for Customer Portal plan changes.
- **New: `_price_id_to_tier(price_id)`** — helper that maps a Stripe price ID back to tier name using config

### 6. Schemas — `src/mcpworks_api/schemas/subscription.py`

- `CreateSubscriptionRequest.tier` pattern → `^(builder|pro|enterprise)$`
- Add `interval: str = "monthly"` field with pattern `^(monthly|annual)$`
- `SubscriptionInfo` — add optional `interval` field

### 7. Schemas — `src/mcpworks_api/schemas/user.py`

- Update tier description/examples to `free, builder, pro, enterprise`

### 8. API Endpoints — `src/mcpworks_api/api/v1/subscriptions.py`

- Pass `body.interval` through to `create_checkout_session()`
- **New endpoint: `POST /v1/subscriptions/portal`** — returns `{"portal_url": "..."}`
- Update docstring tier references

### 9. API — `src/mcpworks_api/api/v1/account.py`

- Update tier examples in response field
- Use `user.effective_tier` (respects tier_override) for limit lookups

### 10. API — `src/mcpworks_api/api/v1/admin.py`

- **New endpoint: `PUT /v1/admin/users/{user_id}/tier`** — set tier_override + reason, audit logged
  - Body: `{"tier": "pro", "reason": "partner account"}`
  - Setting tier to `null` removes the override
  - Fires security event for audit trail
- **New endpoint: `DELETE /v1/admin/users/{user_id}/tier-override`** — remove tier override

### 11. Billing Middleware — `src/mcpworks_api/middleware/billing.py`

```python
TIER_LIMITS = {
    "free": 100,
    "builder": 2_500,       # was founder: 1,000
    "pro": 15_000,           # was founder_pro: 10,000
    "enterprise": 100_000,
}
```

Tier resolution: use `account.tier_override or account.tier` when looking up limits.

### 12. Static Assets

**`src/mcpworks_api/static/console.html`**:
- `.tier-founder` → `.tier-builder`
- `.tier-founder_pro` → `.tier-pro`

**`src/mcpworks_api/static/admin.html`**:
- `TIER_COLORS`: `founder`→`builder`, `founder_pro`→`pro`
- `TIER_LABELS`: `founder`→`Builder`, `founder_pro`→`Pro`

### 13. `.env.example`

Replace old Stripe/legacy vars:
```
# Old (remove)
STRIPE_PRICE_STARTER / STRIPE_PRICE_PRO / STRIPE_PRICE_ENTERPRISE
STRIPE_PRICE_FOUNDER / STRIPE_PRICE_FOUNDER_PRO
MATH_SERVICE_URL / AGENT_SERVICE_URL / AGENT_CALLBACK_SECRET

# New
STRIPE_PRICE_BUILDER_MONTHLY=price_...
STRIPE_PRICE_BUILDER_ANNUAL=price_...
STRIPE_PRICE_PRO_MONTHLY=price_...
STRIPE_PRICE_PRO_ANNUAL=price_...
STRIPE_PRICE_ENTERPRISE_MONTHLY=price_...
STRIPE_PRICE_ENTERPRISE_ANNUAL=price_...
```

### 14. Documentation

- **`src/mcpworks_api/static/legal/privacy-policy.md`** — update tier list to `free, builder, pro, enterprise`
- **`SPEC.md`** — update CHECK constraint definitions (lines 200, 297) to use `builder`/`pro`

### 15. Tests (8+ files)

Global `founder`→`builder`, `founder_pro`→`pro` in:
- `tests/unit/test_stripe_service.py` — tier names, limits, add interval tests, add promo code tests
- `tests/unit/test_middleware_billing.py` — tier limits, tier_override resolution
- `tests/integration/test_subscription_endpoints.py` — request bodies, validation, portal endpoint
- `tests/unit/test_sandbox_backend.py` — ExecutionTier refs, DEFAULT_TIER=FREE
- `tests/integration/test_sandbox_execution.py` — tier refs
- `tests/factories/user.py` — tier defaults, FounderProUserFactory → ProUserFactory
- `tests/factories/service.py` — tier refs
- `tests/unit/test_admin.py` or integration — new tier override endpoint tests

New test coverage:
- `test_checkout_session_allows_promotion_codes` — verify `allow_promotion_codes=True`
- `test_checkout_session_with_interval` — monthly vs annual price selection
- `test_portal_session_creation` — portal returns URL
- `test_admin_tier_override` — set/remove tier override
- `test_tier_override_takes_precedence` — billing middleware uses effective_tier
- `test_webhook_subscription_updated_syncs_tier` — portal plan change updates tier
- `test_default_tier_is_free` — sandbox DEFAULT_TIER is FREE

## Execution Order

1. Create Alembic migration (constraint fix + tier rename + new columns)
2. Update models (subscription.py, user.py)
3. Update sandbox backend (sandbox.py)
4. Update config (config.py)
5. Update Stripe service (stripe.py) — price map, checkout, portal, promo, webhook fixes
6. Update schemas (subscription.py, user.py)
7. Update API endpoints (subscriptions.py, account.py)
8. Update admin API (admin.py) — tier override endpoints
9. Update billing middleware (billing.py)
10. Update static assets (console.html, admin.html)
11. Update .env.example
12. Update documentation (privacy-policy.md, SPEC.md)
13. Update all tests
14. `ruff format src/ tests/ && ruff check src/ tests/`
15. `python -m pytest tests/unit/ -x -q`

## Coupon Policy (Stripe Dashboard)

All coupons created in Stripe Dashboard MUST follow these rules:
- **Always set `max_redemptions`** — no uncapped coupons. Broad promos: 50 max. Partner codes: 10-25 max.
- **100%-off coupons: 1 month maximum duration.** Never create unbounded 100%-off coupons.
- **Use non-guessable codes** for pre-applied promo links (e.g., `MCW-A7K9X2`, not `LAUNCH`).
- **Set `first_time_transaction=True`** on public-facing promos to prevent existing customers gaming codes.
- **Track redemptions weekly** against projected COGS impact.

## Deferred (next iteration)

- **Upgrade/downgrade endpoint** (`PUT /v1/subscriptions/current` calling `stripe.Subscription.modify()`). A0 uses "cancel and re-subscribe" or Customer Portal for plan changes.
- **Annual ↔ monthly interval switching** for existing subscribers.
- **Coupon management API** — coupons are created in Stripe Dashboard for A0.
- **Admin dashboard split** — separate `tier_breakdown_paying` vs `tier_breakdown_override` in stats.

## Verification

```bash
cd /home/user/dev/mcpworks.io/mcpworks-api

# No old tier names in source (exclude migration history + alembic + archive)
grep -rn '"founder"' src/ --include="*.py"
grep -rn "founder_pro" src/ --include="*.py"
grep -rn "FOUNDER" src/ --include="*.py"

# Formatter + linter
ruff format src/ tests/
ruff check src/ tests/

# Tests
python -m pytest tests/unit/ -x -q
python -m pytest tests/integration/ -x -q
```

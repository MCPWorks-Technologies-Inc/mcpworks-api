# API Contract Changes: Open-Source Self-Hosting

**Date**: 2026-03-22

## Modified Endpoints

### GET /v1/account/usage (when billing disabled)

**Current response** (billing enabled):
```json
{
  "billing_period_start": "2026-03-01T00:00:00Z",
  "billing_period_end": "2026-03-31T23:59:59Z",
  "executions_count": 1500,
  "executions_limit": 250000,
  "executions_remaining": 248500,
  "usage_percentage": 0.6,
  "tier": "pro"
}
```

**New response** (billing disabled):
```json
{
  "tier": "self-hosted",
  "billing_enabled": false,
  "executions_count": 1500,
  "executions_limit": -1,
  "executions_remaining": -1,
  "usage_percentage": 0.0
}
```

### POST /v1/auth/register (when registration disabled)

**New error response** (ALLOW_REGISTRATION=false):
```json
{
  "error": "registration_disabled",
  "message": "Public registration is disabled on this instance. Contact the administrator.",
  "error_code": "AUTH_REGISTRATION_DISABLED"
}
```
**HTTP Status**: 403 Forbidden

### GET /v1/subscriptions (when billing disabled)

**New error response**:
```json
{
  "error": "billing_not_configured",
  "message": "Billing is not configured on this instance.",
  "error_code": "BILLING_NOT_CONFIGURED"
}
```
**HTTP Status**: 404 Not Found

### GET /v1/health (unchanged contract, updated validation)

The `/v1/internal/verify-domain` endpoint used by Caddy for on-demand TLS will accept domain suffixes derived from `BASE_DOMAIN` instead of hardcoded `.mcpworks.io`.

## No Breaking Changes

All changes are additive or conditional:
- Existing endpoints continue to work identically when `BASE_DOMAIN=mcpworks.io` (default)
- New responses only appear when billing/registration are explicitly disabled
- No endpoint signatures, authentication, or request formats change

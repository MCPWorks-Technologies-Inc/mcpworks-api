# MCPWorks API - Known Problems

This file tracks significant issues discovered during API testing that need resolution.

---

## PROBLEM-001: Credit System Should Be Subscription-Based Execution Limits

**Severity:** Critical - Billing model mismatch
**Discovered:** 2026-02-11
**Status:** Open

### Summary

The API implements a **credit-based billing system** with hold/commit/release transactions. The business strategy specifies **flat-tiered subscription pricing** with monthly execution limits.

### What the API Currently Does

```
POST /v1/credits/hold          - Reserve credits before operation
POST /v1/credits/hold/{id}/commit  - Charge actual amount used
POST /v1/credits/hold/{id}/release - Return credits on failure
GET  /v1/credits               - Returns credit balance
```

Response from `/v1/credits`:
```json
{
  "available_credits": "500.00",
  "held_credits": "0.00",
  "lifetime_earned": "500.00",
  "lifetime_spent": "0.00"
}
```

New users receive 500 "free credits" and the system tracks credit transactions.

### What the Strategy Requires

From `mcpworks-internals/STRATEGY.md` line 726:
> ✅ **Flat-tiered subscription pricing** (Free/Starter/Pro/Enterprise, not credit-only)

From `mcpworks-internals/PRICING.md`:

| Tier | Monthly Price | Executions/mo | Behavior at Limit |
|------|---------------|---------------|-------------------|
| Free | $0 | 100 | Pause |
| Founder | $29 | 1,000 | Pause |
| Founder Pro | $59 | 10,000 | Pause |
| Founder Enterprise | $129 | Unlimited | N/A |

Key quote from PRICING.md:
> **Overages:** Workflows pause when limit reached (no surprise bills)

### Required Changes

1. **Remove credit endpoints:**
   - DELETE: `/v1/credits/hold`
   - DELETE: `/v1/credits/hold/{id}/commit`
   - DELETE: `/v1/credits/hold/{id}/release`

2. **Replace with execution tracking:**
   - Track `executions_used` and `executions_limit` per billing cycle
   - Reset counter monthly on subscription anniversary
   - Return 429 or pause behavior when limit reached

3. **Update `/v1/credits` or replace with `/v1/usage`:**
   ```json
   {
     "tier": "free",
     "billing_cycle_start": "2026-02-01T00:00:00Z",
     "billing_cycle_end": "2026-03-01T00:00:00Z",
     "executions_used": 42,
     "executions_limit": 100,
     "executions_remaining": 58
   }
   ```

4. **Update user profile response:**
   - Remove `available_credits` and `held_credits`
   - Add `executions_used`, `executions_limit`

5. **Update registration:**
   - Remove "500 free credits" grant
   - Assign `tier: "free"` with 100 executions/month limit

### References

- `mcpworks-internals/STRATEGY.md` - Lines 726, 950 (credit model removed)
- `mcpworks-internals/PRICING.md` - Full tier/limit definitions
- `mcpworks-internals/incoming/mcpworks-api-testing-manual.md` - Documents current (incorrect) implementation

---

## PROBLEM-002: List Services Endpoint Returns INTERNAL_ERROR

**Severity:** High - Endpoint broken
**Discovered:** 2026-02-11
**Status:** Open

### Summary

The `GET /v1/namespaces/{namespace}/services` endpoint returns an internal error instead of the service list.

### Steps to Reproduce

```bash
curl -s "https://api.mcpworks.io/v1/namespaces/{namespace}/services" \
  -H "Authorization: Bearer {token}"
```

### Actual Response

```json
{
  "error": "INTERNAL_ERROR",
  "message": "An unexpected error occurred",
  "details": {}
}
```

### Expected Response

```json
{
  "services": [...],
  "total": 1
}
```

### Notes

- Creating services works (returns 201 or 409 if exists)
- The endpoint fails even when services exist in the namespace
- List functions endpoint works correctly

---

## PROBLEM-003: Create Service Returns Wrong Error on Success

**Severity:** Medium - Misleading response
**Discovered:** 2026-02-11
**Status:** Open

### Summary

`POST /v1/namespaces/{namespace}/services` returns `INTERNAL_ERROR` but actually creates the service successfully.

### Steps to Reproduce

```bash
curl -s -X POST "https://api.mcpworks.io/v1/namespaces/{namespace}/services" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-service", "description": "Test"}'
```

### Actual Behavior

1. First call returns: `{"error": "INTERNAL_ERROR", ...}`
2. Second call returns: `{"error": "HTTP_ERROR", "message": "Service 'my-service' already exists..."}`

This proves the service was created despite the error response.

### Expected Behavior

First call should return 201 with the created service object.

---

## PROBLEM-004: API Key Prefix Mismatch in Documentation

**Severity:** Low - Documentation issue
**Discovered:** 2026-02-11
**Status:** Open

### Summary

The testing manual documents API key prefix as `mcpw_` but the API generates keys with prefix `mcp_`.

### Actual API Response

```json
{
  "key": "mcp_b7c785bcbb2e094bcae44d7f5201e1d8b4969412917460daa39b0cbcb3b74990",
  "key_prefix": "mcp_b7c785bc"
}
```

### Documentation Says

```json
{
  "key": "mcpw_xxxxxxxxxxxxxxxxxxxxxx",
  "key_prefix": "mcpw_xxxx"
}
```

### Resolution

Either update the API to use `mcpw_` prefix (preferred - more distinctive) or update documentation to match `mcp_`.

---

## Test Summary (2026-02-11)

### Passing Endpoints

| Endpoint | Method | Status |
|----------|--------|--------|
| `/v1/health` | GET | ✅ Pass |
| `/v1/health/ready` | GET | ✅ Pass |
| `/v1/auth/register` | POST | ✅ Pass |
| `/v1/auth/login` | POST | ✅ Pass |
| `/v1/auth/refresh` | POST | ✅ Pass |
| `/v1/auth/token` | POST | ✅ Pass (API key exchange) |
| `/v1/users/me` | GET | ✅ Pass |
| `/v1/users/me/api-keys` | POST | ✅ Pass |
| `/v1/namespaces` | POST | ✅ Pass |
| `/v1/namespaces` | GET | ✅ Pass |
| `/v1/namespaces/{ns}` | GET | ✅ Pass |
| `/v1/namespaces/{ns}` | DELETE | ✅ Pass |
| `/v1/namespaces/{ns}/services/{svc}/functions` | POST | ✅ Pass |
| `/v1/namespaces/{ns}/services/{svc}/functions` | GET | ✅ Pass |
| `/v1/namespaces/{ns}/services/{svc}/functions/{fn}` | GET | ✅ Pass |

### Failing Endpoints

| Endpoint | Method | Issue |
|----------|--------|-------|
| `/v1/namespaces/{ns}/services` | GET | PROBLEM-002 |
| `/v1/namespaces/{ns}/services` | POST | PROBLEM-003 |
| `/v1/credits/*` | ALL | PROBLEM-001 (wrong model) |

### Error Handling

| Scenario | Expected | Actual | Status |
|----------|----------|--------|--------|
| Missing auth | 401 | 401 MISSING_TOKEN | ✅ |
| Invalid token | 401 | 401 INVALID_TOKEN | ✅ |
| Wrong password | 401 | 401 INVALID_CREDENTIALS | ✅ |
| Duplicate email | 409 | 409 EMAIL_EXISTS | ✅ |
| Not found | 404 | 404 HTTP_ERROR | ✅ |

---

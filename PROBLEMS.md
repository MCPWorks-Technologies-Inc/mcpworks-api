# MCPWorks API - Known Problems

This file tracks significant issues discovered during API testing that need resolution.

---

## PROBLEM-001: Usage Tracking Endpoint Not Implemented

**Severity:** High - Core feature missing
**Discovered:** 2026-02-11
**Status:** Open

### Summary

The credit system has been correctly removed, but the replacement `/v1/account/usage` endpoint is not yet implemented.

### What Works

- `/v1/credits` returns 404 (correctly removed)
- User profile no longer includes `available_credits` or `held_credits` fields
- User profile correctly shows `tier: "free"`

### What's Missing

```bash
curl https://api.mcpworks.io/v1/account/usage \
  -H "Authorization: Bearer {token}"
```

**Actual Response:**
```json
{"detail":"Not Found"}
```
HTTP Status: 404

**Expected Response (per testing manual):**
```json
{
  "executions_count": 42,
  "executions_limit": 100,
  "executions_remaining": 58,
  "billing_period_start": "2026-02-01T00:00:00Z",
  "billing_period_end": "2026-03-01T00:00:00Z"
}
```

### Required Implementation

1. Create `GET /v1/account/usage` endpoint
2. Track executions via Redis-based BillingMiddleware
3. Return execution counts and limits based on user tier:
   - Free: 100/month
   - Founder: 1,000/month
   - Founder Pro: 10,000/month
   - Enterprise: Unlimited

### References

- `mcpworks-internals/PRICING.md` - Tier limits
- `mcpworks-internals/incoming/mcpworks-api-testing-manual.md` - Expected response format

---

## Resolved Issues

### ~~PROBLEM-002: List Services Endpoint Returns INTERNAL_ERROR~~

**Status:** RESOLVED (2026-02-11)

The endpoint now works correctly:
```json
{"services":[...],"namespace":"test-ns-xxx"}
```
HTTP Status: 200

---

### ~~PROBLEM-003: Create Service Returns Wrong Error on Success~~

**Status:** RESOLVED (2026-02-11)

The endpoint now returns proper response:
```json
{"id":"...","name":"utils","description":"...","namespace_id":"...","function_count":0,"created_at":"..."}
```
HTTP Status: 201

---

### ~~PROBLEM-004: API Key Prefix Mismatch~~

**Status:** RESOLVED (2026-02-11)

API now correctly uses `mcpw_` prefix:
```json
{"api_key":{"key_prefix":"mcpw_0d57f8b",...},"raw_key":"mcpw_..."}
```

---

## Test Summary (2026-02-11, Run 2)

### Passing Endpoints

| Endpoint | Method | Status |
|----------|--------|--------|
| `/v1/health` | GET | Pass |
| `/v1/health/ready` | GET | Pass |
| `/v1/auth/register` | POST | Pass |
| `/v1/auth/login` | POST | Pass |
| `/v1/auth/refresh` | POST | Pass |
| `/v1/auth/token` | POST | Pass (API key exchange) |
| `/v1/auth/api-keys` | POST | Pass (new endpoint) |
| `/v1/users/me` | GET | Pass (no credits fields) |
| `/v1/users/me/api-keys` | POST | Pass (legacy, still works) |
| `/v1/namespaces` | POST | Pass |
| `/v1/namespaces` | GET | Pass |
| `/v1/namespaces/{ns}` | GET | Pass |
| `/v1/namespaces/{ns}` | DELETE | Pass |
| `/v1/namespaces/{ns}/services` | POST | Pass (FIXED) |
| `/v1/namespaces/{ns}/services` | GET | Pass (FIXED) |
| `/v1/namespaces/{ns}/services/{svc}/functions` | POST | Pass |
| `/v1/namespaces/{ns}/services/{svc}/functions` | GET | Pass |
| `/v1/namespaces/{ns}/services/{svc}/functions/{fn}` | GET | Pass |
| `/v1/subscriptions/current` | GET | Pass (404 for free tier = expected) |

### Missing/Not Implemented

| Endpoint | Method | Issue |
|----------|--------|-------|
| `/v1/account/usage` | GET | PROBLEM-001 - Not implemented |

### Removed (Correctly)

| Endpoint | Method | Status |
|----------|--------|--------|
| `/v1/credits` | GET | 404 (removed) |
| `/v1/credits/hold` | POST | 404 (removed) |

### Error Handling

| Scenario | Expected | Actual | Status |
|----------|----------|--------|--------|
| Missing auth | 401 | 401 MISSING_TOKEN | Pass |
| Invalid token | 401 | 401 INVALID_TOKEN | Pass |
| Wrong password | 401 | 401 INVALID_CREDENTIALS | Pass |
| Duplicate email | 409 | 409 EMAIL_EXISTS | Pass |
| Not found | 404 | 404 NOT_FOUND | Pass |

---

## Notes

- API key prefix is now `mcpw_` (correct)
- New API key endpoint at `/v1/auth/api-keys` with improved response format
- Legacy endpoint `/v1/users/me/api-keys` still works for backward compatibility
- Subscription endpoint returns 404 "No subscription found" for free tier users (expected)

---

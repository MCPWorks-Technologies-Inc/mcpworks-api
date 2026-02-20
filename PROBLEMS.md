# MCPWorks API - Known Problems

This file tracks significant issues discovered during API testing that need resolution.

---

## Open Issues

### ~~PROBLEM-006: Code-Mode Execution Not Exposed via MCP Run Server~~

**Status:** RESOLVED (2026-02-20)

Code-mode was fully implemented but hidden behind a `?mode=code` query parameter, while the default was `"tools"`. Flipped the default: `{ns}.run.mcpworks.io/mcp` now serves code-mode by default (single `execute` tool). Per-function tools mode available via `?mode=tools`.

Remaining sub-issue: functions created mid-session aren't discoverable until MCP client reconnects (client-side `tools/list` snapshot limitation). Code-mode sidesteps this since the AI writes code that imports from the `functions` package — no tool discovery needed.

---

---

## Resolved Issues

### ~~PROBLEM-005: MCP Run Server Tools Not Discoverable / Returning Null~~

**Status:** RESOLVED (2026-02-12)

Two root causes found and fixed:

1. **`str(EndpointType.CREATE)` != `"create"` in Python 3.11+** — The `transport.py` endpoint routing used `str(endpoint_type) == "create"` which always evaluated to `False` (returns `"EndpointType.CREATE"`). Both create and run endpoints fell through to RunMCPHandler. Fixed with direct enum comparison: `endpoint_type == EndpointType.CREATE`.

2. **Sandbox wrapper never called `main(input_data)`** — The code_sandbox execution harness only checked for explicit `result` or `output` variables after `exec()`. Functions defining `main(input_data)` (the platform convention) returned `None`. Fixed by adding a `callable(exec_globals.get('main'))` check.

Verified end-to-end: `tools.hello` returns `{"greeting": "Hello, Simon! Welcome to MCPWorks."}` via both curl and Claude Code MCP client.

---

### ~~PROBLEM-001: Usage Tracking Endpoint Not Implemented~~

**Status:** RESOLVED (2026-02-11)

The `/v1/account/usage` endpoint is now implemented and returns:
```json
{
  "executions_count": 0,
  "executions_limit": 100,
  "executions_remaining": 100,
  "billing_period_start": "2026-02-01T00:00:00Z",
  "billing_period_end": "2026-03-01T00:00:00Z",
  "tier": "free"
}
```
HTTP Status: 200

---

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

## Test Summary (2026-02-11, Run 3 - All Issues Resolved)

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
| `/v1/account/usage` | GET | Pass (FIXED - PROBLEM-001) |

### All Endpoints Implemented

All planned endpoints are now implemented and passing.

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

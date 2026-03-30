# mcpworks API Contract

**Version:** 1.0.0
**Created:** 2025-11-02
**Status:** Draft
**Purpose:** Defines the REST API contract for `mcpworks-api` (backend service)

---

## 1. Overview

This document defines the HTTP/JSON API contract for `mcpworks-api`, the open-source (BSL 1.1) backend service powering the MCPWorks platform. AI assistants connect directly via namespace HTTPS endpoints.

### 1.1 Base URL

- **Production:** `https://api.mcpworks.io/v1`
- **Staging:** `https://staging-api.mcpworks.io/v1`
- **Local Development:** `http://localhost:8000/v1`

### 1.2 Authentication

All API requests (except `/auth/register`, `/auth/login`, and `/auth/token`) require authentication via Bearer token:

```
Authorization: Bearer {api_key_or_access_token}
```

**API Key Format:** `sk_{env}_{keyID}_{random}`
- `sk_live_k1_abc123...` - Production key #1
- `sk_test_k1_xyz789...` - Test/sandbox key
- Key ID (`k1`, `k2`, etc.) enables multiple active keys for rotation

**Access Token Format:** JWT signed with ES256 (returned from `/auth/token`)

### 1.3 Environment Variable Passthrough

Functions that call external APIs can receive secrets via the `X-MCPWorks-Env` header on **run** endpoint requests (`/mcp/run/{namespace}`). Values are never stored, logged, or persisted — they exist only for the duration of execution.

```
X-MCPWorks-Env: base64:{base64-encoded JSON object}
```

**Encoding:** Base64-encode a JSON object of key-value pairs, prefixed with `base64:`.

```bash
# Encode
echo -n '{"OPENAI_API_KEY":"sk-xxx","STRIPE_KEY":"sk_live_xxx"}' | base64

# Result header value
X-MCPWorks-Env: base64:eyJPUEVOQUlfQVBJX0tFWSI6InNrLXh4eCIsIlNUUklQRV9LRVkiOiJza19saXZlX3h4eCJ9
```

**Limits:**
- Maximum 64 variables per request
- Maximum 32 KB total header size
- Variable names must be uppercase alphanumeric + underscore (`^[A-Z][A-Z0-9_]*$`)
- Blocked names: `PATH`, `HOME`, `LD_*`, `PYTHON*`, `NSJAIL*`, `MCPWORKS_*`, `SSL_*`

**Function declarations:** Functions declare `required_env` and `optional_env` when created. Only declared variables are passed to each function (least-privilege). Missing required variables return an error before execution.

**Diagnostics:** The `_env_status` tool (available on all run endpoints) reports which variables are configured vs missing across all namespace functions.

### 1.4 Request/Response Format

- **Content-Type:** `application/json`
- **Character Encoding:** UTF-8
- **Date Format:** ISO 8601 (`2025-11-02T20:00:00Z`)

---

## 2. Authentication Endpoints

### 2.1 Register Account

```
POST /v1/auth/register
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "secure_password",
  "name": "John Doe"
}
```

**Response:** `201 Created`
```json
{
  "account_id": "acc_1234567890abcdef",
  "email": "user@example.com",
  "api_key": "msp_live_a1b2c3d4e5f6..."
}
```

### 2.2 Login

```
POST /v1/auth/login
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "secure_password"
}
```

**Response:** `200 OK`
```json
{
  "api_key": "sk_live_k1_a1b2c3d4e5f6...",
  "account_id": "acc_1234567890abcdef"
}
```

### 2.3 Token Exchange (Gateway Authentication)

Exchange an API key for short-lived access and refresh tokens. This is the primary authentication method for AI assistants connecting via namespace endpoints.

```
POST /v1/auth/token
```

**Request Body:**
```json
{
  "api_key": "sk_live_k1_abc123...",
  "token_config": {
    "access_token_ttl": 3600,     // Optional: seconds (default 3600, range 900-14400)
    "refresh_token_ttl": 604800   // Optional: seconds (default 604800, range 86400-2592000)
  },
  "client_info": {
    "gateway_version": "1.0.0",   // Optional: for analytics
    "platform": "linux",          // Optional
    "hostname": "dev-machine"     // Optional
  }
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Im1jcHdvcmtzLTIwMjUtMDEifQ...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "rt_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "refresh_expires_in": 604800,
  "user": {
    "user_id": "usr_abc123def456",
    "email": "user@example.com",
    "tier": "pro",
    "executions_remaining": 248500
  },
  "key_info": {
    "key_id": "k1",
    "created_at": "2025-10-01T00:00:00Z",
    "expires_at": "2025-12-30T00:00:00Z",
    "days_until_expiry": 33,
    "rotation_recommended": false,
    "status": "active"
  }
}
```

**Error Responses:**

- `401 Unauthorized` - Invalid or expired API key
- `410 Gone` - API key has been rotated (new key available)

```json
{
  "error": "key_rotated",
  "message": "This API key has been rotated. Please use the new key.",
  "error_code": "AUTH_KEY_ROTATED",
  "old_key_hint": "sk_live_k1_***xyz",
  "new_key_hint": "sk_live_k2_***abc"
}
```

### 2.4 Token Refresh

Refresh an access token using a refresh token. Returns new access AND refresh tokens (refresh tokens are single-use).

```
POST /v1/auth/refresh
```

**Request Body:**
```json
{
  "refresh_token": "rt_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Im1jcHdvcmtzLTIwMjUtMDEifQ...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "rt_newtoken123456789...",
  "refresh_expires_in": 604800
}
```

**Error Responses:**

- `401 Unauthorized` - Refresh token expired, revoked, or already used

### 2.5 List API Keys

List all API keys for the authenticated account.

```
GET /v1/auth/keys
Authorization: Bearer {access_token}
```

**Response:** `200 OK`
```json
{
  "keys": [
    {
      "key_id": "k1",
      "key_hint": "sk_live_k1_***xyz",
      "status": "active",
      "created_at": "2025-10-01T00:00:00Z",
      "last_used_at": "2025-11-27T10:30:00Z",
      "expires_at": null
    },
    {
      "key_id": "k2",
      "key_hint": "sk_live_k2_***abc",
      "status": "rotating",
      "created_at": "2025-11-27T12:00:00Z",
      "last_used_at": null,
      "revokes_at": "2025-12-04T12:00:00Z"
    }
  ],
  "max_keys": 5
}
```

### 2.6 Rotate API Key

Generate a new API key with a grace period for the old key. **Dashboard-triggered only** (not callable from gateway CLI).

```
POST /v1/auth/keys/rotate
Authorization: Bearer {access_token}
```

**Request Body:**
```json
{
  "grace_period_days": 7  // Optional: default 7, range 1-30
}
```

**Response:** `200 OK`
```json
{
  "new_key": {
    "api_key": "sk_live_k2_newrandom...",
    "key_id": "k2",
    "created_at": "2025-11-27T12:00:00Z"
  },
  "old_key": {
    "key_id": "k1",
    "status": "rotating",
    "revokes_at": "2025-12-04T12:00:00Z"
  },
  "grace_period_ends_at": "2025-12-04T12:00:00Z"
}
```

### 2.7 Revoke API Key

Immediately revoke a specific API key. Use with caution.

```
DELETE /v1/auth/keys/{key_id}
Authorization: Bearer {access_token}
```

**Response:** `200 OK`
```json
{
  "key_id": "k1",
  "status": "revoked",
  "revoked_at": "2025-11-27T12:00:00Z"
}
```

**Error Responses:**

- `400 Bad Request` - Cannot revoke the only active key
- `404 Not Found` - Key ID not found

---

## 3. Account Endpoints

### 3.1 Get Account Details

```
GET /v1/account
```

**Response:** `200 OK`
```json
{
  "account_id": "acc_1234567890abcdef",
  "email": "user@example.com",
  "name": "John Doe",
  "created_at": "2025-10-15T14:30:00Z"
}
```

### 3.2 Get Usage

```
GET /v1/account/usage
```

**Response:** `200 OK`
```json
{
  "billing_period_start": "2025-11-01T00:00:00Z",
  "billing_period_end": "2025-11-30T23:59:59Z",
  "executions_count": 1500,
  "executions_limit": 250000,
  "executions_remaining": 248500,
  "usage_percentage": 0.6,
  "tier": "pro"
}
```

---

## 4. Service Endpoints (Hosting)

### 4.1 Provision Service

```
POST /v1/services
```

**Request Body:**
```json
{
  "type": "web_hosting",
  "size": "small",
  "region": "tor1",
  "configuration": {
    "memory_mb": 1024,
    "vcpus": 1,
    "disk_gb": 25
  }
}
```

**Response:** `202 Accepted`
```json
{
  "service_id": "svc_abc123",
  "status": "provisioning",
  "type": "web_hosting",
  "region": "tor1",
  "estimated_ready_at": "2025-11-02T20:02:00Z",
  "stream_url": "https://api.mcpworks.io/v1/services/svc_abc123/logs"
}
```

### 4.2 Get Service Status

```
GET /v1/services/{service_id}
```

**Response:** `200 OK`
```json
{
  "service_id": "svc_abc123",
  "status": "running",
  "type": "web_hosting",
  "region": "tor1",
  "created_at": "2025-11-02T20:00:00Z",
  "ready_at": "2025-11-02T20:02:30Z",
  "endpoints": {
    "public_ip": "142.93.123.45",
    "ssh": "ssh://root@142.93.123.45"
  }
}
```

### 4.3 Scale Service

```
PATCH /v1/services/{service_id}
```

**Request Body:**
```json
{
  "configuration": {
    "memory_mb": 2048,
    "vcpus": 2
  }
}
```

**Response:** `202 Accepted`
```json
{
  "service_id": "svc_abc123",
  "status": "scaling",
  "new_burn_rate_per_hour": 2.4,
  "stream_url": "https://api.mcpworks.io/v1/services/svc_abc123/logs"
}
```

### 4.4 Deprovision Service

```
DELETE /v1/services/{service_id}
```

**Response:** `202 Accepted`
```json
{
  "service_id": "svc_abc123",
  "status": "deprovisioning",
  "message": "Service will be terminated"
}
```

---

## 5. Deployment Endpoints

### 5.1 Deploy Application

```
POST /v1/deployments
```

**Request Body:**
```json
{
  "service_id": "svc_abc123",
  "repository_url": "https://github.com/user/app.git",
  "branch": "main",
  "build_command": "npm install && npm run build",
  "start_command": "npm start",
  "env_vars": {
    "NODE_ENV": "production",
    "PORT": "3000"
  }
}
```

**Response:** `202 Accepted`
```json
{
  "deployment_id": "dep_xyz789",
  "service_id": "svc_abc123",
  "status": "deploying",
  "created_at": "2025-11-02T20:05:00Z",
  "stream_url": "https://api.mcpworks.io/v1/deployments/dep_xyz789/logs"
}
```

### 5.2 Get Deployment Status

```
GET /v1/deployments/{deployment_id}
```

**Response:** `200 OK`
```json
{
  "deployment_id": "dep_xyz789",
  "service_id": "svc_abc123",
  "status": "deployed",
  "started_at": "2025-11-02T20:05:00Z",
  "completed_at": "2025-11-02T20:08:15Z",
  "url": "https://app.example.com"
}
```

### 5.3 Stream Deployment Logs (SSE)

```
GET /v1/deployments/{deployment_id}/logs
```

**Response:** `200 OK` with `Content-Type: text/event-stream`

```
event: log
data: {"timestamp": "2025-11-02T20:05:01Z", "message": "Cloning repository..."}

event: log
data: {"timestamp": "2025-11-02T20:05:05Z", "message": "Installing dependencies..."}

event: log
data: {"timestamp": "2025-11-02T20:07:30Z", "message": "Building application..."}

event: status
data: {"status": "deployed", "url": "https://app.example.com"}

event: done
data: {"deployment_id": "dep_xyz789", "status": "deployed"}
```

### 5.4 Rollback Deployment

```
POST /v1/deployments/{deployment_id}/rollback
```

**Response:** `202 Accepted`
```json
{
  "deployment_id": "dep_new123",
  "previous_deployment_id": "dep_xyz789",
  "status": "deploying",
  "stream_url": "https://api.mcpworks.io/v1/deployments/dep_new123/logs"
}
```

---

## 6. Domain Endpoints

### 6.1 Register Domain

```
POST /v1/domains
```

**Request Body:**
```json
{
  "domain_name": "example.com",
  "privacy_protection": true,
  "auto_renew": true
}
```

**Response:** `201 Created`
```json
{
  "domain_id": "dom_abc123",
  "domain_name": "example.com",
  "status": "registering",
  "expires_at": "2026-11-02T20:00:00Z",
  "nameservers": [
    "ns1.mcpworks.io",
    "ns2.mcpworks.io"
  ]
}
```

### 6.2 Configure DNS

```
POST /v1/domains/{domain_id}/dns
```

**Request Body:**
```json
{
  "records": [
    {
      "type": "A",
      "name": "@",
      "value": "142.93.123.45",
      "ttl": 3600
    },
    {
      "type": "CNAME",
      "name": "www",
      "value": "example.com",
      "ttl": 3600
    }
  ]
}
```

**Response:** `200 OK`
```json
{
  "domain_id": "dom_abc123",
  "records_updated": 2,
  "propagation_status": "pending"
}
```

### 6.3 Check Domain Availability

```
GET /v1/domains/check?domain=example.com
```

**Response:** `200 OK`
```json
{
  "domain": "example.com",
  "available": false,
  "price_usd": 15.00,
  "suggestions": ["example-app.com", "example-io.com"]
}
```

---

## 7. SSL Endpoints

### 7.1 Provision SSL Certificate

```
POST /v1/ssl
```

**Request Body:**
```json
{
  "domain_id": "dom_abc123",
  "domain_name": "example.com",
  "type": "letsencrypt"
}
```

**Response:** `201 Created`
```json
{
  "certificate_id": "cert_xyz789",
  "domain_name": "example.com",
  "status": "issuing",
  "type": "letsencrypt",
  "expires_at": "2026-02-02T20:00:00Z"
}
```

### 7.2 Renew Certificate

```
POST /v1/ssl/{cert_id}/renew
```

**Response:** `202 Accepted`
```json
{
  "certificate_id": "cert_new456",
  "previous_cert_id": "cert_xyz789",
  "status": "issuing",
  "expires_at": "2026-05-02T20:00:00Z"
}
```

---

## 8. Integration Endpoints

### 8.1 Setup Stripe

```
POST /v1/integrations/stripe
```

**Request Body:**
```json
{
  "account_name": "My Store",
  "country": "CA",
  "currency": "CAD"
}
```

**Response:** `201 Created`
```json
{
  "integration_id": "int_stripe_abc123",
  "provider": "stripe",
  "status": "active",
  "account_id": "acct_1234567890",
  "publishable_key": "pk_test_..."
}
```

### 8.2 Setup Shopify

```
POST /v1/integrations/shopify
```

**Request Body:**
```json
{
  "store_name": "my-store",
  "email": "admin@example.com"
}
```

**Response:** `201 Created`
```json
{
  "integration_id": "int_shopify_xyz789",
  "provider": "shopify",
  "status": "active",
  "store_url": "https://my-store.myshopify.com",
  "admin_url": "https://my-store.myshopify.com/admin"
}
```

---

## 9. Error Responses

All errors follow this format:

```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "details": {
    "field": "Additional context"
  },
  "request_id": "req_abc123"
}
```

### Common Error Codes

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | `invalid_request` | Request body validation failed |
| 401 | `unauthorized` | Missing or invalid API key/access token |
| 401 | `token_expired` | Access token has expired (use refresh) |
| 401 | `refresh_token_invalid` | Refresh token expired, revoked, or already used |
| 402 | `usage_limit_exceeded` | Execution limit reached for billing period |
| 404 | `not_found` | Resource not found |
| 409 | `conflict` | Resource already exists or in invalid state |
| 410 | `key_rotated` | API key has been rotated, use new key |
| 429 | `rate_limit_exceeded` | Too many requests |
| 500 | `internal_error` | Server error |
| 503 | `service_unavailable` | Temporary outage |

**Example Error Response:**
```json
{
  "error": "usage_limit_exceeded",
  "message": "Execution limit reached for current billing period",
  "details": {
    "executions_count": 250000,
    "executions_limit": 250000,
    "resets_at": "2025-12-01T00:00:00Z"
  },
  "request_id": "req_xyz789"
}
```

---

## 10. Rate Limiting

**Limits:**
- **Authenticated:** 100 requests per minute per API key
- **Unauthenticated:** 10 requests per minute per IP

**Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1698960000
```

**429 Response:**
```json
{
  "error": "rate_limit_exceeded",
  "message": "Rate limit exceeded. Retry after 42 seconds.",
  "retry_after": 42
}
```

---

## 11. Pagination

List endpoints support pagination:

```
GET /v1/services?page=1&per_page=20
```

**Response:**
```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total_pages": 5,
    "total_count": 93
  }
}
```

---

## 12. Versioning

**Current Version:** `v1`

**Version in URL:** `/v1/services`

**Breaking Changes:** New major version (`/v2/...`)
**Non-Breaking Changes:** Added to existing version

---

## 13. Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-02 | Initial API contract specification |

---

**This contract is the authoritative reference for the mcpworks-api REST endpoints. Any breaking changes require semantic versioning and deprecation notices.**

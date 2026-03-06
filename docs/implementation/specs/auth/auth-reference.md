# mcpworks API Authentication Reference

**Source:** Consolidated from mcpworks-auth (now deprecated in favor of baked-in auth)
**Version:** 1.0.0
**Date:** 2025-12-16

## Overview

This document captures authentication specifications originally designed for a separate `mcpworks-auth` service, now baked directly into `mcpworks-api` for MVP simplicity.

**MVP Scope (A0):**
- API key management (issue, rotate, revoke)
- API key → JWT token exchange
- JWT validation middleware
- Basic rate limiting

**Deferred (A1+):**
- Full OAuth 2.1 flows (authorization_code, PKCE)
- Dynamic client registration (RFC 7591)
- Federated identity (Google, GitHub)
- MFA support

---

## Token Specification

### JWT Format (ES256)

Access tokens are JSON Web Tokens signed with ES256 (ECDSA P-256).

**Header:**
```json
{
  "alg": "ES256",
  "typ": "JWT",
  "kid": "mcpworks-api-2025-001"
}
```

**Payload:**
```json
{
  "iss": "https://api.mcpworks.io",
  "sub": "usr_01HZXK4M8QWERTY12345ABC",
  "aud": ["https://api.mcpworks.io"],
  "exp": 1732716000,
  "iat": 1732712400,
  "jti": "tok_01HZXK5N9RTYUIO67890DEF",
  "scope": "math:read math:write usage:read",
  "mcpworks": {
    "tier": "pro",
    "user_id": "usr_01HZXK4M8QWERTY12345ABC",
    "executions_limit": 250000
  }
}
```

### Standard Claims

| Claim | Description |
|-------|-------------|
| `iss` | Issuer - `https://api.mcpworks.io` |
| `sub` | Subject - user ID (`usr_*`) |
| `aud` | Audience - Resource Server URLs |
| `exp` | Expiration (Unix timestamp) |
| `iat` | Issued at (Unix timestamp) |
| `jti` | JWT ID - unique token identifier |
| `scope` | Space-separated granted scopes |

### mcpworks Claims

| Claim | Description |
|-------|-------------|
| `tier` | Subscription: `free`, `pro`, `enterprise` |
| `user_id` | User identifier |
| `executions_limit` | Monthly execution limit for tier |

### Token Lifetimes

| Token Type | Lifetime |
|------------|----------|
| Access Token | 1 hour (3600s) |
| Refresh Token | 7 days (604800s) |
| API Key | Until revoked |

---

## Scopes

### Service Scopes

| Scope | Description |
|-------|-------------|
| `math:read` | Read-only access to Math MCP |
| `math:write` | Full access to Math MCP |
| `text:read` | Read-only access to Text MCP |
| `text:write` | Full access to Text MCP |
| `usage:read` | View usage and billing period |
| `billing:write` | Manage subscription, billing |

### Scope Hierarchy

Write scopes include read:
- `math:write` implies `math:read`
- `billing:write` implies `usage:read`

---

## API Key Format

**Format:** `sk_{env}_{keyID}_{random}`

**Examples:**
- Production: `sk_live_k1_abc123def456ghi789jkl012mno345pqr678`
- Test: `sk_test_k1_xyz789abc123def456ghi789jkl012mno345`

**Components:**
- `sk_` - Static prefix (secret key)
- `{env}` - `live` or `test`
- `{keyID}` - Key identifier for rotation tracking
- `{random}` - 32 bytes of cryptographic randomness (Base62 encoded)

---

## Database Models (MVP)

### Users Table

```sql
CREATE TABLE users (
    id VARCHAR(26) PRIMARY KEY,           -- usr_* ULID
    email VARCHAR(255) UNIQUE NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    password_hash VARCHAR(255),           -- Argon2id
    name VARCHAR(255),
    tier VARCHAR(20) DEFAULT 'free',      -- free, pro, enterprise
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### API Keys Table

```sql
CREATE TABLE api_keys (
    id VARCHAR(26) PRIMARY KEY,           -- key_* ULID
    user_id VARCHAR(26) REFERENCES users(id) NOT NULL,
    key_hash VARCHAR(64) NOT NULL,        -- SHA-256 of full key
    key_prefix VARCHAR(20) NOT NULL,      -- sk_live_k1_ (for display)
    name VARCHAR(255),                    -- User-assigned name
    scopes VARCHAR(1024),                 -- Space-separated scopes
    last_used_at TIMESTAMP,
    expires_at TIMESTAMP,                 -- NULL = never expires
    revoked_at TIMESTAMP,                 -- NULL = active
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_api_keys_user ON api_keys(user_id);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);
```

### Refresh Tokens Table

```sql
CREATE TABLE refresh_tokens (
    token_hash VARCHAR(64) PRIMARY KEY,   -- SHA-256 of token
    user_id VARCHAR(26) REFERENCES users(id) NOT NULL,
    api_key_id VARCHAR(26) REFERENCES api_keys(id),
    scope VARCHAR(1024),
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_expires ON refresh_tokens(expires_at);
```

### Signing Keys Table

```sql
CREATE TABLE signing_keys (
    kid VARCHAR(50) PRIMARY KEY,          -- mcpworks-api-2025-001
    private_key_encrypted BYTEA NOT NULL, -- AES-256-GCM encrypted
    public_key TEXT NOT NULL,             -- PEM-encoded
    algorithm VARCHAR(10) NOT NULL,       -- ES256
    active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    activated_at TIMESTAMP,
    deactivated_at TIMESTAMP
);

-- Only one active key at a time
CREATE UNIQUE INDEX idx_signing_keys_active ON signing_keys(active) WHERE active = TRUE;
```

---

## API Endpoints (MVP)

### POST /v1/auth/register

Create a new user account and first API key.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "name": "Jane Developer"
}
```

**Response:**
```json
{
  "user": {
    "id": "usr_01HZXK4M8QWERTY12345ABC",
    "email": "user@example.com",
    "name": "Jane Developer",
    "tier": "free"
  },
  "api_key": {
    "id": "key_01HZXK5N9RTYUIO67890DEF",
    "key": "sk_live_k1_abc123...",
    "name": "Default",
    "created_at": "2025-12-16T00:00:00Z"
  }
}
```

**Note:** The `key` field is only returned once at creation. Store it securely.

### POST /v1/auth/token

Exchange API key for JWT access token.

**Request:**
```http
POST /v1/auth/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Bearer sk_live_k1_abc123...

grant_type=api_key&
scope=math:read%20usage:read
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "rt_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "scope": "math:read usage:read"
}
```

### POST /v1/auth/token (refresh)

Refresh an access token.

**Request:**
```http
POST /v1/auth/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=rt_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "rt_new_token_xyz",
  "scope": "math:read usage:read"
}
```

### GET /v1/auth/keys

List user's API keys.

**Response:**
```json
{
  "keys": [
    {
      "id": "key_01HZXK5N9RTYUIO67890DEF",
      "prefix": "sk_live_k1_",
      "name": "Default",
      "scopes": "math:read math:write usage:read",
      "last_used_at": "2025-12-15T10:30:00Z",
      "created_at": "2025-12-01T00:00:00Z"
    }
  ]
}
```

### POST /v1/auth/keys

Create a new API key.

**Request:**
```json
{
  "name": "CI/CD Pipeline",
  "scopes": "math:read usage:read"
}
```

**Response:**
```json
{
  "id": "key_01HZXK6P0SZXCVB23456JKL",
  "key": "sk_live_k2_def456...",
  "name": "CI/CD Pipeline",
  "scopes": "math:read usage:read",
  "created_at": "2025-12-16T00:00:00Z"
}
```

### POST /v1/auth/keys/rotate

Rotate an API key with grace period.

**Request:**
```json
{
  "key_id": "key_01HZXK5N9RTYUIO67890DEF",
  "grace_period_days": 7
}
```

**Response:**
```json
{
  "old_key": {
    "id": "key_01HZXK5N9RTYUIO67890DEF",
    "expires_at": "2025-12-23T00:00:00Z"
  },
  "new_key": {
    "id": "key_01HZXK7Q1TABCDE34567MNO",
    "key": "sk_live_k3_ghi789...",
    "created_at": "2025-12-16T00:00:00Z"
  }
}
```

### DELETE /v1/auth/keys/{key_id}

Revoke an API key immediately.

**Response:**
```json
{
  "revoked": true,
  "revoked_at": "2025-12-16T00:00:00Z"
}
```

---

## JWKS Endpoint

### GET /.well-known/jwks.json

Public keys for JWT verification.

**Response:**
```json
{
  "keys": [
    {
      "kty": "EC",
      "crv": "P-256",
      "kid": "mcpworks-api-2025-001",
      "use": "sig",
      "alg": "ES256",
      "x": "base64url-encoded-x-coordinate",
      "y": "base64url-encoded-y-coordinate"
    }
  ]
}
```

---

## Security Requirements

### Rate Limiting

| Endpoint | Limit |
|----------|-------|
| `/v1/auth/register` | 10/hour per IP |
| `/v1/auth/token` | 100/minute per API key |
| `/v1/auth/keys` | 50/minute per user |

### Password Requirements

- Minimum 12 characters
- Argon2id hashing (memory: 64MB, iterations: 3)

### Token Security

- ES256 signatures (ECDSA P-256)
- 1-hour access token lifetime
- Single-use refresh tokens (rotation on use)
- Key stored as SHA-256 hash only

---

## Technology Decisions

### JWT Signing: ES256

- 128-bit security with compact 64-byte signatures
- Faster verification than RSA
- Stateless validation via JWKS

### ID Generation: ULID

- Format: `{prefix}_{ulid}` (e.g., `usr_01HZXK4M8Q...`)
- Sortable, URL-safe, no coordination needed

### Password Hashing: Argon2id

- PHC winner, memory-hard
- Parameters: 64MB memory, 3 iterations, 4 parallelism

### Rate Limiting: Sliding Window (Redis)

- Smoother than fixed windows
- Per-client and per-IP tracking

---

## Migration Notes

### From mcpworks-auth

The original mcpworks-auth design included:
- Full OAuth 2.1 (authorization_code, client_credentials, refresh_token)
- Dynamic client registration (RFC 7591)
- Token introspection (RFC 7662) and revocation (RFC 7009)
- Google and GitHub federation
- MFA (TOTP + WebAuthn)

For MVP, we simplify to:
- API key → JWT exchange only
- No OAuth flows (no /authorize endpoint)
- No federation (email/password only)
- No MFA (deferred to A1)

### Future Expansion (A1+)

When/if full OAuth 2.1 is needed:
1. Add `/authorize` endpoint with PKCE
2. Add dynamic client registration
3. Add federated identity providers
4. The token format and validation remain the same

---

## References

- [MCP Authorization Spec (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization)
- [OAuth 2.1 Draft](https://oauth.net/2.1/)
- [RFC 7636 - PKCE](https://tools.ietf.org/html/rfc7636)
- [PyJWT Documentation](https://pyjwt.readthedocs.io/)
- [Authlib Documentation](https://docs.authlib.org/)

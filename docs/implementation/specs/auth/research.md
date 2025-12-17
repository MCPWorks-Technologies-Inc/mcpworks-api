# Auth Technology Research

**Source:** mcpworks-auth specs/001-oauth-server/research.md
**Date:** 2025-12-16

This document captures technology decisions for authentication, applicable to the baked-in auth in mcpworks-api.

---

## 1. JWT Signing Algorithm

### Decision: ES256 (ECDSA P-256)

**Rationale:**
- 128-bit security with compact 64-byte signatures
- Faster verification than RSA
- Stateless validation via JWKS
- Standard for modern OAuth implementations

**Alternatives Rejected:**

| Algorithm | Rejected Because |
|-----------|------------------|
| RS256 | Larger tokens, slower verification |
| HS256 | Symmetric - can't do stateless validation |
| EdDSA | Less universal library support |

---

## 2. ID Generation

### Decision: ULID (Universally Unique Lexicographically Sortable Identifier)

**Format:**
- Users: `usr_01HZXK4M8QWERTY12345ABC`
- Keys: `key_01HZXK5N9RTYUIO67890DEF`
- Tokens: `tok_01HZXK6P0SZXCVB23456JKL`

**Rationale:**
- Sortable (time-ordered)
- 26 characters (compact)
- URL-safe
- Type prefix for identification
- No coordination required

---

## 3. Password Hashing

### Decision: Argon2id

**Parameters:**
- Memory: 64 MB
- Iterations: 3
- Parallelism: 4
- Hash length: 32 bytes

**Rationale:**
- PHC winner
- Memory-hard (resistant to GPU attacks)
- OWASP recommended

**Alternatives Rejected:**

| Algorithm | Rejected Because |
|-----------|------------------|
| bcrypt | 72 byte limit, not memory-hard |
| scrypt | Harder to tune |
| PBKDF2 | GPU vulnerable |

---

## 4. Rate Limiting

### Decision: Sliding Window (Redis)

**Rationale:**
- Smoother than fixed windows
- Redis ZSET for O(log N) operations
- Per-key and per-IP tracking

**Implementation:**
```python
# Store request timestamps in sorted set
key = f"ratelimit:token:{api_key_prefix}"
# TTL: window size (60 seconds)
# Check count in window, reject if over limit
```

---

## 5. Key Rotation Strategy

### Decision: 14-Day Overlap

**Process:**
1. Generate new ES256 key pair
2. Add to JWKS (not yet signing)
3. Wait 7 days
4. Activate new key for signing
5. Keep old key in JWKS 7 more days
6. Remove old key

**Key Naming:** `mcpworks-api-{year}-{seq}`

---

## 6. API Key Format

### Decision: Prefixed Secure Random

**Format:** `sk_{env}_{keyID}_{random}`

**Example:** `sk_live_k1_abc123def456ghi789jkl012mno345pqr678`

**Components:**
- `sk_` - Secret key prefix
- `{env}` - `live` or `test`
- `{keyID}` - Rotation identifier (`k1`, `k2`, etc.)
- `{random}` - 32 bytes Base62 (43 characters)

**Rationale:**
- Prefix identifies key type at glance
- Environment prevents accidental cross-use
- Key ID tracks rotation
- Sufficient entropy (256 bits)

---

## 7. Dependencies

```toml
[project]
dependencies = [
    "fastapi>=0.109.0",
    "pyjwt[crypto]>=2.8.0",
    "cryptography>=42.0.0",
    "argon2-cffi>=23.1.0",
    "redis>=5.0.0",
    "python-ulid>=2.2.0",
]
```

---

## 8. Deferred Decisions (A1+)

These decisions from mcpworks-auth are deferred for MVP:

| Topic | Original Decision | MVP Status |
|-------|-------------------|------------|
| OAuth Library | authlib | Deferred - no OAuth flows yet |
| Federation | Google + GitHub | Deferred |
| MFA | TOTP + WebAuthn | Deferred |
| Client Registration | RFC 7591 | Deferred |
| Token Introspection | RFC 7662 | Deferred |

When needed, refer to original mcpworks-auth SPEC.md for full specifications.

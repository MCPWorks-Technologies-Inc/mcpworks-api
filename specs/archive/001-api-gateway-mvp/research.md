# Research: API Gateway MVP

**Feature**: 001-api-gateway-mvp
**Date**: 2025-12-16
**Status**: Complete

## Overview

This document captures technology decisions and best practices research for the API Gateway MVP implementation.

---

## 1. JWT Signing Algorithm

**Decision**: ES256 (ECDSA with P-256 curve)

**Rationale**:
- Asymmetric algorithm allows public key distribution for token verification
- Shorter signatures than RS256 (64 bytes vs 256 bytes) - better for token size
- Well-supported in PyJWT and standard JWT libraries
- Recommended by MCP OAuth 2.1 specification
- Future-proof for distributed verification (gateway can verify without private key)

**Alternatives Considered**:
- HS256: Symmetric, simpler but requires shared secret distribution
- RS256: Asymmetric but larger signatures, more CPU for signing
- EdDSA: Modern but less library support in current ecosystem

**Implementation**:
```python
# Generate key pair once, store in secrets
from cryptography.hazmat.primitives.asymmetric import ec
private_key = ec.generate_private_key(ec.SECP256R1())
```

---

## 2. Password/API Key Hashing

**Decision**: Argon2id with memory-hard parameters

**Rationale**:
- Winner of Password Hashing Competition (2015)
- Memory-hard: resistant to GPU/ASIC attacks
- Argon2id variant: best of Argon2i (side-channel resistant) and Argon2d (GPU resistant)
- Recommended by OWASP for password storage

**Parameters** (OWASP 2024 recommendations):
- Memory: 64 MiB (65536 KiB)
- Iterations: 3
- Parallelism: 4
- Salt: 16 bytes (auto-generated)
- Hash length: 32 bytes

**Alternatives Considered**:
- bcrypt: Good but memory parameter is fixed
- scrypt: Memory-hard but more complex to tune
- PBKDF2: CPU-bound only, vulnerable to GPU attacks

**Implementation**:
```python
from argon2 import PasswordHasher
ph = PasswordHasher(
    memory_cost=65536,  # 64 MiB
    time_cost=3,
    parallelism=4
)
```

---

## 3. Rate Limiting Strategy

**Decision**: Redis-based sliding window with per-IP and per-user limits

**Rationale**:
- Sliding window more accurate than fixed window (no burst at boundary)
- Redis provides atomic operations and TTL support
- Separate limits for IP (unauthenticated) and user (authenticated)
- Can be shared across multiple API instances

**Limits**:
| Scope | Limit | Window | Use Case |
|-------|-------|--------|----------|
| IP (unauth) | 100 req | 1 hour | Prevent scanning/abuse |
| IP (auth fail) | 5 req | 1 minute | Prevent brute force |
| User (auth) | 1000 req | 1 hour | Normal usage |
| User (credits) | 100 ops | 1 minute | Prevent credit manipulation |

**Alternatives Considered**:
- In-memory (per-instance): Doesn't work with multiple instances
- Token bucket: More complex, sliding window sufficient for MVP
- API gateway rate limiting: Adds external dependency

**Implementation**:
```python
# Redis key pattern: ratelimit:{scope}:{identifier}:{window}
# Use INCR with EXPIRE for sliding window approximation
```

---

## 4. Database Row Locking for Credits

**Decision**: PostgreSQL SELECT FOR UPDATE with NOWAIT

**Rationale**:
- Pessimistic locking prevents race conditions on credit balance
- NOWAIT returns immediately if lock unavailable (fail fast)
- PostgreSQL provides ACID guarantees within transaction
- Simple to implement with SQLAlchemy async

**Pattern**:
```python
async with db.begin():
    # Lock the credit row
    result = await db.execute(
        select(Credit)
        .where(Credit.user_id == user_id)
        .with_for_update(nowait=True)
    )
    credit = result.scalar_one()

    # Check and modify
    if credit.available_balance < amount:
        raise InsufficientCreditsError()

    credit.available_balance -= amount
    credit.held_balance += amount

    # Commit happens on context exit
```

**Alternatives Considered**:
- Optimistic locking (version column): More conflicts under concurrent load
- Serializable isolation: Higher performance overhead
- Application-level locking: Race conditions possible

---

## 5. Stripe Integration Pattern

**Decision**: Webhook-first with Checkout Sessions

**Rationale**:
- Stripe Checkout handles PCI compliance (no card data on our servers)
- Webhooks are source of truth for subscription state
- Idempotency keys prevent duplicate processing
- Retry handling via Stripe's exponential backoff

**Event Handling**:
| Event | Action |
|-------|--------|
| `checkout.session.completed` | Create subscription record |
| `customer.subscription.created` | Grant initial credits |
| `customer.subscription.updated` | Update tier if changed |
| `customer.subscription.deleted` | Downgrade to free |
| `invoice.payment_succeeded` | Grant monthly credits |
| `invoice.payment_failed` | Set grace period flag |

**Alternatives Considered**:
- Stripe Elements: More control but PCI compliance burden
- PaymentIntents directly: More complex, less suited for subscriptions

---

## 6. Service Health Check Pattern

**Decision**: Background task with circuit breaker

**Rationale**:
- Background checks (every 30s) don't add latency to requests
- Circuit breaker pattern prevents cascading failures
- Health status cached in Redis for fast lookups
- Allows graceful degradation (return 503 for unhealthy services)

**Circuit Breaker States**:
- **Closed**: Normal operation, forward requests
- **Open**: Service unhealthy, fail fast with 503
- **Half-Open**: After timeout, allow one request to test recovery

**Parameters**:
- Failure threshold: 3 consecutive failures → Open
- Recovery timeout: 30 seconds → Half-Open
- Success threshold: 2 consecutive successes → Closed

**Alternatives Considered**:
- Inline health checks: Adds latency to every request
- No circuit breaker: Risk of slow cascading failures
- External load balancer: Adds infrastructure complexity

---

## 7. Correlation ID / Request Tracing

**Decision**: X-Request-ID header with UUID generation

**Rationale**:
- Standard header recognized by many tools
- UUID ensures uniqueness across distributed systems
- Propagated to downstream services for tracing
- Logged with every request for debugging

**Flow**:
1. Check for incoming X-Request-ID header
2. If missing, generate UUID v4
3. Add to response headers
4. Include in all log entries
5. Forward to downstream service calls

**Alternatives Considered**:
- W3C Trace Context: More complex, overkill for current scale
- Custom header: Less tooling support
- No tracing: Debugging distributed issues impossible

---

## 8. Auto-Release Hold Timeout

**Decision**: 1-hour timeout with background cleanup

**Rationale**:
- Matches typical workflow execution timeout
- Prevents credits being locked indefinitely
- Background task runs every 5 minutes to clean up
- Audit log entry created for auto-released holds

**Implementation**:
```python
# Celery/APScheduler task running every 5 minutes
async def cleanup_stale_holds():
    stale_cutoff = datetime.utcnow() - timedelta(hours=1)

    async with db.begin():
        stale_holds = await db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.type == "hold")
            .where(CreditTransaction.created_at < stale_cutoff)
            .where(~exists(
                select(CreditTransaction)
                .where(CreditTransaction.hold_id == CreditTransaction.id)
                .where(CreditTransaction.type.in_(["commit", "release"]))
            ))
        )

        for hold in stale_holds.scalars():
            await release_credits(hold.id, reason="timeout")
```

**Alternatives Considered**:
- Longer timeout (24h): Risk of user confusion about available balance
- Shorter timeout (15min): May not cover all workflow executions
- No auto-release: Credits could be locked forever

---

## 9. API Key Format

**Decision**: `sk_{env}_{keyNum}_{random}` format

**Rationale**:
- Prefix `sk_` identifies as secret key (standard convention)
- Environment (`live`/`test`) prevents accidental production use
- Key number (`k1`, `k2`) enables multiple keys per user for rotation
- Random portion (32 chars) provides entropy

**Format Details**:
- Total length: ~50 characters
- Random portion: 32 chars base62 (alphanumeric)
- Example: `sk_live_k1_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456`

**Storage**:
- Only hash stored in database (Argon2id)
- First 12 chars (`sk_live_k1_a`) stored as prefix for identification
- Full key shown exactly once on creation

**Alternatives Considered**:
- UUID format: Less readable, no environment indication
- Simple random: No metadata, harder to manage
- JWT-based keys: Adds complexity, not needed for API keys

---

## 10. Prometheus Metrics

**Decision**: prometheus-fastapi-instrumentator with custom metrics

**Rationale**:
- Automatic HTTP metrics (requests, latency, status codes)
- Custom metrics for business logic (credits, auth)
- Standard Prometheus format for Grafana dashboards
- Low overhead, async-compatible

**Metrics Exposed**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_requests_total` | Counter | method, endpoint, status | Request count |
| `http_request_duration_seconds` | Histogram | method, endpoint | Request latency |
| `credit_transactions_total` | Counter | type, status | Credit operations |
| `credit_balance_available` | Gauge | tier | Total available credits by tier |
| `auth_attempts_total` | Counter | status, method | Auth attempts |
| `service_health_status` | Gauge | service | Backend service health (0/1) |

**Alternatives Considered**:
- OpenTelemetry: More complex, overkill for MVP
- StatsD: Requires additional aggregation service
- Custom metrics only: Miss standard HTTP metrics

---

## Summary

All technology decisions align with:
- **Constitution principles**: Security, observability, transaction safety
- **Spec requirements**: Performance targets, functional requirements
- **Industry best practices**: OWASP, Stripe docs, PostgreSQL patterns
- **MVP scope**: Simple but production-ready patterns

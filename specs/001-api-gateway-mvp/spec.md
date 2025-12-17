# Feature Specification: API Gateway MVP

**Feature Branch**: `001-api-gateway-mvp`
**Created**: 2025-12-16
**Status**: Draft
**Input**: Build mcpworks-api as a focused API gateway and orchestration layer for the mcpworks platform.

## Overview

The mcpworks-api serves as the central gateway for the mcpworks platform - an AI-native workflow automation system. This API handles authentication, credit/token accounting, and routing to specialized microservices (mcpworks-math, mcpworks-agent). It does NOT contain workflow business logic; that lives in dedicated services.

**Architecture Pattern**: Thin API Gateway - authentication, accounting, routing. Actual business logic lives in specialized microservices.

**Key Principle**: This service is the trust boundary. All requests from external clients (mcpworks-gateway proxy) authenticate here before being routed to internal services.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - API Key Authentication Flow (Priority: P1)

A developer using Claude Code wants to execute workflows. The mcpworks-gateway (local proxy) sends requests with an API key. The API must validate the key and issue a short-lived JWT for subsequent requests.

**Why this priority**: Without authentication, no other functionality can work. This is the foundation of the entire platform's security model.

**Independent Test**: Can be fully tested with curl/httpie - send API key, receive JWT, use JWT on protected endpoint. Delivers secure access to the platform.

**Acceptance Scenarios**:

1. **Given** a valid API key `sk_live_k1_abc123...`, **When** POST to `/v1/auth/token`, **Then** receive 200 with `access_token` (JWT, 1h expiry), `refresh_token` (7d expiry), and `token_type: bearer`
2. **Given** an invalid/revoked API key, **When** POST to `/v1/auth/token`, **Then** receive 401 with error code `INVALID_API_KEY`
3. **Given** a valid JWT, **When** GET to `/v1/users/me`, **Then** receive user profile including tier, credit balance
4. **Given** an expired JWT, **When** any authenticated request, **Then** receive 401 with error code `TOKEN_EXPIRED`
5. **Given** a valid refresh token, **When** POST to `/v1/auth/refresh`, **Then** receive new access_token without requiring API key

---

### User Story 2 - Credit Balance & Hold/Commit/Release (Priority: P1)

Before executing a workflow, the system must hold credits from the user's balance. On success, credits are committed (charged). On failure, credits are released back.

**Why this priority**: Credit accounting is the monetization foundation. Without it, we cannot bill users or prevent abuse.

**Independent Test**: Can be tested by calling hold, then commit or hold, then release sequences. Verifies no double-charging and correct balance updates.

**Acceptance Scenarios**:

1. **Given** user has 100 credits available, **When** hold 25 credits requested, **Then** available_balance becomes 75, held_balance becomes 25, total unchanged
2. **Given** 25 credits held (hold_id: h123), **When** commit 20 credits, **Then** held_balance decreases by 25, 5 credits returned to available (partial commit)
3. **Given** 25 credits held (hold_id: h123), **When** release requested, **Then** all 25 credits return to available_balance, held_balance becomes 0
4. **Given** user has 10 credits available, **When** hold 25 credits requested, **Then** receive 400 with error code `INSUFFICIENT_CREDITS`, balances unchanged
5. **Given** concurrent hold requests totaling more than available, **When** processed, **Then** only requests that fit are approved, others rejected (no overdraft)

---

### User Story 3 - Service Routing to mcpworks-math (Priority: P2)

AI assistants need to call the Math MCP for calculations. The API gateway routes these requests to the mcpworks-math service after authentication and credit checks.

**Why this priority**: Math MCP is the free viral hook - it must work for user acquisition. But auth/credits must work first.

**Independent Test**: Authenticated request to `/v1/services/math/verify` routes to mcpworks-math and returns result. Demonstrates end-to-end routing.

**Acceptance Scenarios**:

1. **Given** authenticated user with free tier, **When** POST to `/v1/services/math/verify` with math problem, **Then** request routed to mcpworks-math, result returned (0 credits charged - free service)
2. **Given** authenticated user, **When** GET to `/v1/services`, **Then** receive list of available services with their credit costs and tier requirements
3. **Given** mcpworks-math service is unhealthy, **When** request to math endpoint, **Then** receive 503 with error code `SERVICE_UNAVAILABLE` and retry-after header

---

### User Story 4 - Service Routing to mcpworks-agent (Priority: P2)

Users with workflows want to execute them via AI assistants. The gateway routes execution requests to mcpworks-agent after holding credits.

**Why this priority**: This enables the core product (workflow execution) but depends on auth and credits being solid first.

**Independent Test**: Execute workflow via `/v1/services/agent/execute/{workflow_id}`, verify credits held/committed, result returned.

**Acceptance Scenarios**:

1. **Given** authenticated user with published workflow, **When** POST to `/v1/services/agent/execute/{workflow_id}`, **Then** credits held, request routed to mcpworks-agent, execution started
2. **Given** workflow execution completes successfully, **When** mcpworks-agent sends callback, **Then** credits committed, execution result stored
3. **Given** workflow execution fails, **When** mcpworks-agent sends failure callback, **Then** credits released, error recorded

---

### User Story 5 - Stripe Subscription Management (Priority: P3)

Users upgrade from free to paid tiers via Stripe. The API handles subscription lifecycle and grants monthly credits.

**Why this priority**: Monetization is critical but can be manually managed for first 5-10 pilot users. Automation needed for scale.

**Independent Test**: Create subscription via Stripe Checkout, verify tier upgraded, credits granted.

**Acceptance Scenarios**:

1. **Given** free tier user, **When** POST to `/v1/subscriptions` with `tier: starter`, **Then** Stripe Checkout session created, redirect URL returned
2. **Given** Stripe webhook `customer.subscription.created`, **When** processed, **Then** user tier updated, monthly credits granted
3. **Given** Stripe webhook `invoice.payment_failed`, **When** processed, **Then** user notified, grace period started
4. **Given** active subscription, **When** DELETE to `/v1/subscriptions/current`, **Then** subscription marked for cancellation at period end

---

### User Story 6 - User Registration & API Key Management (Priority: P3)

New users register and obtain API keys to integrate with mcpworks-gateway.

**Why this priority**: Needed for self-service, but pilot users can be manually onboarded initially.

**Independent Test**: Register user, login, generate API key, use key to authenticate.

**Acceptance Scenarios**:

1. **Given** new user email, **When** POST to `/v1/auth/register`, **Then** user created, verification email sent, initial API key returned
2. **Given** authenticated user, **When** POST to `/v1/users/me/api-keys`, **Then** new API key generated (shown once), key_id returned for management
3. **Given** authenticated user with multiple API keys, **When** DELETE to `/v1/users/me/api-keys/{key_id}`, **Then** key revoked, cannot be used
4. **Given** API key approaching expiry (if expiry set), **When** 7 days before expiry, **Then** user notified via email

---

### Edge Cases

- **Race condition on credits**: Two simultaneous holds that would overdraft - second must fail atomically
- **JWT stolen/compromised**: User can revoke all sessions via `/v1/auth/logout-all`
- **Stripe webhook replay**: Idempotency keys prevent duplicate credit grants
- **Service timeout**: Gateway returns 504 after 30s, releases any held credits
- **User deleted mid-execution**: Execution completes, credits committed, but user marked deleted
- **Negative balance prevention**: Database CHECK constraint ensures available_balance >= 0

## Requirements *(mandatory)*

### Functional Requirements

**Authentication (AUTH)**
- **FR-AUTH-001**: System MUST accept API keys in format `sk_{env}_{keyNum}_{random}` (e.g., `sk_live_k1_abc123`)
- **FR-AUTH-002**: System MUST issue JWT access tokens signed with ES256, 1-hour expiry
- **FR-AUTH-003**: System MUST issue refresh tokens with 7-day expiry, stored server-side
- **FR-AUTH-004**: System MUST hash API keys with Argon2id before storage (never store plaintext)
- **FR-AUTH-005**: System MUST support API key rotation (multiple active keys per user)
- **FR-AUTH-006**: System MUST rate-limit failed authentication attempts (5/minute per IP)

**Credit Accounting (CREDIT)**
- **FR-CREDIT-001**: System MUST implement hold/commit/release pattern for all credit operations
- **FR-CREDIT-002**: System MUST use database row-level locking for credit modifications
- **FR-CREDIT-003**: System MUST track: available_balance, held_balance, lifetime_earned, lifetime_spent
- **FR-CREDIT-004**: System MUST create audit trail for every credit transaction (type, amount, timestamp, reference)
- **FR-CREDIT-005**: System MUST enforce available_balance >= 0 via database constraint
- **FR-CREDIT-006**: System MUST auto-release holds after 1 hour if no commit/release received

**Service Routing (ROUTE)**
- **FR-ROUTE-001**: System MUST route requests to mcpworks-math at configurable URL
- **FR-ROUTE-002**: System MUST route requests to mcpworks-agent at configurable URL
- **FR-ROUTE-003**: System MUST perform health checks on backend services (every 30s)
- **FR-ROUTE-004**: System MUST return service catalog via GET /v1/services with costs and tier requirements
- **FR-ROUTE-005**: System MUST reject requests to services user's tier doesn't permit

**Billing (BILL)**
- **FR-BILL-001**: System MUST integrate with Stripe for subscription management
- **FR-BILL-002**: System MUST support 4 tiers: free, starter ($29/mo), pro ($99/mo), enterprise ($299+/mo)
- **FR-BILL-003**: System MUST grant monthly credits on subscription creation and renewal
- **FR-BILL-004**: System MUST handle Stripe webhooks for subscription lifecycle events
- **FR-BILL-005**: System MUST support one-time credit purchases via Stripe

**Observability (OBS)**
- **FR-OBS-001**: System MUST log all requests with correlation ID (X-Request-ID)
- **FR-OBS-002**: System MUST expose /health endpoint with database and Redis connectivity status
- **FR-OBS-003**: System MUST emit Prometheus metrics for request count, latency, error rate
- **FR-OBS-004**: System MUST log all credit transactions for audit purposes

### Key Entities

- **User**: Account holder with email, password_hash, name, tier, created_at, status
- **APIKey**: Credential for programmatic access - key_hash, key_prefix, user_id, scopes, expires_at, revoked_at
- **Credit**: Balance tracking - user_id, available_balance, held_balance, lifetime_earned, lifetime_spent
- **CreditTransaction**: Audit trail - type (hold/commit/release/purchase/grant), amount, balance_before, balance_after, hold_id, created_at
- **Subscription**: Stripe subscription state - user_id, tier, status, stripe_subscription_id, current_period_start/end
- **Service**: Registered backend service - name, url, health_check_url, credit_cost, tier_required

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can authenticate and receive JWT within 200ms (p95)
- **SC-002**: Credit hold/commit/release operations complete within 100ms (p95)
- **SC-003**: Zero double-charging incidents (credit committed twice for same operation)
- **SC-004**: Service routing adds less than 50ms latency to backend service calls
- **SC-005**: System handles 100 concurrent authenticated requests without degradation
- **SC-006**: 99.9% of Stripe webhooks processed successfully within 5 seconds
- **SC-007**: All credit transactions have complete audit trail (queryable by user, date range, type)
- **SC-008**: Health check endpoint responds within 100ms, accurately reflects service state
- **SC-009**: Failed authentication attempts rate-limited effectively (no brute force possible)
- **SC-010**: Pilot users (5-10) can complete full workflow: register, subscribe, execute workflow, view usage

## Assumptions

- mcpworks-math service is already deployed and accessible via HTTP
- mcpworks-agent service will be developed in parallel and available for integration testing
- Stripe account is configured with products for each tier
- PostgreSQL 15+ with row-level locking support is available
- Redis 7+ is available for rate limiting and session management
- Users access API via mcpworks-gateway proxy (not directly)

## Dependencies

- **mcpworks-math**: Must be running for math routing tests
- **mcpworks-agent**: Must be running for workflow execution tests (can mock initially)
- **Stripe**: Account and API keys configured
- **PostgreSQL**: Primary data store
- **Redis**: Rate limiting, session storage, caching

## Out of Scope

- Workflow CRUD operations (handled by mcpworks-agent)
- Activepieces integration (handled by mcpworks-agent)
- Math verification logic (handled by mcpworks-math)
- Local proxy functionality (handled by mcpworks-gateway)
- Web dashboard UI (future phase)
- OAuth2 authorization code flow (deferred to A1)
- Federated login (Google, GitHub) (deferred to A1)
- MFA support (deferred to A1)

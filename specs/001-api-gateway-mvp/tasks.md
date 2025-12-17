# Tasks: API Gateway MVP

**Input**: Design documents from `/specs/001-api-gateway-mvp/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi.yaml

**Tests**: Tests not explicitly requested - excluded per template guidelines. Add test tasks if TDD approach is desired.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US6)
- Include exact file paths in descriptions

## Path Conventions

Based on plan.md project structure:
- Source: `src/mcpworks_api/`
- Tests: `tests/`
- Migrations: `alembic/versions/`

---

## Phase 1: Setup (Project Infrastructure)

**Purpose**: Initialize Python project with FastAPI, dependencies, and basic structure

- [ ] T001 Create project structure: `src/mcpworks_api/`, `tests/`, `alembic/` directories
- [ ] T002 Initialize Python project with pyproject.toml including FastAPI 0.109+, SQLAlchemy 2.0+, Pydantic v2, httpx, PyJWT, argon2-cffi, stripe dependencies
- [ ] T003 [P] Create `.env.example` with required environment variables per quickstart.md
- [ ] T004 [P] Create `docker-compose.yml` for local PostgreSQL 15+ and Redis 7+ services
- [ ] T005 [P] Create `Dockerfile` for API container
- [ ] T006 [P] Configure ruff/black/mypy in pyproject.toml for code quality
- [ ] T007 Create `src/mcpworks_api/__init__.py` with version string
- [ ] T008 Create `src/mcpworks_api/config.py` with Settings class using pydantic-settings

**Checkpoint**: Project structure ready, can run `pip install -e .`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

### Database & Core Infrastructure

- [ ] T009 Create `src/mcpworks_api/core/__init__.py`
- [ ] T010 Create `src/mcpworks_api/core/database.py` with async SQLAlchemy engine and session factory
- [ ] T011 [P] Create `src/mcpworks_api/core/redis.py` with async Redis connection pool
- [ ] T012 [P] Create `src/mcpworks_api/core/exceptions.py` with custom exception classes (InsufficientCreditsError, InvalidApiKeyError, etc.)
- [ ] T013 Initialize Alembic in `alembic/` directory with async PostgreSQL support
- [ ] T014 Create `src/mcpworks_api/models/__init__.py`
- [ ] T015 Create `src/mcpworks_api/models/base.py` with SQLAlchemy declarative base and common mixins (TimestampMixin, UUIDMixin)

### Security Infrastructure (per research.md decisions)

- [ ] T016 Create `src/mcpworks_api/core/security.py` with Argon2id password hasher (64MiB memory, 3 iterations, parallelism 4)
- [ ] T017 Add ES256 JWT key pair generation script in `scripts/generate_keys.py`
- [ ] T018 Add JWT encode/decode functions to `src/mcpworks_api/core/security.py` using PyJWT with ES256

### Shared Models (used by multiple stories)

- [ ] T019 Create User model in `src/mcpworks_api/models/user.py` with fields from data-model.md (id, email, password_hash, name, tier, status, email_verified, verification_token, timestamps)
- [ ] T020 Create Alembic migration for users table in `alembic/versions/001_create_users_table.py`
- [ ] T021 Create Service model in `src/mcpworks_api/models/service.py` with fields from data-model.md (id, name, display_name, url, health_check_url, credit_cost, tier_required, status, timestamps)
- [ ] T022 Create Alembic migration for services table in `alembic/versions/002_create_services_table.py`
- [ ] T023 Create AuditLog model in `src/mcpworks_api/models/audit.py` with fields from data-model.md
- [ ] T024 Create Alembic migration for audit_logs table in `alembic/versions/003_create_audit_logs_table.py`

### API Structure

- [ ] T025 Create `src/mcpworks_api/api/__init__.py`
- [ ] T026 Create `src/mcpworks_api/api/v1/__init__.py`
- [ ] T027 Create `src/mcpworks_api/api/v1/router.py` as main v1 router aggregating all endpoint routers
- [ ] T028 Create `src/mcpworks_api/schemas/__init__.py`
- [ ] T029 Create `src/mcpworks_api/services/__init__.py`

### Middleware Infrastructure

- [ ] T030 Create `src/mcpworks_api/middleware/__init__.py`
- [ ] T031 Create `src/mcpworks_api/middleware/correlation.py` with X-Request-ID handling per research.md decision 7
- [ ] T032 [P] Create `src/mcpworks_api/middleware/metrics.py` with prometheus-fastapi-instrumentator setup per research.md decision 10
- [ ] T033 Create `src/mcpworks_api/dependencies.py` with get_db, get_redis, get_current_user dependency providers

### Main Application

- [ ] T034 Create `src/mcpworks_api/main.py` with FastAPI app, middleware registration, router inclusion, health endpoint stub

### Seed Data

- [ ] T035 Create `scripts/seed_services.py` to seed math and agent services into database

**Checkpoint**: Foundation ready - can run migrations, start server, hit /health endpoint. User story implementation can now begin.

---

## Phase 3: User Story 1 - API Key Authentication Flow (Priority: P1) MVP

**Goal**: Enable API key → JWT authentication flow for mcpworks-gateway proxy

**Independent Test**: `curl -X POST /v1/auth/token -d '{"api_key": "sk_test_k1_..."}' → JWT tokens`

**Acceptance Scenarios** (from spec.md):
1. Valid API key → 200 with access_token, refresh_token, token_type
2. Invalid/revoked key → 401 with INVALID_API_KEY
3. Valid JWT → GET /users/me returns profile
4. Expired JWT → 401 with TOKEN_EXPIRED
5. Valid refresh token → new access_token

### Models for US1

- [ ] T036 [P] [US1] Create APIKey model in `src/mcpworks_api/models/user.py` with fields from data-model.md (id, user_id, key_hash, key_prefix, name, scopes, last_used_at, timestamps, expires_at, revoked_at)
- [ ] T037 [US1] Create Alembic migration for api_keys table in `alembic/versions/004_create_api_keys_table.py`

### Schemas for US1

- [ ] T038 [P] [US1] Create auth schemas in `src/mcpworks_api/schemas/auth.py`: TokenRequest, TokenResponse, RefreshRequest per openapi.yaml
- [ ] T039 [P] [US1] Create user schemas in `src/mcpworks_api/schemas/user.py`: UserProfile, ApiKeySummary, ApiKeyList per openapi.yaml

### Services for US1

- [ ] T040 [US1] Create AuthService in `src/mcpworks_api/services/auth.py` with:
  - `generate_api_key()` - creates sk_{env}_{keyNum}_{random} format key per research.md decision 9
  - `hash_api_key()` - Argon2id hash
  - `validate_api_key()` - lookup by prefix, verify hash, check not revoked/expired
  - `create_access_token()` - ES256 JWT with 1h expiry
  - `create_refresh_token()` - 7d expiry token
  - `validate_access_token()` - decode and verify JWT
  - `validate_refresh_token()` - validate refresh token

### Middleware for US1

- [ ] T041 [US1] Create `src/mcpworks_api/middleware/auth.py` with JWT validation middleware extracting user from Bearer token
- [ ] T042 [US1] Create `src/mcpworks_api/middleware/rate_limit.py` with Redis sliding window rate limiter per research.md decision 3 (5/min auth failures per IP)

### Endpoints for US1

- [ ] T043 [US1] Create `src/mcpworks_api/api/v1/auth.py` with:
  - POST /auth/token - exchange API key for JWT tokens (FR-AUTH-001, FR-AUTH-002, FR-AUTH-003)
  - POST /auth/refresh - refresh access token
  - POST /auth/logout-all - revoke all refresh tokens
- [ ] T044 [US1] Create `src/mcpworks_api/api/v1/users.py` with:
  - GET /users/me - return authenticated user profile with credits

### Integration for US1

- [ ] T045 [US1] Wire auth router and users router into `src/mcpworks_api/api/v1/router.py`
- [ ] T046 [US1] Add rate limiting middleware to auth endpoints in `src/mcpworks_api/main.py`
- [ ] T047 [US1] Add audit logging for login events in AuthService

**Checkpoint**: User Story 1 complete. Can authenticate with API key, receive JWT, access protected endpoints.

---

## Phase 4: User Story 2 - Credit Balance & Hold/Commit/Release (Priority: P1) MVP

**Goal**: Enable transaction-safe credit accounting with hold/commit/release pattern

**Independent Test**: Hold → Commit sequence; Hold → Release sequence; verify balances

**Acceptance Scenarios** (from spec.md):
1. Hold 25 from 100 → available=75, held=25
2. Commit 20 from 25 hold → 5 returned to available
3. Release 25 hold → all returned to available
4. Insufficient credits → 400 INSUFFICIENT_CREDITS
5. Concurrent holds → atomic, no overdraft

### Models for US2

- [ ] T048 [P] [US2] Create Credit model in `src/mcpworks_api/models/credit.py` with fields from data-model.md (user_id PK, available_balance, held_balance, lifetime_earned, lifetime_spent, updated_at)
- [ ] T049 [P] [US2] Create CreditTransaction model in `src/mcpworks_api/models/credit.py` with fields from data-model.md (id, user_id, type, amount, balance_before, balance_after, hold_id, execution_id, metadata, created_at)
- [ ] T050 [US2] Create Alembic migration for credits and credit_transactions tables in `alembic/versions/005_create_credits_tables.py` with CHECK constraints for non-negative balances

### Schemas for US2

- [ ] T051 [US2] Create credit schemas in `src/mcpworks_api/schemas/credit.py`: CreditBalance, CreditHoldRequest, CreditHoldResponse, CreditCommitRequest, CreditCommitResponse, CreditReleaseRequest, CreditReleaseResponse, Transaction, TransactionList per openapi.yaml

### Services for US2

- [ ] T052 [US2] Create CreditService in `src/mcpworks_api/services/credit.py` with:
  - `get_balance(user_id)` - return current credit balance
  - `hold_credits(user_id, amount, execution_id, metadata)` - SELECT FOR UPDATE NOWAIT, move from available to held, create transaction record per research.md decision 4
  - `commit_credits(hold_id, amount)` - deduct from held, handle partial commit, create transaction
  - `release_credits(hold_id, reason)` - return held to available, create transaction
  - `list_transactions(user_id, filters)` - paginated transaction history

### Background Tasks for US2

- [ ] T053 [US2] Create `src/mcpworks_api/tasks/credit_cleanup.py` with stale hold auto-release (1h timeout) per research.md decision 8

### Endpoints for US2

- [ ] T054 [US2] Create `src/mcpworks_api/api/v1/credits.py` with:
  - GET /credits - get balance (FR-CREDIT-003)
  - POST /credits/hold - hold credits (FR-CREDIT-001, FR-CREDIT-002)
  - POST /credits/commit - commit held credits (FR-CREDIT-001)
  - POST /credits/release - release held credits (FR-CREDIT-001)
  - GET /credits/transactions - list transactions (FR-CREDIT-004)

### Integration for US2

- [ ] T055 [US2] Wire credits router into `src/mcpworks_api/api/v1/router.py`
- [ ] T056 [US2] Add Credit record creation when user is created (trigger or service logic)
- [ ] T057 [US2] Add audit logging for credit operations

**Checkpoint**: User Story 2 complete. Can hold, commit, release credits with full transaction safety and audit trail.

---

## Phase 5: User Story 3 - Service Routing to mcpworks-math (Priority: P2)

**Goal**: Route authenticated requests to mcpworks-math service with health checks

**Independent Test**: POST /v1/services/math/verify with math problem → result from mcpworks-math

**Acceptance Scenarios** (from spec.md):
1. Free tier user → POST /services/math/verify → routed, result returned (0 credits)
2. GET /services → service catalog with costs and tiers
3. Math service unhealthy → 503 SERVICE_UNAVAILABLE with Retry-After

### Schemas for US3

- [ ] T058 [P] [US3] Create service schemas in `src/mcpworks_api/schemas/service.py`: ServiceCatalog, Service, MathRequest, MathResponse per openapi.yaml

### Services for US3

- [ ] T059 [US3] Create RoutingService in `src/mcpworks_api/services/routing.py` with:
  - `get_service(name)` - lookup service by name
  - `list_services()` - return service catalog
  - `check_tier_access(user_tier, service)` - verify user can access service
  - `route_request(service, method, path, body)` - forward request via httpx
  - `get_service_health(service)` - check cached health status from Redis
- [ ] T060 [US3] Create HealthCheckService in `src/mcpworks_api/services/health.py` with circuit breaker pattern per research.md decision 6:
  - Background health check task (every 30s)
  - Circuit breaker states: closed, open, half-open
  - Health status cached in Redis

### Endpoints for US3

- [ ] T061 [US3] Create `src/mcpworks_api/api/v1/services.py` with:
  - GET /services - list service catalog (FR-ROUTE-004)
  - POST /services/math/{operation} - route to mcpworks-math (FR-ROUTE-001)

### Integration for US3

- [ ] T062 [US3] Wire services router into `src/mcpworks_api/api/v1/router.py`
- [ ] T063 [US3] Register health check background task in `src/mcpworks_api/main.py` startup event
- [ ] T064 [US3] Add audit logging for service routing

**Checkpoint**: User Story 3 complete. Can call Math MCP through gateway, see service catalog, handle service unavailability.

---

## Phase 6: User Story 4 - Service Routing to mcpworks-agent (Priority: P2)

**Goal**: Route workflow execution requests to mcpworks-agent with credit hold/commit integration

**Independent Test**: POST /v1/services/agent/execute/{workflow_id} → credits held, execution started

**Acceptance Scenarios** (from spec.md):
1. Execute workflow → credits held, routed to agent, execution started
2. Agent success callback → credits committed
3. Agent failure callback → credits released

### Schemas for US4

- [ ] T065 [P] [US4] Add agent schemas to `src/mcpworks_api/schemas/service.py`: WorkflowExecuteRequest, WorkflowExecuteResponse, AgentCallback per openapi.yaml

### Services for US4

- [ ] T066 [US4] Extend RoutingService in `src/mcpworks_api/services/routing.py` with:
  - `execute_workflow(user_id, workflow_id, inputs, callback_url)` - hold credits, route to agent
  - `handle_agent_callback(execution_id, status, credits_used)` - commit or release credits

### Endpoints for US4

- [ ] T067 [US4] Add to `src/mcpworks_api/api/v1/services.py`:
  - POST /services/agent/execute/{workflowId} - execute workflow (FR-ROUTE-002)
- [ ] T068 [US4] Create `src/mcpworks_api/api/v1/webhooks.py` with:
  - POST /webhooks/agent - handle agent completion callbacks

### Integration for US4

- [ ] T069 [US4] Wire webhooks router into `src/mcpworks_api/api/v1/router.py`
- [ ] T070 [US4] Add tier check for agent service access (FR-ROUTE-005)
- [ ] T071 [US4] Add audit logging for workflow executions

**Checkpoint**: User Story 4 complete. Can execute workflows with credit accounting and callback handling.

---

## Phase 7: User Story 5 - Stripe Subscription Management (Priority: P3)

**Goal**: Enable subscription upgrades via Stripe Checkout with webhook handling

**Independent Test**: POST /v1/subscriptions → Stripe Checkout URL; webhook → tier updated

**Acceptance Scenarios** (from spec.md):
1. Free user → POST /subscriptions tier:starter → Checkout URL
2. checkout.session.completed webhook → tier updated, credits granted
3. invoice.payment_failed webhook → grace period started
4. DELETE /subscriptions/current → cancellation scheduled

### Models for US5

- [ ] T072 [P] [US5] Create Subscription model in `src/mcpworks_api/models/subscription.py` with fields from data-model.md (id, user_id, tier, status, stripe_subscription_id, stripe_customer_id, period timestamps, cancel_at_period_end)
- [ ] T073 [US5] Create Alembic migration for subscriptions table in `alembic/versions/006_create_subscriptions_table.py`

### Schemas for US5

- [ ] T074 [US5] Create subscription schemas in `src/mcpworks_api/schemas/subscription.py`: Subscription, CreateSubscriptionRequest, CheckoutSession, PurchaseCreditsRequest per openapi.yaml

### Services for US5

- [ ] T075 [US5] Create StripeService in `src/mcpworks_api/services/stripe.py` with:
  - `create_checkout_session(user_id, tier)` - create Stripe Checkout session (FR-BILL-001)
  - `create_credit_purchase_session(user_id, credits)` - one-time credit purchase (FR-BILL-005)
  - `handle_webhook(event)` - process Stripe webhooks per research.md decision 5
  - `cancel_subscription(user_id)` - cancel at period end
  - `grant_credits(user_id, tier)` - grant monthly credits based on tier (FR-BILL-003)

### Endpoints for US5

- [ ] T076 [US5] Create `src/mcpworks_api/api/v1/subscriptions.py` with:
  - GET /subscriptions - get current subscription
  - POST /subscriptions - create checkout session (FR-BILL-001)
  - DELETE /subscriptions/current - cancel subscription
  - POST /subscriptions/credits - purchase credits (FR-BILL-005)
- [ ] T077 [US5] Add to `src/mcpworks_api/api/v1/webhooks.py`:
  - POST /webhooks/stripe - handle Stripe webhooks (FR-BILL-004)

### Integration for US5

- [ ] T078 [US5] Wire subscriptions router into `src/mcpworks_api/api/v1/router.py`
- [ ] T079 [US5] Add Stripe webhook signature verification
- [ ] T080 [US5] Add idempotency handling for webhook events
- [ ] T081 [US5] Add audit logging for subscription events

**Checkpoint**: User Story 5 complete. Can subscribe via Stripe, receive credits, handle subscription lifecycle.

---

## Phase 8: User Story 6 - User Registration & API Key Management (Priority: P3)

**Goal**: Enable self-service user registration and API key management

**Independent Test**: POST /auth/register → user created, API key returned; POST /users/me/api-keys → new key

**Acceptance Scenarios** (from spec.md):
1. POST /auth/register → user created, verification email sent, API key returned
2. POST /users/me/api-keys → new key generated, shown once
3. DELETE /users/me/api-keys/{key_id} → key revoked
4. Key approaching expiry → notification (future: email)

### Schemas for US6

- [ ] T082 [US6] Create registration schemas in `src/mcpworks_api/schemas/auth.py`: RegisterRequest, RegisterResponse per openapi.yaml
- [ ] T083 [P] [US6] Create API key management schemas in `src/mcpworks_api/schemas/user.py`: CreateApiKeyRequest, ApiKeyCreated per openapi.yaml

### Services for US6

- [ ] T084 [US6] Create UserService in `src/mcpworks_api/services/user.py` with:
  - `register(email, password, name)` - create user, send verification email, create initial Credit record, create initial API key
  - `create_api_key(user_id, name, scopes, expires_at)` - generate new API key (FR-AUTH-005)
  - `list_api_keys(user_id)` - list user's API keys (prefix only)
  - `revoke_api_key(user_id, key_id)` - mark key as revoked
  - `get_profile(user_id)` - return user profile with credit balance

### Endpoints for US6

- [ ] T085 [US6] Add to `src/mcpworks_api/api/v1/auth.py`:
  - POST /auth/register - register new user
- [ ] T086 [US6] Add to `src/mcpworks_api/api/v1/users.py`:
  - GET /users/me/api-keys - list API keys
  - POST /users/me/api-keys - create new API key
  - DELETE /users/me/api-keys/{keyId} - revoke API key

### Integration for US6

- [ ] T087 [US6] Add email verification token generation and validation
- [ ] T088 [US6] Add initial credit grant (500 for free tier) on registration
- [ ] T089 [US6] Add audit logging for registration and API key events

**Checkpoint**: User Story 6 complete. Can register, manage API keys, receive initial credits.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

### Observability (FR-OBS-*)

- [ ] T090 [P] Add structured logging with correlation ID to all services (FR-OBS-001)
- [ ] T091 [P] Enhance /health endpoint to check database, Redis, math_service, agent_service status (FR-OBS-002)
- [ ] T092 [P] Add custom Prometheus metrics for credit_transactions_total, auth_attempts_total, service_health_status (FR-OBS-003)
- [ ] T093 Add credit transaction logging for audit purposes (FR-OBS-004)

### Error Handling

- [ ] T094 Create consistent error response format matching openapi.yaml Error schema
- [ ] T095 Add global exception handlers in `src/mcpworks_api/main.py`

### Configuration & Security

- [ ] T096 Add environment validation on startup (required keys present)
- [ ] T097 Add CORS configuration for production origins
- [ ] T098 Add request size limits and timeout configuration

### Documentation

- [ ] T099 Validate implementation against contracts/openapi.yaml
- [ ] T100 Run quickstart.md validation end-to-end

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) ─── BLOCKING ───┐
    ↓                                   │
    ├── Phase 3 (US1: Auth) ◄──────────┤
    ├── Phase 4 (US2: Credits) ◄───────┤
    │       ↓                           │
    ├── Phase 5 (US3: Math Routing) ◄──┤ (depends on US1 auth)
    ├── Phase 6 (US4: Agent Routing) ◄─┤ (depends on US1, US2)
    │       ↓                           │
    ├── Phase 7 (US5: Stripe) ◄────────┤ (depends on US2)
    └── Phase 8 (US6: Registration) ◄──┘ (depends on US1)
            ↓
      Phase 9 (Polish)
```

### User Story Dependencies

| Story | Depends On | Can Start After |
|-------|------------|-----------------|
| US1 (Auth) | Foundational | Phase 2 complete |
| US2 (Credits) | Foundational | Phase 2 complete |
| US3 (Math Routing) | US1 (auth middleware) | Phase 3 complete |
| US4 (Agent Routing) | US1, US2 (auth + credits) | Phase 3, 4 complete |
| US5 (Stripe) | US2 (credits to grant) | Phase 4 complete |
| US6 (Registration) | US1 (API key generation) | Phase 3 complete |

### Within Each User Story

1. Models → Migrations → Schemas
2. Services (business logic)
3. Endpoints (API layer)
4. Integration (wiring, middleware)

### Parallel Opportunities

**Setup Phase (all [P] tasks)**:
- T003, T004, T005, T006 can run in parallel

**Foundational Phase**:
- T010, T011, T012 (database, redis, exceptions) can run in parallel
- T016, T017, T018 (security) can run in parallel after database setup
- T019, T021, T023 (models) can run in parallel

**User Story 1 & 2** can start in parallel after Foundational:
- US1 T036-T039 models/schemas in parallel
- US2 T048-T051 models/schemas in parallel

**Polish Phase**:
- T090, T091, T092 (observability) can run in parallel

---

## Parallel Example: Foundational Phase

```bash
# Launch database/redis/exceptions in parallel:
Task T010: "Create database.py with async SQLAlchemy engine"
Task T011: "Create redis.py with async Redis connection pool"
Task T012: "Create exceptions.py with custom exception classes"

# Then launch security tasks in parallel:
Task T016: "Create security.py with Argon2id hasher"
Task T017: "Create generate_keys.py for ES256 key pair"
Task T018: "Add JWT functions to security.py"
```

## Parallel Example: User Story 1 Models

```bash
# Launch model and schema tasks in parallel:
Task T036: "Create APIKey model in models/user.py"
Task T038: "Create auth schemas in schemas/auth.py"
Task T039: "Create user schemas in schemas/user.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1 & 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL)
3. Complete Phase 3: User Story 1 (Auth)
4. Complete Phase 4: User Story 2 (Credits)
5. **STOP and VALIDATE**: Test auth + credits independently
6. Deploy/demo if ready - this is the **revenue-enabling MVP**

### Incremental Delivery

| Milestone | Stories | Value Delivered |
|-----------|---------|-----------------|
| MVP | US1 + US2 | Auth + Credits (monetization foundation) |
| +Routing | +US3 + US4 | Full gateway functionality |
| +Billing | +US5 | Automated subscriptions |
| +Self-Service | +US6 | User registration |
| Production | +Polish | Observability, hardening |

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Auth)
   - Developer B: User Story 2 (Credits)
3. After US1 complete:
   - Developer A: User Story 3 (Math Routing)
   - Developer C: User Story 6 (Registration)
4. After US2 complete:
   - Developer B: User Story 5 (Stripe)
5. After US1 + US2 complete:
   - Developer D: User Story 4 (Agent Routing)

---

## Task Summary

| Phase | Task Count | Parallel Tasks |
|-------|------------|----------------|
| Phase 1: Setup | 8 | 4 |
| Phase 2: Foundational | 27 | 10 |
| Phase 3: US1 Auth | 12 | 4 |
| Phase 4: US2 Credits | 10 | 3 |
| Phase 5: US3 Math | 7 | 2 |
| Phase 6: US4 Agent | 7 | 1 |
| Phase 7: US5 Stripe | 10 | 2 |
| Phase 8: US6 Registration | 8 | 2 |
| Phase 9: Polish | 11 | 4 |
| **Total** | **100** | **32** |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- MVP scope: US1 + US2 = Auth + Credits (enables monetization)

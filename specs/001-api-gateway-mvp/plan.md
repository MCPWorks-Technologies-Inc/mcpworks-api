# Implementation Plan: API Gateway MVP

**Branch**: `001-api-gateway-mvp` | **Date**: 2025-12-16 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-api-gateway-mvp/spec.md`

## Summary

Build mcpworks-api as a thin API gateway handling authentication (API keys → JWT), credit accounting (hold/commit/release), and routing to microservices (mcpworks-math, mcpworks-agent). Includes Stripe integration for subscriptions and observability via structured logging and Prometheus metrics.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, httpx, PyJWT, argon2-cffi, stripe
**Storage**: PostgreSQL 15+ (primary), Redis 7+ (rate limiting, sessions)
**Testing**: pytest, pytest-asyncio, httpx (test client), pytest-cov
**Target Platform**: Linux server (Docker containers on DigitalOcean)
**Project Type**: Single backend API service
**Performance Goals**: p95 < 200ms auth, p95 < 100ms credit ops, 100 concurrent users
**Constraints**: p95 < 500ms all endpoints, zero double-charging, 80%+ test coverage
**Scale/Scope**: 5-10 pilot users initially, designed for 10K users

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Plan Compliance | Status |
|-----------|-------------|-----------------|--------|
| **I. Spec-First** | Complete spec before code | Spec complete with 21 FRs, 10 SCs | PASS |
| **II. Token Efficiency** | 200-1000 tokens/operation | API responses return refs not full data; credit ops < 50 tokens | PASS |
| **II. Streaming** | SSE for long-running ops | Not applicable to gateway (routing only) | N/A |
| **III. Transaction Safety** | Hold/commit/release pattern | FR-CREDIT-001 through FR-CREDIT-006 define pattern | PASS |
| **III. Security** | Rate limiting, encryption, validation | FR-AUTH-006 (rate limit), ES256 JWT, Argon2id hashing | PASS |
| **IV. Provider Abstraction** | Swappable backends | Service routing via config; Stripe abstracted | PASS |
| **IV. Observability** | Structured logging, tracing, metrics | FR-OBS-001-004 define requirements | PASS |
| **V. API Contracts** | Semantic versioning, backward compat | OpenAPI spec generated; /v1/ prefix | PASS |
| **V. Test Coverage** | 80% unit, integration, E2E | pytest structure with contract/integration/unit | PASS |

**Gate Status**: PASSED - All applicable principles addressed

## Project Structure

### Documentation (this feature)

```text
specs/001-api-gateway-mvp/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI)
│   └── openapi.yaml
├── checklists/
│   └── requirements.md  # Spec validation checklist
└── tasks.md             # Phase 2 output (from /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── mcpworks_api/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Settings via pydantic-settings
│   ├── dependencies.py      # Dependency injection
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py    # Main v1 router
│   │       ├── auth.py      # /auth/* endpoints
│   │       ├── users.py     # /users/* endpoints
│   │       ├── credits.py   # /credits/* endpoints
│   │       ├── services.py  # /services/* endpoints
│   │       ├── subscriptions.py  # /subscriptions/* endpoints
│   │       └── webhooks.py  # Stripe webhooks
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py          # SQLAlchemy base, mixins
│   │   ├── user.py          # User, APIKey models
│   │   ├── credit.py        # Credit, CreditTransaction models
│   │   ├── subscription.py  # Subscription model
│   │   └── service.py       # Service registry model
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py          # Auth request/response schemas
│   │   ├── user.py          # User schemas
│   │   ├── credit.py        # Credit schemas
│   │   ├── subscription.py  # Subscription schemas
│   │   └── service.py       # Service schemas
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth.py          # JWT, API key logic
│   │   ├── credit.py        # Hold/commit/release logic
│   │   ├── stripe.py        # Stripe integration
│   │   ├── routing.py       # Service routing, health checks
│   │   └── user.py          # User management
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── database.py      # Async SQLAlchemy setup
│   │   ├── redis.py         # Redis connection
│   │   ├── security.py      # Password hashing, JWT utils
│   │   └── exceptions.py    # Custom exceptions
│   │
│   └── middleware/
│       ├── __init__.py
│       ├── auth.py          # JWT validation middleware
│       ├── rate_limit.py    # Redis-based rate limiting
│       ├── correlation.py   # X-Request-ID handling
│       └── metrics.py       # Prometheus middleware

tests/
├── conftest.py              # Fixtures, test DB setup
├── contract/
│   └── test_openapi.py      # Contract validation
├── integration/
│   ├── test_auth_flow.py
│   ├── test_credit_flow.py
│   └── test_service_routing.py
└── unit/
    ├── test_auth_service.py
    ├── test_credit_service.py
    └── test_stripe_service.py

alembic/
├── env.py
└── versions/

docker-compose.yml           # Local dev: API, Postgres, Redis
Dockerfile
pyproject.toml               # Project config, dependencies
```

**Structure Decision**: Single backend API project following FastAPI best practices. Separation of concerns via api/, models/, schemas/, services/, core/, middleware/ layers.

## Complexity Tracking

> No constitution violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |

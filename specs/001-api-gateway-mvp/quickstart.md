# Quickstart: API Gateway MVP

**Feature**: 001-api-gateway-mvp
**Date**: 2025-12-16

This guide helps developers get started with the API Gateway MVP implementation.

---

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose (for local development)
- Stripe account with test keys

---

## Local Development Setup

### 1. Clone and Setup Environment

```bash
cd mcpworks-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
```

### 2. Configure Environment Variables

Create `.env` file from template:

```bash
cp .env.example .env
```

Required variables:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/mcpworks

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT (ES256 keys - generate with scripts/generate_keys.py)
JWT_PRIVATE_KEY_PATH=./keys/private.pem
JWT_PUBLIC_KEY_PATH=./keys/public.pem
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER=price_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_ENTERPRISE=price_...

# Backend Services
MATH_SERVICE_URL=http://localhost:8001
AGENT_SERVICE_URL=http://localhost:8002

# Observability
LOG_LEVEL=DEBUG
PROMETHEUS_ENABLED=true
```

### 3. Start Infrastructure

```bash
docker-compose up -d postgres redis
```

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Seed Initial Data

```bash
python -m mcpworks_api.scripts.seed_services
```

This creates the initial service registry:
- `math` - mcpworks-math (free, all tiers)
- `agent` - mcpworks-agent (credits, starter+)

### 6. Start the Server

```bash
uvicorn mcpworks_api.main:app --reload --port 8000
```

API available at: http://localhost:8000/v1

---

## Quick Verification

### Health Check

```bash
curl http://localhost:8000/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "math_service": "ok",
    "agent_service": "ok"
  }
}
```

### Register Test User

```bash
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "testpass123", "name": "Test User"}'
```

Response includes your first API key (save it!):
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "test@example.com",
  "api_key": "sk_test_k1_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456",
  "message": "Verification email sent"
}
```

### Exchange API Key for JWT

```bash
curl -X POST http://localhost:8000/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key": "sk_test_k1_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456"}'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJFUzI1NiIs...",
  "refresh_token": "refresh_abc123...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### Check Credit Balance

```bash
curl http://localhost:8000/v1/credits \
  -H "Authorization: Bearer eyJhbGciOiJFUzI1NiIs..."
```

Free tier starts with 500 credits:
```json
{
  "available_balance": 500.00,
  "held_balance": 0.00,
  "total_balance": 500.00,
  "lifetime_earned": 500.00,
  "lifetime_spent": 0.00
}
```

### Test Math Service Routing

```bash
curl -X POST http://localhost:8000/v1/services/math/verify \
  -H "Authorization: Bearer eyJhbGciOiJFUzI1NiIs..." \
  -H "Content-Type: application/json" \
  -d '{"problem": "What is 2 + 2?", "show_work": true}'
```

---

## Development Workflow

### Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=src --cov-report=html

# Specific test categories
pytest tests/unit/ -v
pytest tests/integration/ -v
```

### Code Quality

```bash
# Type checking
mypy src/

# Formatting
black src/ tests/
isort src/ tests/

# Linting
ruff check src/ tests/
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Add xyz table"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

---

## API Overview

### Authentication Flow

```
1. Register: POST /v1/auth/register → Get initial API key
2. Token:    POST /v1/auth/token   → Exchange API key for JWT
3. Use:      GET /v1/users/me      → Authenticated request with JWT
4. Refresh:  POST /v1/auth/refresh → Get new access token
```

### Credit Operations

```
1. Hold:    POST /v1/credits/hold    → Reserve credits before operation
2. Commit:  POST /v1/credits/commit  → Charge credits (success)
   OR
   Release: POST /v1/credits/release → Return credits (failure/cancel)
```

### Service Routing

```
Math (free):  POST /v1/services/math/{operation}
Agent (paid): POST /v1/services/agent/execute/{workflowId}
```

---

## Testing with Stripe

### Setup Stripe CLI

```bash
stripe listen --forward-to localhost:8000/v1/webhooks/stripe
```

### Test Subscription Flow

```bash
# 1. Create checkout session
curl -X POST http://localhost:8000/v1/subscriptions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tier": "starter"}'

# 2. Complete checkout in browser (use test card 4242424242424242)

# 3. Stripe webhook updates tier and grants credits
```

---

## Common Issues

### Database Connection

If you see `connection refused`:
```bash
docker-compose up -d postgres
# Wait for postgres to be ready
docker-compose logs -f postgres
```

### Redis Connection

If rate limiting doesn't work:
```bash
docker-compose up -d redis
redis-cli ping  # Should return PONG
```

### JWT Signature Error

Regenerate keys if signature fails:
```bash
python scripts/generate_keys.py
```

### Service Unavailable (503)

Backend service not running:
```bash
# Check health of math service
curl http://localhost:8001/health

# Start mock services for local dev
python -m mcpworks_api.scripts.mock_services
```

---

## Next Steps

1. **Read the spec**: `specs/001-api-gateway-mvp/spec.md`
2. **Review data model**: `specs/001-api-gateway-mvp/data-model.md`
3. **Check research decisions**: `specs/001-api-gateway-mvp/research.md`
4. **Explore OpenAPI**: `specs/001-api-gateway-mvp/contracts/openapi.yaml`

---

## Key Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Project dependencies and config |
| `alembic.ini` | Database migration config |
| `.env` | Environment variables |
| `src/mcpworks_api/config.py` | Application settings |

---

## Architecture Reference

```
src/mcpworks_api/
├── main.py              # FastAPI entry point
├── config.py            # Settings (pydantic-settings)
├── dependencies.py      # DI providers
├── api/v1/              # Route handlers
├── models/              # SQLAlchemy models
├── schemas/             # Pydantic schemas
├── services/            # Business logic
├── core/                # Database, Redis, security
└── middleware/          # Auth, rate limit, metrics
```

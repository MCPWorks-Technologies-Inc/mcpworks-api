# A0 Consolidation Guide

**Version:** 1.0.0
**Created:** 2026-02-09
**Purpose:** Map existing mcpworks-api codebase to A0 namespace architecture

---

## Overview

This guide shows how to consolidate the existing mcpworks-api implementation with the new A0 namespace function platform specifications. The existing codebase provides **75-80% of the foundation** - this document identifies what to keep, what to extend, and what to add.

**Key Principle:** The existing SPEC.md (2,395 lines) remains the authoritative reference for implemented components. The new A0 specifications extend and complement it.

---

## Document Hierarchy

```
docs/implementation/
├── A0-SYSTEM-SPECIFICATION.md      # Master spec (read first)
├── CONSOLIDATION-GUIDE.md          # This file
├── gateway-architecture-specification.md
├── database-models-specification.md
└── code-sandbox-specification.md

Root level (DO NOT MODIFY):
├── SPEC.md                          # Original spec (keep as-is)
└── specs/001-api-gateway-mvp/       # Original feature specs
```

---

## Existing Components to KEEP (As-Is)

These components are fully aligned with A0 and require no changes:

### Core Infrastructure

| File | Lines | Status | Notes |
|------|-------|--------|-------|
| `core/database.py` | ~80 | ✅ Keep | Async SQLAlchemy setup |
| `core/redis.py` | ~50 | ✅ Keep | Redis connection pool |
| `core/security.py` | ~100 | ✅ Keep | Password hashing, JWT |
| `core/exceptions.py` | ~150 | ✅ Keep | Exception hierarchy |
| `config.py` | ~100 | ✅ Keep | Pydantic settings |

### Models (Direct Reuse)

| File | A0 Role | Notes |
|------|---------|-------|
| `models/base.py` | Base model | TimestampMixin, UUIDMixin - keep |
| `models/user.py` | Account | Rename to `account.py` in A0 |
| `models/api_key.py` | API Keys | Add `namespace_id` FK for scoping |
| `models/subscription.py` | Subscription | Already tier-based |
| `models/usage.py` | UsageRecord | Track executions per billing period |
| `models/audit_log.py` | AuditLog | Already SOC 2 ready |

### Services (Direct Reuse)

| File | A0 Role | Notes |
|------|---------|-------|
| `services/auth.py` | Auth | Keep API key validation |
| `services/usage.py` | Usage | Track/check execution limits |
| `services/stripe.py` | Billing | Keep Stripe integration |
| `services/router.py` | Routing | Adapt for backend dispatch |

### Middleware (Direct Reuse)

| File | A0 Role | Notes |
|------|---------|-------|
| `middleware/rate_limit.py` | Rate Limiting | Already Redis-based sliding window |
| `middleware/correlation.py` | Request ID | Keep for tracing |
| `middleware/metrics.py` | Metrics | Keep for observability |
| `middleware/error_handler.py` | Errors | Keep JSON error responses |

---

## Existing Components to EXTEND

These components need additions but core logic remains:

### 1. User Model → Account Model

**File:** `models/user.py`
**Action:** Rename to `models/account.py`, add namespace relationship

```python
# EXISTING (keep)
class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID]
    email: Mapped[str]
    password_hash: Mapped[str]
    tier: Mapped[str]  # free, founder, founder_pro, enterprise

# ADD relationship
    namespaces: Mapped[list["Namespace"]] = relationship(
        "Namespace", back_populates="account", cascade="all, delete-orphan"
    )
```

### 2. Service Model → Extend for Functions

**File:** `models/service.py`
**Current:** Tracks external services (agent, activepieces)
**Action:** Keep for backend services, add new Function model separately

```python
# EXISTING (keep as-is for backend routing)
class Service(Base):
    __tablename__ = "services"
    id: Mapped[uuid.UUID]
    name: Mapped[str]
    url: Mapped[str]
    tier_required: Mapped[str]

# NEW (add in separate file)
class Function(Base):  # This is different from Service
    __tablename__ = "functions"
    # See database-models-specification.md
```

### 3. Execution Model → Add Function Context

**File:** `models/execution.py`
**Action:** Add `function_version_id` FK, rename `workflow_id` to `function_id`

```python
# EXISTING
class Execution(Base):
    workflow_id: Mapped[str]  # RENAME to function_id

# ADD
    function_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("function_versions.id"), nullable=True
    )
    namespace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("namespaces.id")
    )
```

### 4. API Key Model → Add Namespace Scoping

**File:** `models/api_key.py`
**Action:** Add optional `namespace_id` for scoped keys

```python
# EXISTING (keep)
class APIKey(Base):
    user_id: Mapped[uuid.UUID]
    key_hash: Mapped[str]

# ADD
    namespace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("namespaces.id"), nullable=True
    )
    # null = account-level key (all namespaces)
    # set = namespace-scoped key
```

---

## New Components to ADD

These do not exist and must be created per A0 specs:

### 1. Namespace Model (NEW)

**Create:** `models/namespace.py`
**Spec:** `database-models-specification.md` Section 2.1

```python
class Namespace(Base):
    __tablename__ = "namespaces"
    id: Mapped[uuid.UUID]
    account_id: Mapped[uuid.UUID]  # FK to accounts
    name: Mapped[str]              # Unique subdomain
    display_name: Mapped[str]
    network_whitelist: Mapped[list[str]]  # JSONB
```

### 2. Function + FunctionVersion Models (NEW)

**Create:** `models/function.py`, `models/function_version.py`
**Spec:** `database-models-specification.md` Sections 2.3, 2.4

### 3. SecurityEvent Model (NEW)

**Create:** `models/security_event.py`
**Spec:** `database-models-specification.md` Section 2.7
**Note:** Different from existing `audit_log.py` - tracks security incidents

### 4. Webhook Model (NEW)

**Create:** `models/webhook.py`
**Spec:** `database-models-specification.md` Section 2.8

### 5. Subdomain Middleware (NEW)

**Create:** `middleware/subdomain.py`
**Spec:** `gateway-architecture-specification.md` Section 2.1

```python
class SubdomainMiddleware(BaseHTTPMiddleware):
    """Extract namespace and mode from subdomain."""
    # {namespace}.create.mcpworks.io
    # {namespace}.run.mcpworks.io
```

### 6. Billing Middleware (NEW)

**Create:** `middleware/billing.py`
**Spec:** `gateway-architecture-specification.md` Section 2.4

### 7. MCP Protocol Layer (NEW)

**Create:** `mcp/` directory
**Spec:** `gateway-architecture-specification.md` Section 3

```
mcp/
├── __init__.py
├── protocol.py      # JSON-RPC 2.0 helpers
├── create_handler.py  # 10 management tools
├── run_handler.py     # Dynamic function tools
└── router.py          # Route to handlers
```

### 8. Sandbox Backend (NEW)

**Create:** `backends/` directory
**Spec:** `code-sandbox-specification.md`

```
backends/
├── __init__.py
├── base.py          # Abstract Backend class
└── sandbox.py       # Code Sandbox implementation
```

### 9. Namespace/Function Services (NEW)

**Create:** `services/namespace_service.py`, `services/function_service.py`
**Spec:** `gateway-architecture-specification.md` Section 3.2

---

## Database Migration Strategy

### Existing Migrations (Keep)

```
alembic/versions/
├── 20251217_000001_initial_schema.py  # Users, APIKeys, Usage, Subscriptions
└── 20251217_000002_add_executions_table.py  # Executions
```

### New Migration (Add)

**Create:** `alembic/versions/YYYYMMDD_000003_add_namespace_tables.py`

```python
def upgrade():
    # 1. Rename users -> accounts (optional, can keep as users)
    # 2. Create namespaces table
    # 3. Create services table (namespace-scoped)
    # 4. Create functions table
    # 5. Create function_versions table
    # 6. Create security_events table
    # 7. Create webhooks table
    # 8. Add namespace_id FK to api_keys (nullable)
    # 9. Add function_version_id FK to executions
    # 10. Create partitioned execution history (optional)
```

**See:** `database-models-specification.md` Section 5 for complete migration

---

## API Endpoint Mapping

### Existing Endpoints (Keep)

| Endpoint | A0 Role | Notes |
|----------|---------|-------|
| `POST /v1/auth/login` | Login | Keep |
| `POST /v1/auth/register` | Register | Keep |
| `GET /v1/users/me` | Account info | Rename path to `/v1/accounts/me` |
| `GET /v1/usage` | Get usage | Returns executions count/limit |
| `GET /v1/subscriptions` | List subs | Keep |
| `POST /v1/subscriptions` | Create sub | Keep |

### New Endpoints (Add)

| Endpoint | Purpose | Spec |
|----------|---------|------|
| `POST /mcp` | MCP protocol | gateway-architecture-specification.md |
| `GET /v1/namespaces` | List namespaces | A0-SYSTEM-SPECIFICATION.md |
| `POST /v1/namespaces` | Create namespace | A0-SYSTEM-SPECIFICATION.md |
| `PATCH /v1/namespaces/{name}` | Update namespace | A0-SYSTEM-SPECIFICATION.md |
| `GET /v1/api-keys` | List API keys | A0-SYSTEM-SPECIFICATION.md |
| `POST /v1/api-keys` | Create API key | A0-SYSTEM-SPECIFICATION.md |
| `DELETE /v1/api-keys/{id}` | Revoke key | A0-SYSTEM-SPECIFICATION.md |
| `GET /v1/usage` | Usage stats | A0-SYSTEM-SPECIFICATION.md |
| `GET /v1/audit/logs` | Audit logs | A0-SYSTEM-SPECIFICATION.md |
| `POST /graphql` | GraphQL | A0-SYSTEM-SPECIFICATION.md |

---

## Terminology Migration

The A0 architecture uses different terminology. Update throughout:

| Old Term | New Term | Scope |
|----------|----------|-------|
| User | Account | Database, API |
| Workflow | Function | Everywhere |
| workflow_id | function_id | Executions |
| - | Namespace | New concept |
| - | Service | Namespace-scoped grouping |
| - | FunctionVersion | Immutable snapshots |

---

## File Structure After Consolidation

```
src/mcpworks_api/
├── main.py                 # EXTEND: Add MCP router
├── config.py               # KEEP
├── dependencies.py         # KEEP
│
├── middleware/
│   ├── __init__.py
│   ├── subdomain.py        # NEW
│   ├── auth.py             # EXTEND (was in services/)
│   ├── rate_limit.py       # KEEP
│   ├── billing.py          # NEW
│   ├── correlation.py      # KEEP
│   ├── metrics.py          # KEEP
│   └── error_handler.py    # KEEP
│
├── mcp/                    # NEW DIRECTORY
│   ├── __init__.py
│   ├── protocol.py
│   ├── create_handler.py
│   ├── run_handler.py
│   └── router.py
│
├── backends/               # NEW DIRECTORY
│   ├── __init__.py
│   ├── base.py
│   └── sandbox.py
│
├── models/
│   ├── __init__.py         # EXTEND: Export new models
│   ├── base.py             # KEEP
│   ├── account.py          # RENAME from user.py
│   ├── api_key.py          # EXTEND
│   ├── namespace.py        # NEW
│   ├── service.py          # EXTEND (namespace-scoped)
│   ├── function.py         # NEW
│   ├── function_version.py # NEW
│   ├── execution.py        # EXTEND
│   ├── subscription.py     # KEEP
│   ├── usage.py            # Usage records per billing period
│   ├── audit_log.py        # KEEP
│   ├── security_event.py   # NEW
│   └── webhook.py          # NEW
│
├── schemas/                # EXTEND with new schemas
│   ├── __init__.py
│   ├── common.py           # KEEP
│   ├── auth.py             # KEEP
│   ├── user.py             # RENAME to account.py
│   ├── namespace.py        # NEW
│   ├── function.py         # NEW
│   ├── service.py          # EXTEND
│   ├── usage.py            # Usage tracking schemas
│   └── subscription.py     # KEEP
│
├── services/
│   ├── __init__.py
│   ├── auth.py             # KEEP
│   ├── usage.py            # Usage tracking
│   ├── stripe.py           # KEEP
│   ├── router.py           # EXTEND for backends
│   ├── execution.py        # EXTEND
│   ├── namespace_service.py # NEW
│   └── function_service.py  # NEW
│
├── api/v1/
│   ├── __init__.py
│   ├── health.py           # KEEP
│   ├── auth.py             # KEEP
│   ├── users.py            # RENAME to accounts.py
│   ├── namespaces.py       # NEW
│   ├── usage.py            # Usage tracking
│   ├── subscriptions.py    # KEEP
│   ├── services.py         # EXTEND
│   └── api_keys.py         # NEW
│
└── core/
    ├── __init__.py
    ├── database.py         # KEEP
    ├── redis.py            # KEEP
    ├── security.py         # KEEP
    └── exceptions.py       # EXTEND with new exceptions

config/                     # NEW DIRECTORY (at repo root)
├── sandbox.cfg             # nsjail configuration
└── seccomp-allowlist.policy # Syscall filter
```

---

## Implementation Phases (Aligned with A0)

### Phase 1: Core Gateway (Week 1-2)

1. ✅ Keep existing FastAPI skeleton
2. ADD `middleware/subdomain.py`
3. CREATE new Alembic migration for namespace tables
4. ADD `middleware/billing.py`
5. EXTEND health check for new components

### Phase 2: Management MCP Server (Week 2-3)

1. CREATE `mcp/` directory structure
2. CREATE `mcp/protocol.py` (JSON-RPC 2.0)
3. CREATE `mcp/create_handler.py` (10 tools)
4. CREATE `services/namespace_service.py`
5. CREATE `services/function_service.py`

### Phase 3: Code Sandbox Backend (Week 3-4)

1. CREATE `backends/` directory
2. CREATE `backends/sandbox.py`
3. INSTALL nsjail + configure
4. CREATE `config/sandbox.cfg`
5. CREATE `config/seccomp-allowlist.policy`

### Phase 4: Execution MCP Server (Week 4-5)

1. CREATE `mcp/run_handler.py`
2. EXTEND `services/execution.py` for functions
3. EXTEND `services/router.py` for backend dispatch
4. ADD usage metering per execution

### Phase 5: Infrastructure & Security (Week 5-6)

1. Configure Cloudflare Tunnel
2. Set up wildcard DNS
3. Security audit of sandbox
4. ADD REST endpoints for namespaces
5. OPTIONAL: GraphQL endpoint

### Phase 6: Integration & Polish (Week 6-8)

1. End-to-end testing
2. Create demo namespace
3. Documentation for pilots
4. Onboard 5-10 pilot users

---

## Validation Checklist

Before marking consolidation complete:

- [ ] All existing tests still pass
- [ ] New namespace tables created via migration
- [ ] User → Account rename applied (or documented as future)
- [ ] API key scoping added
- [ ] Subdomain middleware extracting namespace/mode
- [ ] MCP protocol layer responding to JSON-RPC
- [ ] At least one management tool working (list_namespaces)
- [ ] Sandbox executing simple Python code
- [ ] Usage tracking working for executions

---

## References

- **Original Spec:** `/SPEC.md` (2,395 lines) - Authoritative for existing components
- **Feature Spec:** `/specs/001-api-gateway-mvp/spec.md` - Original user stories
- **Constitution:** `/docs/implementation/specs/CONSTITUTION.md` - Development principles
- **A0 Master:** `/docs/implementation/A0-SYSTEM-SPECIFICATION.md` - New architecture
- **Gateway:** `/docs/implementation/gateway-architecture-specification.md`
- **Database:** `/docs/implementation/database-models-specification.md`
- **Sandbox:** `/docs/implementation/code-sandbox-specification.md`

---

## Summary

**What exists:** 75-80% of foundation (auth, usage tracking, billing, middleware, core)
**What to extend:** User→Account, APIKey scoping, Execution→Function context
**What to add:** Namespaces, Functions, FunctionVersions, MCP layer, Sandbox backend

The existing codebase is well-structured and follows the same patterns. The A0 consolidation adds namespace-scoped function management while preserving all existing account/subscription functionality.

# A0 System Specification — MCPWorks Namespace Function Platform

**Version:** 1.0.0
**Created:** 2026-02-09
**Status:** Active — Ready for Implementation
**Target:** Week 1-8 of A0 milestone

---

## Executive Summary

This is the **master specification** for the MCPWorks A0 implementation. It consolidates all component specifications into a single reference document.

**A0 Deliverable:** Working namespace function platform with Code Sandbox backend, accessible via `{namespace}.create.mcpworks.io` and `{namespace}.run.mcpworks.io`.

---

## Component Specifications

| Component | Specification | Lines | Status |
|-----------|---------------|-------|--------|
| **Gateway Architecture** | [gateway-architecture-specification.md](./gateway-architecture-specification.md) | ~800 | ✅ Complete |
| **Database Models** | [database-models-specification.md](./database-models-specification.md) | 2,562 | ✅ Complete |
| **Code Sandbox** | [code-sandbox-specification.md](./code-sandbox-specification.md) | ~2,000 | ✅ Complete |

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  AI Assistant (Claude Code / Copilot / Codex)                                │
│  .mcp.json: { "url": "https://acme.create.mcpworks.io", "headers": {...} }   │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │ HTTPS + Authorization header
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Cloudflare Tunnel                                                           │
│  *.create.mcpworks.io → localhost:8000                                       │
│  *.run.mcpworks.io → localhost:8000                                          │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Gateway (FastAPI) - SINGLE ENTRYPOINT                                       │
│                                                                              │
│  1. Parse subdomain → extract namespace + endpoint type (create/run)         │
│  2. Authenticate → validate API key from Authorization header                │
│  3. Authorize → check key scope (create, run, admin)                         │
│  4. Rate limit → check account limits                                        │
│  5. Route → dispatch to appropriate MCP handler                              │
│                                                                              │
│  ┌─────────────────────────────┐   ┌─────────────────────────────────┐       │
│  │  Create MCP Handler         │   │  Run MCP Handler                │       │
│  │  (if subdomain = *.create)  │   │  (if subdomain = *.run)         │       │
│  │                             │   │                                 │       │
│  │  • make_namespace           │   │  • Dynamic tools from DB        │       │
│  │  • list_namespaces          │   │  • service.function notation    │       │
│  │  • make_service             │   │  • Invoke function              │       │
│  │  • list_services            │   │  • Return result + metadata     │       │
│  │  • delete_service           │   │                                 │       │
│  │  • make_function            │   │                                 │       │
│  │  • update_function          │   │                                 │       │
│  │  • delete_function          │   │                                 │       │
│  │  • list_functions           │   │                                 │       │
│  │  • describe_function        │   │                                 │       │
│  └─────────────────────────────┘   └──────────────┬──────────────────┘       │
│                                                    │                          │
└────────────────────────────────────────────────────┼──────────────────────────┘
                                                     │
                                                     ▼
                                    ┌───────────────────────────────────┐
                                    │  Function Backends                │
                                    │                                   │
                                    │  ┌─────────────────────────────┐  │
                                    │  │ Code Sandbox (A0)           │  │
                                    │  │ • nsjail isolation          │  │
                                    │  │ • Seccomp ALLOWLIST         │  │
                                    │  │ • Egress proxy (whitelist)  │  │
                                    │  │ • cgroups v2 limits         │  │
                                    │  └─────────────────────────────┘  │
                                    │                                   │
                                    │  ┌─────────────────────────────┐  │
                                    │  │ Activepieces (A1)           │  │
                                    │  │ • Visual workflows          │  │
                                    │  │ • 150+ integrations         │  │
                                    │  └─────────────────────────────┘  │
                                    │                                   │
                                    │  ┌─────────────────────────────┐  │
                                    │  │ nanobot.ai (A2)             │  │
                                    │  │ • TBD                       │  │
                                    │  └─────────────────────────────┘  │
                                    │                                   │
                                    │  ┌─────────────────────────────┐  │
                                    │  │ GitHub Repo (A3)            │  │
                                    │  │ • MCPWorks Framework        │  │
                                    │  └─────────────────────────────┘  │
                                    └───────────────────────────────────┘
```

**Authentication Flow:**

```
1. Client sends request with header:
   Authorization: Bearer mcpw_abc123...

2. Gateway middleware chain:
   ├── subdomain.py → extract namespace + endpoint type
   ├── auth.py → validate API key, attach account to request
   ├── rate_limit.py → check limits, reject if exceeded
   └── billing.py → check quota, track usage

3. If auth passes → route to MCP handler
   If auth fails → return 401/403 immediately
```

---

## Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Single Entrypoint** | Gateway-first | Authenticate before routing to handlers |
| **Subdomain Pattern** | `{ns}.{create\|run}.mcpworks.io` | Clean separation of concerns |
| **Tool Naming** | Dot notation (`service.function`) | Modern, readable, unique |
| **Function Versioning** | Immutable versions | Audit trail, rollback capability |
| **Network Control** | Per-tier whitelist | Tier-based security |
| **Sandbox Isolation** | nsjail + seccomp ALLOWLIST | Defense in depth |
| **Monorepo** | Single repository | LLM-friendly development |
| **SOC 2 Prep** | Audit tables from day one | Future compliance ready |

---

## Data Model Summary

```
Account (existing)
├── Namespace[]
│   ├── Service[]
│   │   └── Function[]
│   │       └── FunctionVersion[] (immutable)
│   └── network_whitelist[]
├── APIKey[]
├── Subscription
└── UsageRecord (per billing period)

Supporting Tables:
├── Execution (partitioned by month)
├── AuditLog (SOC 2)
├── SecurityEvent (SOC 2)
└── Webhook
```

---

## API Surface

### MCP Protocol (Primary)

**Create Endpoint:** `POST https://{namespace}.create.mcpworks.io/mcp`

| Tool | Description |
|------|-------------|
| `make_namespace` | Create a new namespace |
| `list_namespaces` | List all namespaces |
| `make_service` | Create a service |
| `list_services` | List services |
| `delete_service` | Delete service and functions |
| `make_function` | Create a function |
| `update_function` | Update (creates new version) |
| `delete_function` | Delete a function |
| `list_functions` | List functions in service |
| `describe_function` | Get function + version history |

**Run Endpoint:** `POST https://{namespace}.run.mcpworks.io/mcp`

| Tool | Description |
|------|-------------|
| `{service}.{function}` | Dynamic tools from database |

### REST API (Admin/Dashboard)

```
POST   /v1/accounts           Create account
GET    /v1/accounts/me        Get current account
POST   /v1/api-keys           Create API key
DELETE /v1/api-keys/{id}      Revoke API key
GET    /v1/namespaces         List namespaces
POST   /v1/namespaces         Create namespace
PATCH  /v1/namespaces/{name}  Update namespace (whitelist)
GET    /v1/usage              Get usage stats
GET    /v1/audit/logs         Get audit logs
```

### GraphQL API

```
POST   /graphql               Full schema access
```

---

## Tier Limits

| Limit | Free | Founder | Founder Pro | Enterprise |
|-------|------|---------|-------------|------------|
| **Price** | $0 | $29/mo | $59/mo | $129+/mo |
| **Namespaces** | 1 | 3 | 10 | Unlimited |
| **Functions** | 5 | 25 | 100 | Unlimited |
| **Executions/mo** | 500 | 10,000 | 50,000 | Unlimited |
| **Execution time** | 10s | 30s | 60s | 300s |
| **Memory** | 128MB | 256MB | 512MB | 2GB |
| **Network hosts** | ❌ | 5 | 25 | Unlimited |
| **Versions kept** | 10 | 50 | 100 | Unlimited |
| **Concurrent exec** | 2 | 10 | 25 | 100 |

---

## Security Model

### Defense in Depth

```
Layer 1: Gateway
├── API key authentication (bcrypt hashed)
├── Rate limiting (sliding window)
├── Input validation (size, schema)
└── Quota enforcement

Layer 2: Process Isolation (nsjail)
├── PID namespace (isolated process tree)
├── User namespace (unprivileged)
├── IPC namespace (isolated IPC)
└── UTS namespace (isolated hostname)

Layer 3: Filesystem Isolation
├── Mount namespace (isolated mounts)
├── Read-only root filesystem
├── tmpfs for /sandbox
└── No access to host paths

Layer 4: Network Isolation
├── Network namespace (isolated)
├── Egress proxy only
├── Per-tier whitelist enforcement
└── Blocked metadata services

Layer 5: Resource Limits (cgroups v2)
├── Memory limits
├── CPU limits
├── PID limits
└── Aggregate host limits

Layer 6: Syscall Filtering (seccomp)
├── ALLOWLIST (not blocklist)
├── 200+ dangerous syscalls blocked
└── Default deny for unknowns
```

### Critical Security Requirements (🔴 Before Pilots)

- [ ] Seccomp ALLOWLIST operational
- [ ] All namespaces enabled
- [ ] Aggregate cgroup limits set
- [ ] API key hashing (bcrypt)
- [ ] Rate limiting per account
- [ ] Egress proxy enforces whitelist
- [ ] Input validation on all endpoints
- [ ] Audit logging operational

---

## Implementation Phases

### Phase 1: Core Gateway (Week 1-2)
- FastAPI skeleton with middleware chain
- PostgreSQL schema migrations
- Redis connection for rate limiting
- API key authentication
- Health check endpoint

### Phase 2: Management MCP Server (Week 2-3)
- MCP protocol (JSON-RPC 2.0)
- All 10 management tools
- Function versioning with restore
- Namespace routing

### Phase 3: Code Sandbox Backend (Week 3-4)
- nsjail installation + configuration
- Seccomp allowlist policy
- Egress proxy with whitelist
- Execution wrapper

### Phase 4: Execution MCP Server (Week 4-5)
- Dynamic tool generation
- Backend dispatch
- Response metadata
- Usage metering

### Phase 5: Infrastructure & Security (Week 5-6)
- Cloudflare Tunnel setup
- Wildcard DNS
- Security audit
- REST + GraphQL APIs

### Phase 6: Integration & Polish (Week 6-8)
- End-to-end testing
- Demo namespace
- Pilot documentation
- Onboard 5-10 pilots

---

## Success Metrics (Week 8)

| Metric | Target |
|--------|--------|
| Pilot users | 5-10 |
| Functions created | 50+ |
| Successful executions | 500+ |
| P95 latency | <3s |
| Error rate | <5% |
| Security incidents | 0 |
| Uptime | 95%+ |

---

## File Structure

```
mcpworks-api/
├── docs/implementation/
│   ├── A0-SYSTEM-SPECIFICATION.md        # This file (master spec)
│   ├── gateway-architecture-specification.md
│   ├── database-models-specification.md
│   └── code-sandbox-specification.md
│
├── src/mcpworks_api/
│   ├── main.py
│   ├── config.py
│   ├── middleware/
│   │   ├── subdomain.py              # NEW
│   │   ├── auth.py                   # ENHANCE
│   │   ├── rate_limit.py             # EXISTS
│   │   └── billing.py                # NEW
│   ├── mcp/                          # NEW
│   │   ├── protocol.py
│   │   ├── create_handler.py
│   │   ├── run_handler.py
│   │   └── router.py
│   ├── backends/                     # NEW
│   │   ├── base.py
│   │   └── sandbox.py
│   ├── models/                       # EXTEND
│   │   ├── namespace.py              # NEW
│   │   ├── function.py               # NEW
│   │   ├── function_version.py       # NEW
│   │   └── ...
│   ├── schemas/                      # EXTEND
│   ├── services/                     # NEW
│   │   ├── namespace_service.py
│   │   └── function_service.py
│   └── core/                         # EXISTS
│
├── config/
│   ├── sandbox.cfg                   # nsjail config
│   └── seccomp-allowlist.policy
│
├── alembic/versions/
│   └── YYYYMMDD_add_namespace_tables.py
│
└── tests/
    ├── unit/
    ├── integration/
    └── security/
```

---

## Quick Start for Implementation

1. **Read the specs in order:**
   - This document (overview)
   - [Database Models](./database-models-specification.md) (data layer)
   - [Gateway Architecture](./gateway-architecture-specification.md) (API layer)
   - [Code Sandbox](./code-sandbox-specification.md) (execution layer)

2. **Start with Phase 1:**
   - Add SubdomainMiddleware
   - Create Alembic migration for new tables
   - Test middleware chain

3. **Build up through phases:**
   - Each phase builds on the previous
   - Test thoroughly before moving on
   - Security checks at each stage

---

## Related Documents

**In mcpworks-internals:**
- [A0-IMPLEMENTATION-PLAN.md](../../../mcpworks-internals/docs/implementation/A0-IMPLEMENTATION-PLAN.md) - Original implementation plan
- [STRATEGY.md](../../../mcpworks-internals/STRATEGY.md) - Business strategy
- [FINANCIAL-PLAN.md](../../../mcpworks-internals/FINANCIAL-PLAN.md) - Financial projections

---

## Changelog

**v1.0.0 (2026-02-09):**
- Initial master specification
- Consolidated from 3 component specs
- Ready for A0 implementation

# MCPWorks API Specification

**Version:** 2.0.0
**Status:** Ready for Implementation
**Last Updated:** 2026-02-10

> **A0 Architecture Migration Note:**
> This specification is transitioning from "workflows" terminology to the new **namespace-based function architecture**.
> - **Old model:** Workflows → Activepieces
> - **New model:** Namespaces → Services → Functions → Backends (Code Sandbox, Activepieces, nanobot.ai, GitHub Repo)
>
> See [database-models-specification.md](docs/implementation/database-models-specification.md) for the A0 data models.
> See [namespace-architecture.md](../mcpworks-internals/docs/implementation/namespace-architecture.md) for the complete A0 architecture.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Data Models](#data-models)
4. [API Endpoints](#api-endpoints)
5. [Usage Tracking](#usage-tracking)
6. [Activepieces Integration](#activepieces-integration)
7. [Authentication & Security](#authentication--security)
8. [Pricing & Subscriptions](#pricing--subscriptions)
9. [Error Handling](#error-handling)
10. [Monitoring & Observability](#monitoring--observability)
11. [Deployment](#deployment)
12. [Testing Strategy](#testing-strategy)
13. [Implementation Roadmap](#implementation-roadmap)
14. [Related Documentation](#related-documentation)

---

## Overview

### Purpose

The **mcpworks-api** is the backend REST API service that powers the mcpworks namespace-based function hosting platform. AI assistants connect directly via HTTPS to namespace endpoints where they can create and execute functions backed by multiple backends.

### Key Responsibilities

- **User & Account Management**: Registration, authentication, API key management
- **Usage Tracking**: Monitor execution counts against subscription tier limits
- **Namespace & Function Management**: CRUD operations for namespaces, services, and functions
- **Execution Orchestration**: Route function execution to appropriate backend (Code Sandbox, Activepieces, etc.)
- **Billing & Subscriptions**: Stripe integration for payments and subscriptions
- **Service Discovery**: Expose available functions via namespace endpoints
- **Audit & Compliance**: Comprehensive logging for GDPR/HIPAA/SOX compliance

### Technology Stack

- **Framework**: FastAPI 0.109+ (async support, automatic OpenAPI docs)
- **Database**: PostgreSQL 15+ with SQLAlchemy 2.0+ (async ORM)
- **Cache**: Redis 7+ for rate limiting and session management
- **Migrations**: Alembic for database schema versioning
- **Validation**: Pydantic v2 for request/response schemas
- **Task Queue**: Celery for async workflow monitoring
- **HTTP Client**: httpx for external API calls (Activepieces, Stripe)
- **Testing**: pytest, pytest-asyncio, httpx
- **Deployment**: Docker + docker-compose on Digital Ocean

---

## Architecture

### System Context

> **Note:** As of v4.0.0, AI assistants connect directly via HTTPS to namespace endpoints.
> No local proxy/gateway is required. See [Namespace Architecture](../mcpworks-internals/docs/implementation/namespace-architecture.md).

```
┌─────────────────────────────────────────────────────────┐
│  Claude Code / Codex / GitHub Copilot (MCP Client)     │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS (direct connection)
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
┌─────────────────────┐  ┌─────────────────────┐
│ {ns}.create.mcpworks.io │  │ {ns}.run.mcpworks.io │
│ (Management)         │  │ (Execution)         │
└─────────┬───────────┘  └─────────┬───────────┘
          │                        │
          └────────────┬───────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│  mcpworks-api (This Service)                            │
│  - Authenticate requests (API key / JWT)                │
│  - Track usage against subscription limits              │
│  - Orchestrate function execution                       │
│  - Route to appropriate backend                         │
└────────┬───────────┬───────────┬─────────────┬──────────┘
         │           │           │             │
         ▼           ▼           ▼             ▼
    ┌────────┐  ┌──────────┐  ┌──────┐  ┌──────────┐
    │Postgres│  │  Redis   │  │ Code │  │  Stripe  │
    │   DB   │  │  Cache   │  │Sandbox│  │ Payments │
    └────────┘  └──────────┘  └──────┘  └──────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
               ┌────────┐  ┌──────────┐  ┌────────┐
               │Active  │  │ nanobot  │  │ GitHub │
               │pieces  │  │   .ai    │  │  Repo  │
               └────────┘  └──────────┘  └────────┘
```

**Endpoint Pattern:**
- `{namespace}.create.mcpworks.io` - Management interface (CRUD functions/services)
- `{namespace}.run.mcpworks.io` - Execution interface (call functions)

**Function Backends:**
- **Code Sandbox** - LLM-authored Python/TypeScript execution (nsjail isolation)
- **Activepieces** - Visual workflow builder (150+ integrations)
- **nanobot.ai** - Definition TBD
- **GitHub Repo** - Future: MCPWorks Framework functions

### Service Components

#### API Layer (`src/mcpworks_api/api/v1/`)
- REST endpoints for all operations
- Request validation via Pydantic schemas
- Response serialization
- Error handling and status codes

#### Service Layer (`src/mcpworks_api/services/`)
- Business logic implementation
- Usage tracking and limits
- Workflow orchestration
- External service integration (Activepieces, Stripe)

#### Data Layer (`src/mcpworks_api/models/`)
- SQLAlchemy ORM models
- Database schema definitions
- Relationships and constraints

#### Core Utilities (`src/mcpworks_api/core/`)
- Database connection management
- Redis cache utilities
- Security helpers (hashing, JWT)
- Rate limiting

#### Middleware (`src/mcpworks_api/middleware/`)
- Authentication (API key, JWT)
- Rate limiting
- Audit logging
- CORS handling

---

## Data Models

### Database Schema

#### Users Table

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),
    email_verified BOOLEAN DEFAULT FALSE,
    verification_token VARCHAR(255)
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_status ON users(status);
```

#### API Keys Table

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash VARCHAR(255) NOT NULL UNIQUE,
    key_prefix VARCHAR(20) NOT NULL,  -- 'mcp_live_' or 'mcp_test_'
    name VARCHAR(100),
    scopes TEXT[] DEFAULT ARRAY['read', 'write', 'execute'],
    last_used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_api_keys_user ON api_keys(user_id);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
```

#### Subscriptions Table

```sql
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    tier VARCHAR(20) NOT NULL CHECK (tier IN ('free', 'builder', 'pro', 'enterprise')),
    status VARCHAR(20) NOT NULL CHECK (status IN ('active', 'cancelled', 'past_due', 'trialing')),
    stripe_subscription_id VARCHAR(255) UNIQUE,
    stripe_customer_id VARCHAR(255),
    current_period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    current_period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_stripe ON subscriptions(stripe_subscription_id);
```

#### Usage Records Table

```sql
CREATE TABLE usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    billing_period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    billing_period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    executions_count INTEGER NOT NULL DEFAULT 0,
    executions_limit INTEGER NOT NULL,  -- From subscription tier
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (user_id, billing_period_start)
);

CREATE INDEX idx_usage_records_user ON usage_records(user_id);
CREATE INDEX idx_usage_records_period ON usage_records(billing_period_start, billing_period_end);
```

#### Workflows Table

```sql
CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    activepieces_flow_id VARCHAR(255),
    activepieces_project_id VARCHAR(255),
    mcp_tool_name VARCHAR(100) NOT NULL,
    mcp_tool_description TEXT,
    mcp_input_schema JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
    -- Removed: base_credit_cost (using subscription tiers instead)
    execution_count INTEGER DEFAULT 0,
    last_executed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (user_id, mcp_tool_name)
);

CREATE INDEX idx_workflows_user ON workflows(user_id);
CREATE INDEX idx_workflows_status ON workflows(status);
```

#### Workflow Executions Table

```sql
CREATE TABLE workflow_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    activepieces_execution_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    input_params JSONB,
    result JSONB,
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER
);

CREATE INDEX idx_workflow_executions_workflow ON workflow_executions(workflow_id);
CREATE INDEX idx_workflow_executions_user ON workflow_executions(user_id);
CREATE INDEX idx_workflow_executions_status ON workflow_executions(status);
CREATE INDEX idx_workflow_executions_started ON workflow_executions(started_at DESC);
```

#### Workflow Templates Table

```sql
CREATE TABLE workflow_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(50),  -- 'email', 'ecommerce', 'crm', etc.
    activepieces_flow_template JSONB NOT NULL,
    mcp_tool_name VARCHAR(100) NOT NULL UNIQUE,
    mcp_tool_description TEXT,
    mcp_input_schema JSONB NOT NULL,
    preview_image_url TEXT,
    usage_count INTEGER DEFAULT 0,
    tier_required VARCHAR(20) DEFAULT 'free' CHECK (tier_required IN ('free', 'builder', 'pro', 'enterprise')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_workflow_templates_category ON workflow_templates(category);
CREATE INDEX idx_workflow_templates_tier ON workflow_templates(tier_required);
```

#### Audit Logs Table

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50),
    resource_id UUID,
    ip_address INET,
    user_agent TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created ON audit_logs(created_at DESC);
```

---

## API Endpoints

### Authentication & Users

#### POST /v1/auth/register
Register a new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "name": "John Doe"
}
```

**Response 201 Created:**
```json
{
  "user": {
    "id": "usr_abc123",
    "email": "user@example.com",
    "name": "John Doe",
    "created_at": "2025-01-15T10:30:00Z"
  },
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### POST /v1/auth/login
Authenticate and receive session tokens.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

**Response 200 OK:**
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### POST /v1/auth/logout
Invalidate current session.

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Response 204 No Content**

#### GET /v1/users/me
Get current user profile.

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Response 200 OK:**
```json
{
  "id": "usr_abc123",
  "email": "user@example.com",
  "name": "John Doe",
  "created_at": "2025-01-15T10:30:00Z",
  "email_verified": true,
  "subscription": {
    "tier": "builder",
    "status": "active",
    "current_period_end": "2025-02-15T10:30:00Z"
  },
  "usage": {
    "executions_count": 847,
    "executions_limit": 25000,
    "executions_remaining": 24153
  }
}
```

#### POST /v1/users/me/api-keys
Generate a new API key.

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Request:**
```json
{
  "name": "Production Key",
  "scopes": ["read", "write", "execute"],
  "expires_in_days": 365
}
```

**Response 201 Created:**
```json
{
  "id": "key_xyz789",
  "key": "mcp_live_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456",
  "key_prefix": "mcp_live_",
  "name": "Production Key",
  "scopes": ["read", "write", "execute"],
  "created_at": "2025-01-15T10:30:00Z",
  "expires_at": "2026-01-15T10:30:00Z"
}
```

**Note:** The full API key is only returned once. Store it securely.

#### DELETE /v1/users/me/api-keys/{key_id}
Revoke an API key.

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Response 204 No Content**

---

### Usage

#### GET /v1/usage
Get current usage for billing period.

**Headers:**
```
Authorization: Bearer {api_key}
```

**Response 200 OK:**
```json
{
  "billing_period_start": "2025-01-01T00:00:00Z",
  "billing_period_end": "2025-01-31T23:59:59Z",
  "executions_count": 847,
  "executions_limit": 25000,
  "executions_remaining": 24153,
  "usage_percentage": 3.4,
  "tier": "builder"
}
```

#### GET /v1/usage/history
Get usage history across billing periods.

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Query Parameters:**
- `limit` (default: 12, max: 24)

**Response 200 OK:**
```json
{
  "periods": [
    {
      "billing_period_start": "2025-01-01T00:00:00Z",
      "billing_period_end": "2025-01-31T23:59:59Z",
      "executions_count": 847,
      "executions_limit": 25000,
      "tier": "builder"
    },
    {
      "billing_period_start": "2024-12-01T00:00:00Z",
      "billing_period_end": "2024-12-31T23:59:59Z",
      "executions_count": 923,
      "executions_limit": 25000,
      "tier": "builder"
    }
  ],
  "total": 12
}
```

---

### Subscriptions

#### POST /v1/subscriptions
Subscribe to a monthly plan.

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Request:**
```json
{
  "tier": "builder",
  "payment_method_id": "pm_abc123"
}
```

**Response 201 Created:**
```json
{
  "subscription": {
    "id": "sub_xyz789",
    "tier": "builder",
    "status": "active",
    "current_period_start": "2025-01-15T10:30:00Z",
    "current_period_end": "2025-02-15T10:30:00Z",
    "stripe_subscription_id": "sub_stripe123"
  },
  "usage_limits": {
    "executions_per_month": 25000,
    "max_functions": 25
  }
}
```

#### GET /v1/subscriptions/current
Get current subscription details.

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Response 200 OK:**
```json
{
  "id": "sub_xyz789",
  "tier": "builder",
  "status": "active",
  "current_period_start": "2025-01-15T10:30:00Z",
  "current_period_end": "2025-02-15T10:30:00Z",
  "cancel_at_period_end": false,
  "limits": {
    "max_functions": 25,
    "max_executions_per_month": 25000
  }
}
```

#### PATCH /v1/subscriptions/current
Update subscription tier.

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Request:**
```json
{
  "tier": "pro"
}
```

**Response 200 OK:**
```json
{
  "subscription": {
    "id": "sub_xyz789",
    "tier": "pro",
    "status": "active",
    "current_period_start": "2025-01-15T10:30:00Z",
    "current_period_end": "2025-02-15T10:30:00Z"
  },
  "prorated_charge_usd": 120.00,
  "new_limits": {
    "executions_per_month": 250000,
    "max_functions": 100
  }
}
```

#### DELETE /v1/subscriptions/current
Cancel subscription (effective at period end).

**Headers:**
```
Authorization: Bearer {jwt_token}
```

**Response 200 OK:**
```json
{
  "subscription": {
    "id": "sub_xyz789",
    "tier": "builder",
    "status": "active",
    "cancel_at_period_end": true,
    "current_period_end": "2025-02-15T10:30:00Z"
  },
  "message": "Subscription will be cancelled on 2025-02-15T10:30:00Z"
}
```

---

### Workflows

#### GET /v1/workflows
List user's workflows.

**Headers:**
```
Authorization: Bearer {api_key}
```

**Query Parameters:**
- `status` (optional: draft, published, archived)
- `limit` (default: 50, max: 100)
- `offset` (default: 0)

**Response 200 OK:**
```json
{
  "workflows": [
    {
      "id": "wf_abc123",
      "name": "Send Welcome Email",
      "description": "Sends a welcome email to new users",
      "mcp_tool_name": "send_welcome_email",
      "status": "published",
      "execution_count": 342,
      "last_executed_at": "2025-01-15T10:30:00Z",
      "created_at": "2025-01-10T08:00:00Z"
    }
  ],
  "total": 12,
  "limit": 50,
  "offset": 0
}
```

#### POST /v1/workflows
Create a new workflow.

**Headers:**
```
Authorization: Bearer {api_key}
```

**Request:**
```json
{
  "name": "Send Welcome Email",
  "description": "Sends a welcome email to new users",
  "mcp_tool_name": "send_welcome_email",
  "mcp_tool_description": "Send a personalized welcome email",
  "mcp_input_schema": {
    "type": "object",
    "properties": {
      "email": {"type": "string", "format": "email"},
      "name": {"type": "string"}
    },
    "required": ["email", "name"]
  },
  "activepieces_flow_template": {
    "trigger": {"type": "webhook"},
    "actions": [...]
  }
}
```

**Response 201 Created:**
```json
{
  "id": "wf_abc123",
  "name": "Send Welcome Email",
  "mcp_tool_name": "send_welcome_email",
  "status": "draft",
  "activepieces_flow_id": "ap_flow_xyz789",
  "created_at": "2025-01-15T10:30:00Z"
}
```

#### GET /v1/workflows/{workflow_id}
Get workflow details.

**Headers:**
```
Authorization: Bearer {api_key}
```

**Response 200 OK:**
```json
{
  "id": "wf_abc123",
  "name": "Send Welcome Email",
  "description": "Sends a welcome email to new users",
  "mcp_tool_name": "send_welcome_email",
  "mcp_tool_description": "Send a personalized welcome email",
  "mcp_input_schema": {...},
  "status": "published",
  "execution_count": 342,
  "last_executed_at": "2025-01-15T10:30:00Z",
  "created_at": "2025-01-10T08:00:00Z",
  "updated_at": "2025-01-10T08:00:00Z"
}
```

#### PATCH /v1/workflows/{workflow_id}
Update workflow.

**Headers:**
```
Authorization: Bearer {api_key}
```

**Request:**
```json
{
  "name": "Send Welcome Email (Updated)",
  "description": "Updated description"
}
```

**Response 200 OK:**
```json
{
  "id": "wf_abc123",
  "name": "Send Welcome Email (Updated)",
  "description": "Updated description",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

#### DELETE /v1/workflows/{workflow_id}
Delete workflow.

**Headers:**
```
Authorization: Bearer {api_key}
```

**Response 204 No Content**

#### POST /v1/workflows/{workflow_id}/publish
Publish workflow (make it active for execution).

**Headers:**
```
Authorization: Bearer {api_key}
```

**Response 200 OK:**
```json
{
  "id": "wf_abc123",
  "status": "published",
  "published_at": "2025-01-15T10:30:00Z"
}
```

#### GET /v1/workflows/{workflow_id}/schema
Get MCP tool schema for workflow.

**Headers:**
```
Authorization: Bearer {api_key}
```

**Response 200 OK:**
```json
{
  "name": "send_welcome_email",
  "description": "Send a personalized welcome email",
  "inputSchema": {
    "type": "object",
    "properties": {
      "email": {"type": "string", "format": "email"},
      "name": {"type": "string"}
    },
    "required": ["email", "name"]
  }
}
```

---

### Workflow Execution

#### POST /v1/execute/{workflow_id}
Execute a workflow (check usage limits, trigger execution).

**Headers:**
```
Authorization: Bearer {api_key}
```

**Request:**
```json
{
  "input_params": {
    "email": "user@example.com",
    "name": "John Doe"
  }
}
```

**Response 202 Accepted:**
```json
{
  "execution_id": "exec_abc123",
  "workflow_id": "wf_xyz789",
  "status": "pending",
  "estimated_completion_ms": 2000,
  "started_at": "2025-01-15T10:30:00Z"
}
```

**Error 400 Bad Request (Usage Limit Exceeded):**
```json
{
  "error": {
    "code": "USAGE_LIMIT_EXCEEDED",
    "message": "Usage limit exceeded for current billing period",
    "details": {
      "executions_count": 1000,
      "executions_limit": 1000,
      "resets_at": "2025-02-01T00:00:00Z"
    }
  }
}
```

#### GET /v1/executions/{execution_id}
Get execution status and results.

**Headers:**
```
Authorization: Bearer {api_key}
```

**Response 200 OK (Completed):**
```json
{
  "execution_id": "exec_abc123",
  "workflow_id": "wf_xyz789",
  "status": "completed",
  "input_params": {
    "email": "user@example.com",
    "name": "John Doe"
  },
  "result": {
    "email_sent": true,
    "message_id": "msg_xyz789"
  },
  "duration_ms": 1250,
  "started_at": "2025-01-15T10:30:00Z",
  "completed_at": "2025-01-15T10:30:01Z"
}
```

**Response 200 OK (Failed):**
```json
{
  "execution_id": "exec_abc123",
  "workflow_id": "wf_xyz789",
  "status": "failed",
  "error_message": "Failed to connect to email service",
  "duration_ms": 500,
  "started_at": "2025-01-15T10:30:00Z",
  "completed_at": "2025-01-15T10:30:00Z"
}
```

#### GET /v1/executions
List execution history.

**Headers:**
```
Authorization: Bearer {api_key}
```

**Query Parameters:**
- `workflow_id` (optional filter)
- `status` (optional filter: pending, running, completed, failed, cancelled)
- `limit` (default: 50, max: 100)
- `offset` (default: 0)

**Response 200 OK:**
```json
{
  "executions": [
    {
      "execution_id": "exec_abc123",
      "workflow_id": "wf_xyz789",
      "workflow_name": "Send Welcome Email",
      "status": "completed",
      "duration_ms": 1250,
      "started_at": "2025-01-15T10:30:00Z",
      "completed_at": "2025-01-15T10:30:01Z"
    }
  ],
  "total": 342,
  "limit": 50,
  "offset": 0
}
```

#### DELETE /v1/executions/{execution_id}
Cancel a running execution.

**Headers:**
```
Authorization: Bearer {api_key}
```

**Response 200 OK:**
```json
{
  "execution_id": "exec_abc123",
  "status": "cancelled",
  "message": "Execution cancelled successfully"
}
```

---

### Service Discovery

#### GET /v1/services
Get available services (workflows + first-party MCPs).

**Headers:**
```
Authorization: Bearer {api_key}
```

**Response 200 OK:**
```json
{
  "services": [
    {
      "name": "math",
      "type": "first_party",
      "endpoint": "https://math.mcpworks.io",
      "tier_required": "free",
      "description": "Advanced mathematical calculations and verification"
    },
    {
      "name": "text",
      "type": "first_party",
      "endpoint": "https://text.mcpworks.io",
      "tier_required": "builder",
      "description": "Document analysis and text processing"
    },
    {
      "name": "send_welcome_email",
      "type": "user_workflow",
      "workflow_id": "wf_abc123",
      "description": "Send a personalized welcome email",
      "input_schema": {...}
    }
  ],
  "user": {
    "id": "usr_123",
    "tier": "builder",
    "executions_remaining": 24153
  }
}
```

---

### Webhooks

#### POST /v1/webhooks/activepieces
Receive callbacks from Activepieces.

**Headers:**
```
X-Activepieces-Signature: sha256=...
```

**Request:**
```json
{
  "execution_id": "exec_abc123",
  "flow_id": "ap_flow_xyz789",
  "status": "completed",
  "result": {
    "email_sent": true,
    "message_id": "msg_xyz789"
  }
}
```

**Response 200 OK:**
```json
{
  "status": "processed"
}
```

---

## Usage Tracking

### Subscription-Based Billing

MCPWorks uses **monthly subscription billing** with usage limits per tier. No credits, no prepaid balance - just simple subscription tiers.

### How It Works

1. User subscribes to a tier (Free, Builder, Pro, Enterprise)
2. Each tier has monthly execution limits
3. Usage is tracked per billing period
4. Soft limits: warn at 80%, pause at 100% (or prompt upgrade)
5. Usage resets at start of each billing period

### Usage Tracking Schema

```python
class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    billing_period_start: Mapped[datetime]
    billing_period_end: Mapped[datetime]
    executions_count: Mapped[int] = mapped_column(default=0)
    executions_limit: Mapped[int]  # From subscription tier

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(onupdate=datetime.utcnow)
```

### Usage Check on Execution

```python
async def check_usage_limit(user_id: UUID) -> bool:
    """Check if user is within their subscription limits."""
    usage = await get_current_usage(user_id)

    if usage.executions_count >= usage.executions_limit:
        raise UsageLimitExceededError(
            current=usage.executions_count,
            limit=usage.executions_limit,
            resets_at=usage.billing_period_end
        )

    return True

async def increment_usage(user_id: UUID) -> None:
    """Increment execution count for current billing period."""
    usage = await get_current_usage(user_id)
    usage.executions_count += 1
    await db.commit()
```

### Tier Limits

| Tier | Executions/Month | Functions | Price |
|------|------------------|-----------|-------|
| Free | 1,000 | 5 | $0 |
| Builder | 25,000 | 25 | $29/mo |
| Pro | 250,000 | 100 | $149/mo |
| Enterprise | 1,000,000 | Unlimited | $499+/mo |

---

## Activepieces Integration

### Overview

Activepieces is the workflow execution engine. It provides:
- Visual workflow builder
- 150+ pre-built integrations (Stripe, Shopify, SendGrid, etc.)
- Webhook triggers
- Step-by-step execution tracking

### Integration Architecture

```
mcpworks-api  ←→  Activepieces
     │                 │
     ├─ Create Flow    │
     ├─ Update Flow    │
     ├─ Trigger Exec   │
     │                 │
     │    ← Webhooks ──┤
     │    (callbacks)  │
```

### Workflow Lifecycle

#### 1. Workflow Creation

When user creates a workflow in mcpworks:

```python
async def create_workflow(user_id: UUID, workflow_data: WorkflowCreate) -> Workflow:
    # Create flow in Activepieces
    ap_response = await activepieces_client.create_flow(
        project_id=user.activepieces_project_id,
        flow_definition=workflow_data.activepieces_flow_template,
        webhook_url=f"{API_BASE_URL}/v1/webhooks/activepieces"
    )

    # Store workflow in our database
    workflow = Workflow(
        user_id=user_id,
        name=workflow_data.name,
        activepieces_flow_id=ap_response.flow_id,
        mcp_tool_name=workflow_data.mcp_tool_name,
        mcp_input_schema=workflow_data.mcp_input_schema
    )

    await db.add(workflow)
    await db.commit()

    return workflow
```

#### 2. Workflow Execution

When AI assistant requests workflow execution via namespace endpoint:

```python
async def execute_workflow(workflow_id: UUID, input_params: dict) -> WorkflowExecution:
    workflow = await db.get(Workflow, workflow_id)

    # Check usage limits
    await usage_service.check_limit(user_id=workflow.user_id)

    # Create execution record
    execution = WorkflowExecution(
        workflow_id=workflow_id,
        user_id=workflow.user_id,
        input_params=input_params,
        status="pending"
    )
    await db.add(execution)
    await db.commit()

    # Trigger Activepieces flow
    ap_response = await activepieces_client.trigger_flow(
        flow_id=workflow.activepieces_flow_id,
        input_data={
            "execution_id": str(execution.id),
            "params": input_params
        }
    )

    # Update with Activepieces execution ID
    execution.activepieces_execution_id = ap_response.execution_id
    execution.status = "running"
    await db.commit()

    # Increment usage counter
    await usage_service.increment(user_id=workflow.user_id)

    return execution
```

#### 3. Webhook Callbacks

Activepieces sends callbacks when execution completes:

```python
async def handle_activepieces_webhook(webhook_data: dict) -> None:
    # Verify signature
    verify_activepieces_signature(webhook_data)

    execution_id = UUID(webhook_data["execution_id"])
    execution = await db.get(WorkflowExecution, execution_id)

    if webhook_data["status"] == "completed":
        # Update execution
        execution.status = "completed"
        execution.result = webhook_data["result"]
        execution.completed_at = datetime.utcnow()
        execution.duration_ms = webhook_data["duration_ms"]

    elif webhook_data["status"] == "failed":
        # Update execution
        execution.status = "failed"
        execution.error_message = webhook_data["error"]
        execution.completed_at = datetime.utcnow()

    await db.commit()
```

### Activepieces API Endpoints Used

- **POST /v1/flows** - Create new flow
- **GET /v1/flows/{flow_id}** - Get flow definition
- **PATCH /v1/flows/{flow_id}** - Update flow
- **DELETE /v1/flows/{flow_id}** - Delete flow
- **POST /v1/flows/{flow_id}/executions** - Trigger execution
- **GET /v1/executions/{execution_id}** - Get execution status

### Security

- Activepieces API key stored in environment variables
- Webhook callbacks authenticated via HMAC-SHA256 signature
- Each user isolated in separate Activepieces project
- Rate limiting on flow executions

---

## Authentication & Security

### Authentication Methods

#### 1. API Key Authentication (MCP Client → API)

Used for programmatic access from AI assistants via namespace endpoints.

**Key Format:**
- Live: `mcp_live_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456`
- Test: `mcp_test_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456`

**Storage:**
- Keys hashed with bcrypt (cost factor 12)
- Only prefix stored in plaintext for identification
- Full key shown only once at creation

**Usage:**
```http
Authorization: Bearer mcp_live_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456
```

**Scopes:**
- `read` - Read user data, workflows, executions
- `write` - Create/update/delete workflows
- `execute` - Execute workflows

#### 2. Session-Based Authentication (Web Dashboard)

Used for web interface access.

**Flow:**
1. User logs in with email/password
2. Server issues JWT access token (15 min expiry)
3. Server issues refresh token (30 day expiry, httpOnly cookie)
4. Access token used for API calls
5. Refresh token used to get new access token

**JWT Claims:**
```json
{
  "sub": "usr_abc123",
  "email": "user@example.com",
  "tier": "builder",
  "exp": 1642252800,
  "iat": 1642252800
}
```

**Usage:**
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### 3. Webhook Signature Verification

Used for Activepieces callbacks.

**Signature Calculation:**
```python
signature = hmac.new(
    key=WEBHOOK_SECRET.encode(),
    msg=request_body.encode(),
    digestmod=hashlib.sha256
).hexdigest()
```

**Verification:**
```http
X-Activepieces-Signature: sha256=abc123...
```

### Security Features

#### Rate Limiting

Implemented via Redis with sliding window algorithm.

**Limits:**
- Per API key: 1000 requests/hour
- Per IP (unauthenticated): 100 requests/hour
- Per workflow execution: Based on subscription tier

**Headers:**
```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 950
X-RateLimit-Reset: 1642252800
```

#### Input Validation

- All requests validated via Pydantic schemas
- JSON schema validation for workflow inputs
- SQL injection prevention (SQLAlchemy ORM)
- XSS prevention (sanitize all user inputs)

#### Data Protection

- Passwords hashed with bcrypt (cost factor 12)
- API keys hashed before storage
- Sensitive data encrypted at rest (database-level)
- TLS 1.3 for all API communication
- No logging of passwords or full API keys

#### Audit Logging

All security-relevant events logged:
- Authentication attempts (success/failure)
- API key creation/revocation
- Subscription changes
- Workflow executions
- Administrative actions

**Retention:**
- Free tier: 90 days
- Paid tiers: 1 year
- Enterprise: 7 years

---

## Pricing & Subscriptions

### Subscription Tiers

#### Free Tier ($0/month)
- 5 functions maximum
- 1,000 executions/month
- Community support (GitHub Discussions)
- Code Sandbox backend included

#### Builder Tier ($29/month)
- 25 functions
- 25,000 executions/month
- Email support (48h response)
- Function templates library
- All backends included

#### Pro Tier ($149/month)
- 100 functions
- 250,000 executions/month
- Priority email support (24h response)
- Advanced function templates
- Custom integrations

#### Enterprise Tier ($499+/month)
- Unlimited functions
- 1,000,000 executions
- Dedicated support (4h response)
- SOC 2 compliance reports
- Custom SLA
- White-label option

### Pricing Model

**Monthly Subscription Only** - No credits, no prepaid balance, no complexity.

**How It Works:**
- Subscribe to a tier
- Use up to your execution limit
- Upgrade anytime if you need more
- Usage resets each billing period

**Overage Handling:**
- Soft limit at 80% (warning email)
- Hard limit at 100% (prompt to upgrade)
- No automatic charges beyond subscription

### Stripe Integration

**Subscription Management:**
- Created via Stripe Checkout
- Managed via Stripe Customer Portal
- Automatic renewal
- Prorated upgrades/downgrades

**Payment Methods:**
- Credit/debit cards
- ACH bank transfers (US only)
- Apple Pay / Google Pay

**Webhooks:**
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_succeeded`
- `invoice.payment_failed`

---

## Error Handling

### HTTP Status Codes

- **200 OK** - Success
- **201 Created** - Resource created
- **204 No Content** - Success with no body
- **400 Bad Request** - Invalid input
- **401 Unauthorized** - Missing/invalid authentication
- **403 Forbidden** - Insufficient permissions
- **404 Not Found** - Resource not found
- **409 Conflict** - Resource already exists or state conflict
- **429 Too Many Requests** - Rate limit exceeded
- **500 Internal Server Error** - Unexpected server error
- **503 Service Unavailable** - Temporary outage

### Error Response Format

```json
{
  "error": {
    "code": "USAGE_LIMIT_EXCEEDED",
    "message": "Usage limit exceeded for current billing period",
    "details": {
      "executions_count": 1000,
      "executions_limit": 1000,
      "resets_at": "2025-02-01T00:00:00Z"
    },
    "request_id": "req_abc123"
  }
}
```

### Error Codes

- `AUTHENTICATION_FAILED` - Invalid credentials
- `INVALID_API_KEY` - API key invalid or revoked
- `RATE_LIMIT_EXCEEDED` - Too many requests
- `USAGE_LIMIT_EXCEEDED` - Execution limit reached for billing period
- `WORKFLOW_NOT_FOUND` - Workflow doesn't exist
- `EXECUTION_FAILED` - Workflow execution error
- `ACTIVEPIECES_ERROR` - External service error
- `STRIPE_PAYMENT_FAILED` - Payment processing error
- `VALIDATION_ERROR` - Input validation failed
- `INTERNAL_ERROR` - Unexpected server error

### Retry Strategy

**Idempotent Operations (GET, PUT, DELETE):**
- Safe to retry automatically
- Exponential backoff: 1s, 2s, 4s, 8s, 16s
- Max retries: 5 attempts

**Non-Idempotent Operations (POST):**
- Include idempotency key in request
- Server deduplicates based on key
- Returns cached response for duplicate requests

**Circuit Breaker:**
- For external services (Activepieces, Stripe)
- Opens after 5 consecutive failures
- Half-open after 30 seconds
- Closes after 3 consecutive successes

---

## Monitoring & Observability

### Application Metrics (Prometheus)

**Request Metrics:**
- `http_requests_total{method, endpoint, status}` - Request count
- `http_request_duration_seconds{method, endpoint}` - Request latency

**Business Metrics:**
- `workflow_executions_total{status}` - Execution count by status
- `workflow_execution_duration_seconds` - Execution duration
- `usage_percentage{tier}` - Usage percentage by subscription tier
- `active_users_total` - Active user count

**System Metrics:**
- `db_connections_active` - Active database connections
- `db_connections_idle` - Idle database connections
- `redis_cache_hit_rate` - Cache hit percentage
- `error_rate{endpoint}` - Error rate by endpoint

### Health Checks

**Endpoint:** `GET /health`

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-01-15T10:30:00Z",
  "checks": {
    "database": {
      "status": "up",
      "latency_ms": 5
    },
    "redis": {
      "status": "up",
      "latency_ms": 2
    },
    "activepieces": {
      "status": "up",
      "latency_ms": 50
    }
  }
}
```

**Status Values:**
- `healthy` - All checks passing
- `degraded` - Some checks failing (non-critical)
- `unhealthy` - Critical checks failing

### Logging

**Levels:**
- `DEBUG` - Development only (SQL queries, detailed execution)
- `INFO` - Request/response, execution lifecycle
- `WARNING` - Rate limit approaching, retries
- `ERROR` - Failed executions, external service errors
- `CRITICAL` - Database connection loss, service failures

**Structured Format:**
```json
{
  "timestamp": "2025-01-15T10:30:00Z",
  "level": "INFO",
  "logger": "mcpworks_api.services.execution",
  "message": "Workflow execution completed",
  "context": {
    "user_id": "usr_123",
    "workflow_id": "wf_456",
    "execution_id": "exec_789",
    "duration_ms": 1250,
    "status": "completed"
  },
  "request_id": "req_abc123"
}
```

### Alerts (PagerDuty)

**Critical (Immediate):**
- API down (health check failing)
- Database connection lost
- Redis connection lost
- Error rate >10%

**High (15 min):**
- Error rate >5%
- Execution failure rate >10%
- Response time p95 >1s

**Medium (1 hour):**
- Rate limits frequently hit
- Cache hit rate <80%
- Disk space >85%

**Low (Daily digest):**
- Approaching resource limits
- Unusual traffic patterns

---

## Deployment

### Development Environment

**Docker Compose Setup:**

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/mcpworks
      - REDIS_URL=redis://redis:6379/0
      - ACTIVEPIECES_URL=http://activepieces:3000
      - ACTIVEPIECES_API_KEY=ap_dev_key
      - JWT_SECRET_KEY=dev_secret_key
      - LOG_LEVEL=DEBUG
    depends_on:
      - db
      - redis
      - activepieces
    volumes:
      - ./src:/app/src
    command: uvicorn mcpworks_api.main:app --host 0.0.0.0 --reload

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=mcpworks
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  activepieces:
    image: activepieces/activepieces:latest
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/activepieces
      - AP_ENCRYPTION_KEY=dev_encryption_key
    ports:
      - "3000:3000"
    depends_on:
      - db

volumes:
  postgres_data:
```

**Commands:**
```bash
# Start development environment
docker-compose up --build

# Run migrations
docker-compose exec api alembic upgrade head

# Create sample data
docker-compose exec api python scripts/seed_data.py

# Run tests
docker-compose exec api pytest tests/ -v
```

### Production Infrastructure (Digital Ocean)

**Components:**

1. **Application Servers**
   - 2x App Droplets (4GB RAM, 2 vCPUs)
   - Load balanced via Digital Ocean Load Balancer
   - Auto-scaling: 2-10 instances based on CPU (50-80% target)
   - Health checks: `GET /health` every 30s

2. **Database**
   - Digital Ocean Managed PostgreSQL
   - Primary + Read Replica
   - Daily automated backups (7 day retention)
   - Point-in-time recovery enabled
   - Connection pooling via PgBouncer

3. **Cache**
   - Digital Ocean Managed Redis
   - High availability (primary + replica)
   - Eviction policy: allkeys-lru
   - Max memory: 2GB

4. **Activepieces**
   - Dedicated Droplet (8GB RAM, 4 vCPUs)
   - Docker-based deployment
   - Persistent volume for data
   - Separate database from main app

5. **Monitoring**
   - Digital Ocean Monitoring (built-in)
   - Prometheus for application metrics
   - Logs aggregated to Digital Ocean Logs
   - PagerDuty for alerts

**Environment Variables:**

```bash
# Database
DATABASE_URL=postgresql://user:pass@db-prod.do.com:5432/mcpworks
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Cache
REDIS_URL=redis://redis-prod.do.com:6379/0
REDIS_MAX_CONNECTIONS=50

# Activepieces
ACTIVEPIECES_URL=https://flows.mcpworks.io
ACTIVEPIECES_API_KEY=ap_live_...
ACTIVEPIECES_WEBHOOK_SECRET=whsec_...

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# JWT
JWT_SECRET_KEY=...
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=15

# Rate Limiting
API_RATE_LIMIT_PER_HOUR=1000
EXECUTION_RATE_LIMIT_FREE=100
EXECUTION_RATE_LIMIT_STARTER=1000
EXECUTION_RATE_LIMIT_PRO=10000

# Observability
SENTRY_DSN=https://...@sentry.io/...
LOG_LEVEL=INFO

# Feature Flags
ENABLE_WORKFLOW_TEMPLATES=true
ENABLE_TEXT_MCP=false  # A1 release
```

**Deployment Process:**

```bash
# 1. Build Docker image
docker build -t mcpworks-api:1.0.0 .

# 2. Push to container registry
docker tag mcpworks-api:1.0.0 registry.digitalocean.com/mcpworks/api:1.0.0
docker push registry.digitalocean.com/mcpworks/api:1.0.0

# 3. Run migrations (on one instance)
kubectl exec -it api-pod -- alembic upgrade head

# 4. Rolling update (zero downtime)
kubectl set image deployment/api api=registry.digitalocean.com/mcpworks/api:1.0.0

# 5. Verify deployment
kubectl rollout status deployment/api
curl https://api.mcpworks.io/health
```

---

## Testing Strategy

### Testing Pyramid

**70% Unit Tests:**
- Test individual functions and methods
- Mock external dependencies
- Fast execution (<100ms per test)
- Focus areas:
  - Usage tracking and limit checking
  - Authentication and authorization
  - Input validation
  - Business logic calculations

**20% Integration Tests:**
- Test API endpoints with real database
- Use test database (Docker container)
- Test complete request/response cycles
- Focus areas:
  - API endpoint behavior
  - Database transactions
  - Webhook handling
  - Multi-step workflows

**10% End-to-End Tests:**
- Test complete user workflows
- Use staging environment
- Critical paths:
  - User registration → workflow creation → execution
  - Subscription → execution → usage tracking
  - Subscription upgrade → limit changes

### Test Organization

```python
# tests/conftest.py
@pytest.fixture
async def test_db():
    """Provide test database session"""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def test_user(test_db):
    """Create test user with API key"""
    user = User(email="test@example.com", password_hash="...")
    test_db.add(user)
    await test_db.commit()

    api_key = APIKey(user_id=user.id, key_hash="...")
    test_db.add(api_key)
    await test_db.commit()

    return user, api_key

# tests/unit/test_usage_service.py
async def test_check_limit_within_limit(test_db, test_user):
    """Test usage check within limit"""
    user, _ = test_user

    # Create usage record with room remaining
    usage = UsageRecord(
        user_id=user.id,
        billing_period_start=datetime(2025, 1, 1),
        billing_period_end=datetime(2025, 1, 31),
        executions_count=500,
        executions_limit=1000
    )
    test_db.add(usage)
    await test_db.commit()

    # Should pass
    result = await usage_service.check_limit(user.id)
    assert result is True

async def test_check_limit_exceeded(test_db, test_user):
    """Test usage check when limit exceeded"""
    user, _ = test_user

    usage = UsageRecord(
        user_id=user.id,
        billing_period_start=datetime(2025, 1, 1),
        billing_period_end=datetime(2025, 1, 31),
        executions_count=1000,
        executions_limit=1000
    )
    test_db.add(usage)
    await test_db.commit()

    # Should fail
    with pytest.raises(UsageLimitExceededError):
        await usage_service.check_limit(user.id)

# tests/integration/test_workflow_execution.py
async def test_execute_workflow_success(test_client, test_user):
    """Test complete workflow execution flow"""
    user, api_key = test_user

    # Create workflow
    workflow = await create_test_workflow(user.id)

    # Execute workflow
    response = await test_client.post(
        f"/v1/execute/{workflow.id}",
        headers={"Authorization": f"Bearer {api_key.key}"},
        json={"input_params": {"email": "test@example.com"}}
    )

    assert response.status_code == 202
    execution_id = response.json()["execution_id"]

    # Simulate Activepieces callback
    await simulate_activepieces_callback(execution_id, status="completed")

    # Verify execution completed
    execution = await db.get(WorkflowExecution, execution_id)
    assert execution.status == "completed"
```

### Continuous Integration

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: mcpworks_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run linters
        run: |
          black --check src/
          mypy src/
          ruff check src/

      - name: Run migrations
        run: alembic upgrade head
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/mcpworks_test

      - name: Run tests
        run: pytest tests/ -v --cov=src --cov-report=xml
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/mcpworks_test
          REDIS_URL: redis://localhost:6379/0

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## Implementation Roadmap

### Phase 1 - Foundation (Week 1-2)

**Goals:**
- Database schema and migrations
- User authentication system
- Usage tracking system
- Development environment

**Tasks:**
1. Set up project structure and dependencies
2. Create Alembic migrations for all tables
3. Implement User and APIKey models
4. Build authentication endpoints (register, login, logout)
5. Implement API key generation and validation
6. Create usage tracking service (check/increment)
7. Set up Docker Compose development environment
8. Configure logging and error handling
9. Add health check endpoint
10. Write unit tests for core services

**Deliverables:**
- Working authentication system
- Usage tracking system
- Docker development environment
- 70% unit test coverage

### Phase 2 - Core Workflow Platform (Week 3-4)

**Goals:**
- Activepieces integration
- Workflow CRUD operations
- Workflow execution with usage tracking
- Webhook handling

**Tasks:**
1. Integrate Activepieces client library
2. Implement workflow creation (API → Activepieces)
3. Build workflow CRUD endpoints
4. Create workflow execution endpoint
5. Implement usage limit check on execution start
6. Set up webhook receiver for Activepieces callbacks
7. Implement usage increment on execution complete
8. Add workflow templates system
9. Build service discovery endpoint
10. Write integration tests for workflow lifecycle

**Deliverables:**
- Functional workflow platform
- Activepieces integration working
- Complete workflow execution flow
- 60% integration test coverage

### Phase 3 - Billing & Subscriptions (Week 5-6)

**Goals:**
- Stripe integration
- Subscription management
- Usage reporting
- Tier enforcement

**Tasks:**
1. Integrate Stripe SDK
2. Create subscription endpoints (create, upgrade, cancel)
3. Implement Stripe webhook handling
4. Set up automatic subscription renewals
5. Implement usage tracking and reporting
6. Create usage reset on billing period change
7. Add subscription tier enforcement
8. Build admin dashboard endpoints (internal)
9. Implement upgrade prompts at 80% usage
10. Write tests for billing workflows

**Deliverables:**
- Working Stripe integration
- Subscription management system
- Usage tracking and reporting
- Tier-based limit enforcement

### Phase 4 - Polish & Production (Week 7-8)

**Goals:**
- Production deployment
- Security hardening
- Monitoring and alerting
- Documentation

**Tasks:**
1. Implement rate limiting (Redis-based)
2. Add comprehensive audit logging
3. Set up Prometheus metrics
4. Configure PagerDuty alerts
5. Write OpenAPI documentation
6. Deploy to Digital Ocean staging
7. Run load testing (Locust)
8. Security audit and penetration testing
9. Deploy to Digital Ocean production
10. Create runbook and operational docs

**Deliverables:**
- Production-ready deployment
- Complete monitoring and alerting
- Security hardened
- Full API documentation

### Success Criteria

**A0 Milestone (End of Week 8):**
- 5-10 pilot users successfully creating and executing workflows
- 3-5 workflow templates available
- 99% uptime in first month
- p95 latency <500ms
- Zero usage tracking errors
- Complete API documentation
- SOC 2 preparation started

---

## Appendix

### Project Structure

```
mcpworks-api/
├── src/
│   ├── mcpworks_api/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── auth.py
│   │   │       ├── users.py
│   │   │       ├── usage.py
│   │   │       ├── workflows.py
│   │   │       ├── executions.py
│   │   │       ├── subscriptions.py
│   │   │       └── webhooks.py
│   │   │
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── api_key.py
│   │   │   ├── subscription.py
│   │   │   ├── usage.py
│   │   │   ├── workflow.py
│   │   │   └── execution.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── auth.py
│   │   │   ├── usage.py
│   │   │   ├── workflow.py
│   │   │   └── execution.py
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── usage.py
│   │   │   ├── workflow.py
│   │   │   ├── execution.py
│   │   │   ├── activepieces.py
│   │   │   └── stripe.py
│   │   │
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── database.py
│   │   │   ├── cache.py
│   │   │   ├── security.py
│   │   │   └── rate_limit.py
│   │   │
│   │   └── middleware/
│   │       ├── __init__.py
│   │       ├── auth.py
│   │       ├── rate_limit.py
│   │       └── audit.py
│   │
├── alembic/
│   ├── versions/
│   └── env.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_usage_service.py
│   │   ├── test_auth_service.py
│   │   └── test_workflow_service.py
│   └── integration/
│       ├── test_workflow_execution.py
│       ├── test_subscription_flow.py
│       └── test_webhook_handling.py
│
├── scripts/
│   ├── seed_data.py
│   └── migrate_production.sh
│
├── .github/
│   └── workflows/
│       └── test.yml
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── alembic.ini
├── README.md
└── SPEC.md (this file)
```

### Dependencies

**requirements.txt:**
```
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy[asyncio]==2.0.25
asyncpg==0.29.0
alembic==1.13.1
pydantic==2.5.3
pydantic-settings==2.1.0
redis==5.0.1
httpx==0.26.0
stripe==7.11.0
bcrypt==4.1.2
pyjwt==2.8.0
python-multipart==0.0.6
prometheus-client==0.19.0
sentry-sdk[fastapi]==1.39.2
```

**requirements-dev.txt:**
```
pytest==7.4.4
pytest-asyncio==0.23.3
pytest-cov==4.1.0
black==24.1.1
mypy==1.8.0
ruff==0.1.14
locust==2.20.0
```

### Configuration

**config.py:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str
    redis_max_connections: int = 50

    # Activepieces
    activepieces_url: str
    activepieces_api_key: str
    activepieces_webhook_secret: str

    # Stripe
    stripe_secret_key: str
    stripe_webhook_secret: str

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 15

    # Rate Limiting
    api_rate_limit_per_hour: int = 1000
    execution_rate_limit_free: int = 1000
    execution_rate_limit_builder: int = 25000
    execution_rate_limit_pro: int = 250000

    # Observability
    sentry_dsn: str | None = None
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

---

## Related Documentation

This specification is the **source of truth** for mcpworks-api implementation. The following supporting documents provide additional context and guidance:

### Implementation Framework (`docs/implementation/`)

| Directory | Purpose | Key Documents |
|-----------|---------|---------------|
| `specs/` | Development principles and requirements | [CONSTITUTION.md](docs/implementation/specs/CONSTITUTION.md) - Governing principles |
| `plans/` | Technical architecture and implementation strategies | [technical-architecture.md](docs/implementation/plans/technical-architecture.md) - System design |
| `guidance/` | Best practices and patterns | [mcp-token-optimization.md](docs/implementation/guidance/mcp-token-optimization.md) - Token efficiency |

### Document Hierarchy

```
SPEC.md (this file)          ← Source of truth for implementation
    │
    └── docs/implementation/
        ├── specs/           ← Development principles (CONSTITUTION.md)
        │   ├── CONSTITUTION.md      - Quality standards, non-negotiables
        │   ├── api-contract.md      - REST API contract details
        │   └── TEMPLATE.md          - Template for new specs
        │
        ├── plans/           ← How we build (architecture decisions)
        │   └── technical-architecture.md
        │
        └── guidance/        ← Best practices (patterns to follow)
            └── mcp-token-optimization.md
```

### When to Reference Which Document

- **"What should I build?"** → This SPEC.md
- **"What are the quality standards?"** → `docs/implementation/specs/CONSTITUTION.md`
- **"How should I architect this?"** → `docs/implementation/plans/technical-architecture.md`
- **"How do I optimize token usage?"** → `docs/implementation/guidance/mcp-token-optimization.md`
- **"What's the REST API contract?"** → `docs/implementation/specs/api-contract.md`

---

**End of Specification**

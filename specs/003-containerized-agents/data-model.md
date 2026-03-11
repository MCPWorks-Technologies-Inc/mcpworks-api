# Data Model: MCPWorks Containerized Agents

**Branch**: `003-containerized-agents` | **Date**: 2026-03-11

## Entity Relationship Overview

```
Account (1) ──── (*) Agent
                      │
                      ├── (1) Namespace (dedicated, auto-created)
                      ├── (*) AgentSchedule
                      ├── (*) AgentWebhook
                      ├── (*) AgentRun
                      ├── (*) AgentState
                      └── (*) AgentChannel
```

## Entities

### Agent

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, auto-generated | Unique agent identifier |
| account_id | UUID | FK → accounts.id, NOT NULL | Owning account |
| namespace_id | UUID | FK → namespaces.id, NOT NULL | Dedicated namespace |
| name | VARCHAR(63) | NOT NULL, UNIQUE(account_id, name) | Agent name (DNS-safe) |
| display_name | VARCHAR(255) | nullable | Human-readable label |
| container_id | VARCHAR(255) | nullable | Docker container ID |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'creating' | Lifecycle state |
| ai_engine | VARCHAR(50) | nullable | Provider: anthropic, openai, google, openrouter |
| ai_model | VARCHAR(100) | nullable | Model ID string |
| ai_api_key_encrypted | BYTEA | nullable | AES-256-GCM encrypted API key |
| ai_api_key_dek_encrypted | BYTEA | nullable | KEK-wrapped DEK for this agent |
| memory_limit_mb | INTEGER | NOT NULL, DEFAULT 256 | Container RAM limit |
| cpu_limit | FLOAT | NOT NULL, DEFAULT 0.25 | Container CPU limit (vCPUs) |
| system_prompt | TEXT | nullable | Optional system prompt for AI mode |
| enabled | BOOLEAN | NOT NULL, DEFAULT true | Soft-disable flag |
| cloned_from_id | UUID | FK → agents.id, nullable | Source agent if cloned |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW(), ON UPDATE | Last modification |

**Status values**: `creating`, `running`, `stopped`, `error`, `destroying`

**State transitions**:
```
creating → running → stopped → running (cycle)
                  → error → stopped (admin restart)
                  → destroying → (deleted)
running → destroying → (deleted)
stopped → destroying → (deleted)
```

**Validation rules**:
- `name`: lowercase alphanumeric + hyphens, 1-63 chars, must start/end with alphanumeric (same as namespace validation)
- `memory_limit_mb`: must match tier allocation (256, 512, 1024, 2048)
- `cpu_limit`: must match tier allocation (0.25, 0.5, 1.0, 2.0)
- `ai_engine`: if set, `ai_model` and `ai_api_key_encrypted` must also be set

### AgentSchedule

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, auto-generated | Schedule identifier |
| agent_id | UUID | FK → agents.id, ON DELETE CASCADE | Parent agent |
| function_name | VARCHAR(255) | NOT NULL | Target function to execute |
| cron_expression | VARCHAR(255) | NOT NULL | Standard 5-field cron expression |
| timezone | VARCHAR(50) | NOT NULL, DEFAULT 'UTC' | IANA timezone |
| failure_policy | JSONB | NOT NULL | Required strategy: continue, auto_disable, backoff |
| enabled | BOOLEAN | NOT NULL, DEFAULT true | Active/inactive toggle |
| consecutive_failures | INTEGER | NOT NULL, DEFAULT 0 | Failure counter for policy enforcement |
| last_run_at | TIMESTAMPTZ | nullable | Last execution time |
| next_run_at | TIMESTAMPTZ | nullable | Next scheduled execution |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Creation timestamp |

**Validation rules**:
- `cron_expression`: must parse as valid 5-field cron; minimum interval enforced per tier (5 min / 30 sec / 15 sec)
- `failure_policy`: required JSON with `strategy` field; if `auto_disable`, requires `max_failures`; if `backoff`, requires `backoff_factor`
- `function_name`: must reference an existing function in the agent's namespace

**Failure policy schema**:
```json
{
  "strategy": "auto_disable",
  "max_failures": 5
}
// OR
{
  "strategy": "continue"
}
// OR
{
  "strategy": "backoff",
  "backoff_factor": 2.0,
  "max_interval_seconds": 3600
}
```

### AgentWebhook

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, auto-generated | Webhook identifier |
| agent_id | UUID | FK → agents.id, ON DELETE CASCADE | Parent agent |
| path | VARCHAR(255) | NOT NULL, UNIQUE(agent_id, path) | URL path segment |
| handler_function_name | VARCHAR(255) | NOT NULL | Function to invoke |
| secret_hash | VARCHAR(255) | nullable | Argon2id hash of webhook secret |
| enabled | BOOLEAN | NOT NULL, DEFAULT true | Active/inactive toggle |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Creation timestamp |

**Validation rules**:
- `path`: alphanumeric + hyphens + slashes, no leading/trailing slashes, 1-255 chars
- `handler_function_name`: must reference an existing function in the agent's namespace
- `secret_hash`: if provided, webhook requests must include matching secret

### AgentRun

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, auto-generated | Run identifier |
| agent_id | UUID | FK → agents.id, ON DELETE CASCADE | Parent agent |
| trigger_type | VARCHAR(20) | NOT NULL | One of: cron, webhook, manual, ai |
| trigger_detail | VARCHAR(255) | nullable | Cron expression or webhook path |
| function_name | VARCHAR(255) | nullable | Function that was executed |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'running' | Execution status |
| started_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Execution start |
| completed_at | TIMESTAMPTZ | nullable | Execution end |
| duration_ms | INTEGER | nullable | Execution duration |
| result_summary | TEXT | nullable | PII-scrubbed result |
| error | TEXT | nullable | Error message if failed |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Record creation |

**Status values**: `running`, `completed`, `failed`, `timeout`

**Retention**: auto-purged based on tier — 7 days (builder), 30 days (pro), 90 days (enterprise)

**Indexes**: `(agent_id, created_at DESC)` for efficient listing; `(created_at)` for retention purging

### AgentState

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, auto-generated | State entry identifier |
| agent_id | UUID | FK → agents.id, ON DELETE CASCADE | Parent agent |
| key | VARCHAR(255) | NOT NULL, UNIQUE(agent_id, key) | State key |
| value_encrypted | BYTEA | NOT NULL | AES-256-GCM encrypted value |
| value_dek_encrypted | BYTEA | NOT NULL | KEK-wrapped DEK |
| size_bytes | INTEGER | NOT NULL | Unencrypted value size |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Last update |

**Validation rules**:
- `key`: alphanumeric + underscores + hyphens + dots, 1-255 chars
- Total `size_bytes` across all keys for an agent must not exceed tier limit: 10 MB (builder), 100 MB (pro), 1 GB (enterprise)
- On PUT: calculate `SUM(size_bytes)` for agent; reject with 413 if adding new value exceeds limit

### AgentChannel

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, auto-generated | Channel identifier |
| agent_id | UUID | FK → agents.id, ON DELETE CASCADE | Parent agent |
| channel_type | VARCHAR(20) | NOT NULL, UNIQUE(agent_id, channel_type) | discord, slack, whatsapp, email |
| config_encrypted | BYTEA | NOT NULL | AES-256-GCM encrypted config |
| config_dek_encrypted | BYTEA | NOT NULL | KEK-wrapped DEK |
| enabled | BOOLEAN | NOT NULL, DEFAULT true | Active/inactive toggle |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Creation timestamp |

**Validation rules**:
- `channel_type`: must be one of: discord, slack, whatsapp, email
- One channel per type per agent (unique constraint)

### Function (existing — additions)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| locked | BOOLEAN | NOT NULL, DEFAULT false | Prevents non-admin modification |
| locked_by | UUID | FK → users.id, nullable | Who locked the function |
| locked_at | TIMESTAMPTZ | nullable | When the function was locked |

### SubscriptionTier Enum (existing — additions)

New values added to `SubscriptionTier` and `UserTier` enums:
- `builder-agent`
- `pro-agent`
- `enterprise-agent`

## Tier Configuration Reference

| Tier | Agents | RAM | CPU | Min Schedule | State | Run Retention | Webhook Size |
|------|--------|-----|-----|-------------|-------|---------------|-------------|
| builder-agent | 1 | 256 MB | 0.25 vCPU | 5 min | 10 MB | 7 days | 256 KB |
| pro-agent | 5 | 512 MB | 0.5 vCPU | 30 sec | 100 MB | 30 days | 1 MB |
| enterprise-agent | 20 | 1 GB | 1.0 vCPU | 15 sec | 1 GB | 90 days | 5 MB |

## Migration Plan

All schema changes delivered as a single Alembic migration per phase:

- **Phase A migration**: `agents`, `agent_runs` tables; `SubscriptionTier` enum extension; `Function.locked` columns
- **Phase B migration**: `agent_schedules`, `agent_webhooks` tables
- **Phase C migration**: `agent_state` table
- **Phase D migration**: `agent_channels` table

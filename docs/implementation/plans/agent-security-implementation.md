# Agent Security Implementation Plan

**Version:** 1.0.0
**Last Updated:** 2026-03-14
**Status:** Active
**Framework:** OWASP Top 10 for LLM Applications 2025

---

## Overview

This plan covers agent security controls for the mcpworks-api codebase. It covers P0 tasks (build before pilot users) and P1 tasks (build before public launch).

**Architecture context:** The security controls in this plan are enforced in the API layer — deterministically, not by the LLM. The LLM never decides what it's allowed to do; the API decides based on the agent's tool tier, the account's quotas, and the operation's risk level.

---

## P0-A: Per-Agent Tool Scoping (LLM06 Excessive Agency)

**Risk:** Agents currently have access to all MCP tools available to their account tier. A compromised agent (via prompt injection through webhook data, fetched content, etc.) can call `destroy_agent`, `delete_function`, or `delete_service` without restriction.

### Database Changes

**New column on `agents` table:**

```python
# alembic migration: add_agent_tool_tier
# File: src/mcpworks_api/models/agent.py

class Agent(Base):
    # ... existing fields ...
    tool_tier = Column(
        String(20),
        nullable=False,
        default="standard",
        server_default="standard"
    )
    # Values: "execute_only", "standard", "builder", "admin"
```

**Migration:**
```
alembic revision --autogenerate -m "Add tool_tier to agents table"
```

### Tool Tier Definitions

**New file: `src/mcpworks_api/core/tool_permissions.py`**

```python
from enum import Enum

class ToolTier(str, Enum):
    EXECUTE_ONLY = "execute_only"
    STANDARD = "standard"
    BUILDER = "builder"
    ADMIN = "admin"

TIER_TOOLS: dict[ToolTier, set[str]] = {
    ToolTier.EXECUTE_ONLY: {
        # Can only run functions — no management
        "execute",
    },
    ToolTier.STANDARD: {
        "execute",
        "get_agent_state",
        "set_agent_state",
        "delete_agent_state",
        "list_agent_state_keys",
        "list_functions",
        "describe_function",
        "list_services",
        "list_namespaces",
        "list_agents",
        "describe_agent",
        "list_schedules",
        "list_webhooks",
        "list_packages",
        "list_templates",
        "describe_template",
        "chat_with_agent",
    },
    ToolTier.BUILDER: {
        # Standard + create/update (but not delete)
        *TIER_TOOLS[ToolTier.STANDARD],
        "make_function",
        "update_function",
        "make_service",
        "make_namespace",
        "make_agent",
        "add_schedule",
        "add_webhook",
        "add_channel",
        "configure_agent_ai",
        "configure_mcp_servers",
        "lock_function",
        "unlock_function",
        "clone_agent",
    },
    ToolTier.ADMIN: {
        # Builder + destructive operations
        *TIER_TOOLS[ToolTier.BUILDER],
        "delete_function",
        "delete_service",
        "destroy_agent",
        "remove_agent_ai",
        "remove_schedule",
        "remove_webhook",
        "remove_channel",
        "start_agent",
        "stop_agent",
    },
}

# Tools that require two-step confirmation
CONFIRMATION_REQUIRED: set[str] = {
    "destroy_agent",
    "delete_service",
    "delete_function",
}

def is_tool_allowed(tool_tier: ToolTier, tool_name: str) -> bool:
    return tool_name in TIER_TOOLS.get(tool_tier, set())

def requires_confirmation(tool_name: str) -> bool:
    return tool_name in CONFIRMATION_REQUIRED
```

### Enforcement Point

**Where:** `src/mcpworks_api/mcp/create_handler.py` — the `handle_tool_call()` method (or equivalent dispatch point)

The check must happen BEFORE the tool handler runs. Every tool call flows through `CreateMCPHandler`, so we add authorization at the dispatch level:

```python
# In CreateMCPHandler.handle_tool_call() or _dispatch()
async def _authorize_tool(self, tool_name: str, agent: Agent | None):
    if agent is None:
        # Direct user call (not agent) — use account-level permissions
        return

    tier = ToolTier(agent.tool_tier)
    if not is_tool_allowed(tier, tool_name):
        await fire_security_event(
            event_type="tool_access_denied",
            severity="warning",
            actor_id=str(agent.id),
            details={"tool": tool_name, "tier": agent.tool_tier}
        )
        raise ToolAccessDenied(
            tool=tool_name,
            tier=agent.tool_tier,
            message=f"Agent '{agent.name}' (tier: {agent.tool_tier}) "
                    f"is not authorized to call '{tool_name}'"
        )
```

**Key files to modify:**
| File | Change |
|------|--------|
| `src/mcpworks_api/models/agent.py` | Add `tool_tier` column |
| `src/mcpworks_api/core/tool_permissions.py` | **New file** — tier definitions, `is_tool_allowed()` |
| `src/mcpworks_api/mcp/create_handler.py` | Add `_authorize_tool()` check in dispatch |
| `src/mcpworks_api/schemas/agent.py` | Add `tool_tier` to agent create/update schemas |
| `src/mcpworks_api/services/agent_service.py` | Pass `tool_tier` on create, support updates |

### Confirmation Token Flow

**Where:** `src/mcpworks_api/mcp/create_handler.py` — in handlers for `destroy_agent`, `delete_service`, `delete_function`

**Token storage:** Redis with 60-second TTL

```python
# In create_handler.py, before executing destructive ops
async def _require_confirmation(self, operation: str, target: str, account_id: str) -> dict:
    token = secrets.token_urlsafe(32)
    key = f"confirm:{account_id}:{operation}:{target}"
    await redis.setex(key, 60, token)
    await fire_security_event(
        event_type="destructive_op_requested",
        severity="info",
        actor_id=account_id,
        details={"operation": operation, "target": target}
    )
    return {
        "status": "confirmation_required",
        "confirmation_token": token,
        "expires_in": 60,
        "message": f"{operation}('{target}') is irreversible. "
                   f"Call again with confirmation_token to proceed."
    }

async def _verify_confirmation(self, operation: str, target: str, account_id: str, token: str) -> bool:
    key = f"confirm:{account_id}:{operation}:{target}"
    stored = await redis.get(key)
    if stored and stored == token:
        await redis.delete(key)
        await fire_security_event(
            event_type="destructive_op_confirmed",
            severity="info",
            actor_id=account_id,
            details={"operation": operation, "target": target}
        )
        return True
    return False
```

**Modify existing handlers:**
- `_destroy_agent()` — already has a `confirm` parameter; replace boolean with token flow
- `_delete_function()` — add confirmation_token parameter
- `_delete_service()` — add confirmation_token parameter

### Management Operation Rate Limits

**Where:** `src/mcpworks_api/middleware/rate_limit.py` — add management-specific limits

**New limits to add to the LIMITS config:**

```python
MANAGEMENT_LIMITS = {
    "make_function": (10, 60),      # 10 per minute
    "update_function": (20, 60),    # 20 per minute
    "delete_function": (5, 60),     # 5 per minute
    "destroy_agent": (2, 3600),     # 2 per hour
    "delete_service": (2, 3600),    # 2 per hour
    "configure_agent_ai": (5, 3600),# 5 per hour
}
```

**Enforcement:** Check in `CreateMCPHandler` before tool dispatch, using existing `RateLimiter.is_rate_limited()` with key pattern `mgmt:{account_id}:{tool_name}`.

**Burst protection:** If any account hits 3+ rate limits within 5 minutes on destructive ops, trigger a 15-minute cooldown on all destructive operations for that account.

---

## P0-B: Output Validation (LLM05 Improper Output Handling)

**Risk:** Sandbox code produces output that is returned to the LLM and may be passed to downstream systems. Output could contain XSS, SQL injection, shell commands, or leaked secrets.

### Output Size Limits

**Where:** `src/mcpworks_api/backends/sandbox.py` — in `execute()` method, after capturing stdout

```python
OUTPUT_SIZE_LIMITS = {
    "free": 256 * 1024,         # 256 KB
    "builder": 512 * 1024,     # 512 KB
    "pro": 1 * 1024 * 1024,    # 1 MB
    "enterprise": 5 * 1024 * 1024,  # 5 MB
}

def _enforce_output_limits(self, output: str, tier: str) -> str:
    max_size = OUTPUT_SIZE_LIMITS.get(tier, OUTPUT_SIZE_LIMITS["free"])
    if len(output.encode("utf-8")) > max_size:
        truncated = output[:max_size // 2]  # rough truncation
        return truncated + f"\n\n[OUTPUT TRUNCATED: exceeded {max_size // 1024}KB limit for {tier} tier]"
    return output
```

### Secret Pattern Scrubbing

**New file: `src/mcpworks_api/core/output_sanitizer.py`**

```python
import re

SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_API_KEY]"),
    (r"sk-proj-[a-zA-Z0-9_-]{50,}", "[REDACTED_API_KEY]"),
    (r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
    (r"ghp_[a-zA-Z0-9]{36}", "[REDACTED_GITHUB_TOKEN]"),
    (r"gho_[a-zA-Z0-9]{36}", "[REDACTED_GITHUB_TOKEN]"),
    (r"mcpw_[a-f0-9]{64}", "[REDACTED_MCPWORKS_KEY]"),
    (r"eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", "[REDACTED_JWT]"),
    (r"(postgres|postgresql|mysql|mongodb|redis|rediss)://[^\s\"']+", "[REDACTED_CONNECTION_URI]"),
    (r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]"),
    (r"(bearer|token|authorization)[:\s]+[a-zA-Z0-9_\-\.]{20,}", "[REDACTED_AUTH_TOKEN]"),
]

COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), r) for p, r in SECRET_PATTERNS]

def scrub_secrets(output: str) -> tuple[str, int]:
    """Returns (scrubbed_output, redaction_count)."""
    count = 0
    for pattern, replacement in COMPILED_PATTERNS:
        output, n = pattern.subn(replacement, output)
        count += n
    return output, count
```

**Integration point:** `src/mcpworks_api/backends/sandbox.py` — call `scrub_secrets()` on execution output before returning `ExecutionResult`. If `redaction_count > 0`, fire `security_event` type `secret_redacted`.

### Output Schema Validation

**Where:** `src/mcpworks_api/backends/sandbox.py` — post-execution, before returning result

The `FunctionVersion` model already has `output_schema` (JSON field). When set, validate the function's output against it:

```python
import jsonschema

def _validate_output_schema(self, output: str, schema: dict | None) -> tuple[bool, str | None]:
    if schema is None:
        return True, None
    try:
        parsed = json.loads(output)
        jsonschema.validate(parsed, schema)
        return True, None
    except json.JSONDecodeError:
        return False, "Output is not valid JSON"
    except jsonschema.ValidationError as e:
        return False, f"Output schema violation: {e.message}"
```

If validation fails, the output is still returned but with a warning header: `X-MCPWorks-Output-Validated: false`. The validation error is included in execution metadata.

**Key files to modify:**
| File | Change |
|------|--------|
| `src/mcpworks_api/core/output_sanitizer.py` | **New file** — secret scrubbing |
| `src/mcpworks_api/backends/sandbox.py` | Add output size limits, secret scrubbing, schema validation |
| `src/mcpworks_api/mcp/run_handler.py` | Pass output_schema from FunctionVersion to backend |

---

## P0-C: Compute Budget Controls (LLM10 Unbounded Consumption)

**Risk:** Agents on tight schedules (30s minimum) running resource-intensive sandbox code can exhaust infrastructure. Existing controls: nsjail cgroup limits (per-execution) and BillingMiddleware (monthly execution count). Missing: daily compute budgets and input size validation.

### Daily Compute Budget Tracking

**Where:** `src/mcpworks_api/middleware/billing.py` — extend `BillingMiddleware`

The existing BillingMiddleware tracks monthly execution counts. Add parallel tracking for daily CPU-seconds:

```python
DAILY_COMPUTE_BUDGETS = {
    "free": 900,            # 15 CPU-minutes
    "builder": 3600,        # 1 CPU-hour
    "pro": 14400,           # 4 CPU-hours
    "enterprise": 86400,    # 24 CPU-hours
}

DAILY_EXEC_LIMITS = {
    "free": 500,
    "builder": 2000,
    "pro": 10000,
    "enterprise": 50000,
}

async def track_compute(account_id: str, cpu_seconds: float, tier: str):
    date_key = datetime.utcnow().strftime("%Y-%m-%d")
    redis_key = f"compute:daily:{account_id}:{date_key}"

    current = await redis.incrbyfloat(redis_key, cpu_seconds)
    # Set expiry if this is the first increment today
    ttl = await redis.ttl(redis_key)
    if ttl == -1:
        await redis.expire(redis_key, 86400 * 2)  # 2-day expiry for safety

    budget = DAILY_COMPUTE_BUDGETS.get(tier, DAILY_COMPUTE_BUDGETS["free"])

    if current >= budget:
        await fire_security_event(
            event_type="compute_budget_exceeded",
            severity="high",
            actor_id=account_id,
            details={"current": current, "budget": budget, "tier": tier}
        )
        raise ComputeBudgetExceeded(account_id, current, budget)

    if current >= budget * 0.8:
        await fire_security_event(
            event_type="compute_budget_warning",
            severity="warning",
            actor_id=account_id,
            details={"current": current, "budget": budget, "pct": round(current / budget * 100)}
        )
```

**Integration:** Call `track_compute()` after each sandbox execution completes, using the actual CPU time reported by nsjail (from `ExecutionResult.duration_ms` converted to seconds).

**Pre-execution check:** Before dispatching to sandbox, check if the account has remaining daily budget. If not, return 429 immediately.

### Input Size Validation

**Where:** `src/mcpworks_api/mcp/create_handler.py` — at the top of each tool handler

**New file: `src/mcpworks_api/core/input_limits.py`**

```python
INPUT_LIMITS = {
    "code": 100 * 1024,              # 100 KB — function source code
    "execute_input": 1 * 1024 * 1024, # 1 MB — function execution input
    "agent_state_value": 10 * 1024 * 1024,  # 10 MB — single state value
    "agent_ai_config": 50 * 1024,     # 50 KB — system prompt / AI config
    "webhook_payload": 1 * 1024 * 1024, # 1 MB — incoming webhook
    "description": 10 * 1024,        # 10 KB — descriptions
    "input_schema": 50 * 1024,       # 50 KB — JSON schema
    "output_schema": 50 * 1024,      # 50 KB — JSON schema
}

def validate_input_size(field: str, value: str | bytes | None) -> None:
    if value is None:
        return
    limit = INPUT_LIMITS.get(field)
    if limit is None:
        return
    size = len(value.encode("utf-8")) if isinstance(value, str) else len(value)
    if size > limit:
        raise InputTooLarge(
            field=field,
            size=size,
            limit=limit,
            message=f"Input '{field}' is {size} bytes, max is {limit} bytes"
        )
```

**Apply in handlers:**
- `_make_function()` — validate `code`, `description`, `input_schema`, `output_schema`
- `_update_function()` — same
- `_set_agent_state()` — validate `value`
- `_configure_agent_ai()` — validate `system_prompt`
- `RunMCPHandler.handle_tool_call()` — validate execution input

### Anomaly Detection

**New file: `src/mcpworks_api/tasks/anomaly_detector.py`**

Run as a periodic task (every 5 minutes) via APScheduler (already in `tasks/scheduler.py`):

```python
async def detect_anomalies():
    """Run every 5 minutes. Flags accounts with unusual execution patterns."""
    async with get_session() as db:
        # Spike detection: >50 executions in 5 minutes
        results = await db.execute(text("""
            SELECT e.user_id, COUNT(*) as exec_count,
                   AVG(EXTRACT(EPOCH FROM (e.completed_at - e.started_at))) as avg_duration,
                   COUNT(*) FILTER (WHERE e.status = 'failed') as failures
            FROM executions e
            WHERE e.started_at > NOW() - INTERVAL '5 minutes'
            GROUP BY e.user_id
            HAVING COUNT(*) > 50
                OR COUNT(*) FILTER (WHERE e.status = 'failed')::float / GREATEST(COUNT(*), 1) > 0.5
        """))

        for row in results:
            if row.exec_count > 50:
                await fire_security_event(
                    event_type="anomaly_spike",
                    severity="warning",
                    actor_id=str(row.user_id),
                    details={
                        "exec_count_5min": row.exec_count,
                        "avg_duration_sec": round(row.avg_duration, 2),
                    }
                )
            if row.failures / max(row.exec_count, 1) > 0.5:
                await fire_security_event(
                    event_type="anomaly_error_storm",
                    severity="warning",
                    actor_id=str(row.user_id),
                    details={
                        "total": row.exec_count,
                        "failures": row.failures,
                        "failure_rate": round(row.failures / row.exec_count * 100),
                    }
                )
```

**Key files to modify:**
| File | Change |
|------|--------|
| `src/mcpworks_api/middleware/billing.py` | Add daily compute budget tracking |
| `src/mcpworks_api/core/input_limits.py` | **New file** — input size validation |
| `src/mcpworks_api/mcp/create_handler.py` | Apply input size validation in tool handlers |
| `src/mcpworks_api/mcp/run_handler.py` | Apply execution input size validation |
| `src/mcpworks_api/tasks/anomaly_detector.py` | **New file** — periodic anomaly detection |
| `src/mcpworks_api/tasks/scheduler.py` | Register anomaly detection job |

---

## P1-A: Prompt Injection Defense (LLM01)

### Scheduled Execution Tool Restrictions

**Where:** `src/mcpworks_api/tasks/orchestrator.py` — when agent schedules trigger execution

When an agent runs on a schedule (no human present), enforce stricter tool access:

```python
async def execute_scheduled_run(agent: Agent, schedule: AgentSchedule):
    # Override tool_tier for scheduled runs
    effective_tier = min(agent.tool_tier, ToolTier.EXECUTE_ONLY)
    # ... execute with effective_tier ...
```

Scheduled runs default to `execute_only` unless the agent has been explicitly configured with `scheduled_tool_tier` (new column, defaults to `execute_only`).

**Rationale:** If an agent is compromised via indirect prompt injection (malicious webhook payload, poisoned fetched data), scheduled runs limit the blast radius. The agent can still run its functions but can't create/delete/modify infrastructure.

### External Data Tagging

**Where:** `src/mcpworks_api/mcp/run_handler.py` — when processing webhook-triggered executions

Add source metadata to execution context:

```python
{
    "source": "webhook" | "schedule" | "manual" | "ai",
    "source_verified": false,
    "received_at": "2026-03-15T10:00:00Z"
}
```

This metadata is passed to the sandbox as environment variables (`MCPWORKS_TRIGGER_SOURCE`, `MCPWORKS_TRIGGER_VERIFIED`) so function code can make trust decisions.

### Audit Trail Enhancement

**Where:** `src/mcpworks_api/models/security_event.py` — add new event types

Add the 11 new event types from the security specification to the security event system. All are already supported by the existing `SecurityEvent` model (it uses a string `event_type` field), but add documentation and ensure consistent usage.

**Key files to modify:**
| File | Change |
|------|--------|
| `src/mcpworks_api/models/agent.py` | Add `scheduled_tool_tier` column (default: execute_only) |
| `src/mcpworks_api/tasks/orchestrator.py` | Enforce scheduled tool tier |
| `src/mcpworks_api/mcp/run_handler.py` | Add trigger source metadata |

---

## P1-B: Sensitive Info Disclosure Defense (LLM02)

### Error Message Sanitization

**Where:** `src/mcpworks_api/middleware/error_handler.py`

Ensure all error responses:
- Never include stack traces in production
- Never expose database hostnames, internal IPs, or file paths
- Truncate error messages to 255 chars
- Replace nsjail-specific errors with generic messages

```python
NSJAIL_ERROR_MAP = {
    "nsjail: error: clone(CLONE_NEW": "Sandbox initialization failed",
    "nsjail: error: rlimit": "Resource limit exceeded",
    "nsjail: error: seccomp": "Blocked system call",
    "nsjail: error: cgroup": "Resource quota exceeded",
}
```

### Environment Variable Security

Already partially implemented via `mcp/env_passthrough.py` which blocks `MCPWORKS_*`, `AWS_*`, `INTERNAL_*` prefixes. Verify and harden:

- Confirm env vars are never included in `describe_agent` response
- Confirm env vars are never included in execution logs
- Confirm env vars are never returned in function output (covered by secret scrubbing in P0-B)

**Key files to verify:**
| File | Verify |
|------|--------|
| `src/mcpworks_api/mcp/create_handler.py` | `_describe_agent()` doesn't leak AI key |
| `src/mcpworks_api/mcp/env_passthrough.py` | Blocked prefixes are comprehensive |
| `src/mcpworks_api/middleware/error_handler.py` | Production errors are sanitized |

---

## New Files Summary

| File | Purpose |
|------|---------|
| `src/mcpworks_api/core/tool_permissions.py` | Tool tier definitions, authorization logic |
| `src/mcpworks_api/core/output_sanitizer.py` | Secret pattern scrubbing for function output |
| `src/mcpworks_api/core/input_limits.py` | Input size validation for all MCP tool inputs |
| `src/mcpworks_api/tasks/anomaly_detector.py` | Periodic anomaly detection (every 5 min) |

## Modified Files Summary

| File | Changes |
|------|---------|
| `src/mcpworks_api/models/agent.py` | Add `tool_tier`, `scheduled_tool_tier` columns |
| `src/mcpworks_api/schemas/agent.py` | Add tool tier fields to create/update schemas |
| `src/mcpworks_api/services/agent_service.py` | Handle tool tier on create/update |
| `src/mcpworks_api/mcp/create_handler.py` | Tool authorization, confirmation tokens, input validation, management rate limits |
| `src/mcpworks_api/mcp/run_handler.py` | Input size validation, output validation, trigger source metadata |
| `src/mcpworks_api/backends/sandbox.py` | Output size limits, secret scrubbing, schema validation post-execution |
| `src/mcpworks_api/middleware/billing.py` | Daily compute budget tracking |
| `src/mcpworks_api/middleware/rate_limit.py` | Management operation rate limits |
| `src/mcpworks_api/middleware/error_handler.py` | Error message sanitization |
| `src/mcpworks_api/tasks/scheduler.py` | Register anomaly detection job |
| `src/mcpworks_api/tasks/orchestrator.py` | Enforce scheduled tool tier |

## Migration Required

One Alembic migration:
```
alembic revision --autogenerate -m "Add tool_tier and scheduled_tool_tier to agents"
```

Adds:
- `agents.tool_tier` — VARCHAR(20), NOT NULL, DEFAULT 'standard'
- `agents.scheduled_tool_tier` — VARCHAR(20), NOT NULL, DEFAULT 'execute_only'

---

## Implementation Order

Build in this sequence to maximize safety at each step:

1. **`core/tool_permissions.py`** + **`core/input_limits.py`** — definitions only, no integration yet
2. **`core/output_sanitizer.py`** — definitions only
3. **DB migration** — add tool_tier columns
4. **`create_handler.py` tool authorization** — enforce tool tiers (biggest security win)
5. **`create_handler.py` confirmation tokens** — add to destructive ops
6. **`sandbox.py` output pipeline** — size limits + secret scrubbing
7. **`billing.py` daily compute budgets** — parallel Redis tracking
8. **`create_handler.py` + `run_handler.py` input validation** — apply limits
9. **`rate_limit.py` management limits** — per-tool rate limits
10. **`tasks/anomaly_detector.py`** — periodic detection
11. **`orchestrator.py` scheduled restrictions** — scheduled run tool tier enforcement

Steps 1-6 are the critical path. Steps 7-11 add defense-in-depth.

---

## Testing Requirements

Each new component needs:

| Component | Test Type | Coverage Target |
|-----------|-----------|----------------|
| Tool tier authorization | Unit (per-tier, per-tool) | 100% — every tool × every tier |
| Confirmation tokens | Unit + integration (Redis) | Token create, verify, expire |
| Output sanitizer | Unit (pattern matching) | Every secret pattern |
| Input size validation | Unit (boundary cases) | At limit, over limit, no limit |
| Compute budget tracking | Integration (Redis) | Track, warn, exceed |
| Anomaly detection | Integration (PostgreSQL) | Spike, error storm |
| Scheduled tool restrictions | Unit | Tier downgrade logic |

**Test files:**
- `tests/unit/test_tool_permissions.py`
- `tests/unit/test_output_sanitizer.py`
- `tests/unit/test_input_limits.py`
- `tests/integration/test_confirmation_tokens.py`
- `tests/integration/test_compute_budgets.py`
- `tests/integration/test_anomaly_detection.py`

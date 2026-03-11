# Research: MCPWorks Containerized Agents

**Branch**: `003-containerized-agents` | **Date**: 2026-03-11

## R1: Envelope Encryption (AES-256-GCM)

**Decision**: Implement envelope encryption in a new `core/encryption.py` module using `cryptography` library (already available via PyJWT dependency chain).

**Rationale**: The codebase has no data-at-rest encryption beyond password hashing (Argon2id). Agent state, AI API keys, and channel credentials all require encryption. Envelope encryption (KEK wraps DEK, DEK encrypts data) is the industry standard for multi-tenant key isolation.

**Pattern**:
- Platform KEK loaded from environment variable (`ENCRYPTION_KEK_B64`)
- Per-agent DEK generated on agent creation, encrypted with KEK, stored in `agents.ai_api_key_dek_encrypted`
- AES-256-GCM provides authenticated encryption (integrity + confidentiality)
- `cryptography.hazmat.primitives.ciphers.aead.AESGCM` for implementation

**Alternatives considered**:
- AWS KMS / HashiCorp Vault — too complex for Phase 1, single-droplet deployment
- Per-field encryption without envelope — no key rotation capability
- NaCl/libsodium — good but `cryptography` library already in dependency tree

## R2: Docker SDK Integration

**Decision**: Add `docker>=7.0.0` to dependencies. Use `docker.DockerClient.from_env()` for container management.

**Rationale**: Docker SDK is the spec-mandated interface for container lifecycle. The existing sandbox uses nsjail (Linux namespaces), which is correct for function execution but not suitable for long-running agent containers. Docker provides restart policies, resource limits, network management, and health checks.

**Key considerations**:
- API server container needs Docker socket access (`/var/run/docker.sock` volume mount)
- Security: Docker socket access = root-equivalent. Mitigate by validating all inputs before Docker calls, never passing user-controlled data to container commands
- The `mcpworks-agents` bridge network must be created once at startup if it doesn't exist

**Alternatives considered**:
- Podman — compatible API but less mature Python SDK
- containerd directly — too low-level for our needs
- Docker Compose — spec explicitly prohibits this

## R3: MCP Tool Registration Pattern

**Decision**: Add agent tools to `CreateMCPHandler` as static tools with tier-based visibility filtering.

**Rationale**: `CreateMCPHandler.get_tools()` returns a static list of management tools. Agent tools (make_agent, list_agents, etc.) are management operations, not dynamic function executions. The handler already has `_tier_notice()` for tier-aware descriptions.

**Implementation approach**:
- Add 18 agent tools to `TOOL_SCOPES` dict in `create_handler.py`
- Filter agent tools out of `get_tools()` response when user is not on an agent tier
- Agent tool dispatch follows existing pattern: `dispatch_tool()` → service method

**Alternatives considered**:
- Separate AgentMCPHandler — unnecessary complexity, breaks existing single-handler pattern
- Dynamic tool generation from DB — agent tools are fixed, not user-defined

## R4: Function Locking

**Decision**: Add `locked`, `locked_by`, `locked_at` columns to `functions` table via Alembic migration.

**Rationale**: The Function model has no locking mechanism. Adding three columns is minimal and follows the spec's design. Auth middleware check is 2 lines in the existing create endpoint handler.

**Implementation**:
- `locked: bool = False` (default)
- `locked_by: UUID | None` (FK to users)
- `locked_at: datetime | None`
- Check in function update/delete handlers: if `function.locked` and scope != 'admin', raise 403

## R5: Admin Endpoint Patterns

**Decision**: Follow existing `AdminUserId` dependency pattern for new agent admin endpoints.

**Rationale**: 18 admin endpoints already exist using `AdminUserId` from `dependencies.py`. Auth via `X-Admin-Key` header or JWT with admin email. Adding 6 new agent admin endpoints follows the established pattern exactly.

## R6: Agent Runtime Base Image

**Decision**: Build `mcpworks/agent-runtime:latest` as a separate Dockerfile in `agent-runtime/` directory.

**Rationale**: The agent container runs independently from the API server. It needs its own image with: Python 3.11 slim, httpx, apscheduler, fastapi, uvicorn, AI SDKs (anthropic, openai), discord.py, and the MCPWorks agent entrypoint.

**Build approach**:
- `agent-runtime/Dockerfile` — multi-stage build for minimal image size
- `agent-runtime/entrypoint.py` — starts FastAPI webhook listener, loads schedules, connects channels
- Built and tagged during CI/CD, pushed to container registry (or built locally on prod for Phase 1)

## R7: Networking Architecture

**Decision**: Single `mcpworks-agents` Docker bridge network. API container joins both the existing network and the agents network.

**Rationale**: Agent containers need to reach the API server (`http://mcpworks-api:8000`) and the internet, but NOT the database or Redis. A dedicated bridge network achieves this isolation.

**Implementation**:
- Create `mcpworks-agents` network in `AgentService.__init__()` if it doesn't exist
- API container added to this network (via docker-compose.prod.yml update)
- Agent containers created on this network only
- Database and Redis remain on the existing `mcpworks_default` network

## R8: Schedule Failure Policy

**Decision**: `AgentSchedule` model includes a `failure_policy` JSON column with the user's chosen strategy.

**Rationale**: Per clarification, failure policy is required at schedule creation. The policy is a structured object:
```json
{
  "strategy": "auto_disable",  // "continue" | "auto_disable" | "backoff"
  "max_failures": 5,           // for auto_disable
  "backoff_factor": 2.0        // for backoff
}
```

The agent runtime reads this policy and applies it locally. The API validates the policy structure at creation time.

## R9: Run Retention & Purging

**Decision**: Implement run retention via a periodic background task that deletes expired AgentRun records.

**Rationale**: With 15-second schedules, a single enterprise agent generates ~5.7M runs/month. Tier-based retention (7/30/90 days) keeps the table manageable. A daily cleanup task is sufficient.

**Implementation**:
- Background task runs daily (APScheduler on the API server, or a cron-triggered admin function)
- `DELETE FROM agent_runs WHERE created_at < NOW() - INTERVAL '{retention_days} days'`
- Retention days resolved from the agent's account tier

## R10: Webhook Payload Size Enforcement

**Decision**: Enforce payload size limits in the webhook ingress handler before forwarding to agent container.

**Rationale**: Per clarification, tier-based limits: 256 KB (builder), 1 MB (pro), 5 MB (enterprise). Enforcement at the API layer prevents oversized payloads from reaching agent containers.

**Implementation**:
- Check `Content-Length` header in webhook ingress handler
- If missing, read body with a streaming limit and abort if exceeded
- Return 413 Payload Too Large with tier limit info

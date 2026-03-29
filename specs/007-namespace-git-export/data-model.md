# Data Model: Namespace Git Export

**Feature**: 007-namespace-git-export
**Date**: 2026-03-26

## New Entities

### NamespaceGitRemote

One-to-one relationship with Namespace. Stores the Git push target for exports.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | Primary key |
| namespace_id | UUID | FK → namespaces.id, UNIQUE, ON DELETE CASCADE | Owning namespace |
| git_url | VARCHAR(500) | NOT NULL | HTTPS URL (e.g., `https://github.com/user/repo.git`) |
| git_branch | VARCHAR(100) | NOT NULL, DEFAULT 'main' | Target branch |
| token_encrypted | BYTEA | NOT NULL | PAT encrypted with DEK (AES-256-GCM) |
| token_dek_encrypted | BYTEA | NOT NULL | DEK encrypted with KEK |
| last_export_at | TIMESTAMPTZ | NULLABLE | Timestamp of last successful export |
| last_export_sha | VARCHAR(40) | NULLABLE | Git commit SHA of last export |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Record creation |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Last update |

**Indexes**:
- UNIQUE on `namespace_id` (one remote per namespace)

**Relationships**:
- `Namespace` has zero or one `NamespaceGitRemote`
- CASCADE delete: removing namespace removes its git remote config

## Serialization Format (Export)

These are not DB entities — they describe the YAML manifest format written to Git.

### namespace.yaml

```yaml
apiVersion: mcpworks/v1
kind: Namespace
metadata:
  name: string          # namespace name
  description: string   # nullable
  exported_at: datetime # ISO 8601
  exported_from: string # instance hostname
  mcpworks_version: string
```

### service.yaml

```yaml
apiVersion: mcpworks/v1
kind: Service
metadata:
  name: string
  description: string   # nullable
```

### function.yaml

```yaml
apiVersion: mcpworks/v1
kind: Function
metadata:
  name: string
  description: string   # nullable
spec:
  backend: enum         # code_sandbox | nanobot | github_repo
  language: enum        # python | typescript
  requirements: [string]  # package names
  tags: [string]
  public_safe: boolean
  locked: boolean
  input_schema: object  # JSON Schema
  output_schema: object # JSON Schema
  env:
    required: [string]  # env var names
    optional: [string]  # env var names
```

### agent.yaml

```yaml
apiVersion: mcpworks/v1
kind: Agent
metadata:
  name: string
  display_name: string  # nullable
spec:
  ai_engine: string     # nullable (not configured)
  ai_model: string      # nullable
  system_prompt: string  # nullable, literal block scalar
  tool_tier: string
  scheduled_tool_tier: string
  auto_channel: string  # nullable
  memory_limit_mb: integer
  cpu_limit: float
  heartbeat:
    enabled: boolean
    interval: integer   # nullable
  orchestration_limits: object  # nullable, opaque JSON
  mcp_servers: object   # nullable, opaque JSON
  schedules:
    - name: string
      cron: string
      enabled: boolean
  webhooks:
    - name: string
      enabled: boolean
  channels:
    - type: string      # discord | slack | whatsapp | email
      # config values are NEVER exported (secrets)
```

## Entity Mapping (Export → Import)

| DB Entity | Export Location | Notes |
|-----------|----------------|-------|
| Namespace | `namespace.yaml` | name, description |
| Service (NamespaceService) | `services/{name}/service.yaml` | name, description |
| Function | `services/{svc}/functions/{name}/function.yaml` | metadata + schemas |
| FunctionVersion (active) | `services/{svc}/functions/{name}/handler.py` or `handler.ts` | code only |
| Agent | `agents/{name}/agent.yaml` | config, schedules, webhooks |
| AgentSchedule | embedded in `agent.yaml` | cron, name, enabled |
| AgentWebhook | embedded in `agent.yaml` | name, enabled |
| AgentChannel | embedded in `agent.yaml` | type only (no config) |
| AgentState | NOT EXPORTED | encrypted, instance-specific |
| Agent AI API key | NOT EXPORTED | encrypted secret |
| Channel config | NOT EXPORTED | encrypted secret |
| Env var values | NOT EXPORTED | instance-specific |

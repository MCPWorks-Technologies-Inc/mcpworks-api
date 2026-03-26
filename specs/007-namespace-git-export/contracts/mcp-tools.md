# MCP Tool Contracts: Namespace Git Export

**Feature**: 007-namespace-git-export
**Endpoint**: `{namespace}.create.mcpworks.io/mcp`

All 6 tools are exposed on the create endpoint (management operations).

---

## configure_git_remote

**Description**: Configure a Git remote for this namespace. The namespace will push exports to this repository. One remote per namespace; calling again overwrites.

**Authorization**: Namespace owner only.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| git_url | string | yes | HTTPS Git URL (e.g., `https://github.com/user/repo.git`) |
| git_token | string | yes | Personal access token with push access |
| git_branch | string | no | Branch name (default: `main`) |

**Success response** (~80 tokens):
```json
{
  "status": "configured",
  "git_url": "https://github.com/user/repo.git",
  "git_branch": "main",
  "verified": true
}
```

**Error responses**:
- `git_url` not a valid HTTPS URL → 400
- `git ls-remote` fails with provided credentials → 400 with Git error message
- Not namespace owner → 403

---

## remove_git_remote

**Description**: Remove the Git remote configuration for this namespace.

**Authorization**: Namespace owner only.

**Parameters**:

*None (operates on the current namespace).*

**Success response** (~30 tokens):
```json
{
  "status": "removed"
}
```

**Error responses**:
- No remote configured → 404
- Not namespace owner → 403

---

## export_namespace

**Description**: Export the entire namespace to its configured Git remote. Serializes all services, functions (active version), and agents into YAML + code files, commits, and pushes.

**Authorization**: Namespace owner only.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| message | string | no | Commit message (default: `MCPWorks export: {namespace}`) |

**Success response** (~120 tokens):
```json
{
  "status": "exported",
  "commit_sha": "a1b2c3d4e5f6",
  "git_url": "https://github.com/user/repo.git",
  "git_branch": "main",
  "files_changed": 15,
  "summary": {
    "services": 3,
    "functions": 12,
    "agents": 2
  }
}
```

**Error responses**:
- No remote configured → 400 `"Configure a Git remote first with configure_git_remote"`
- Git push fails → 502 with Git error message
- Namespace empty → success (exports `namespace.yaml` only)
- Not namespace owner → 403

---

## export_service

**Description**: Export a single service to the namespace's configured Git remote. Only that service's functions are included.

**Authorization**: Namespace owner only.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| service | string | yes | Service name to export |
| message | string | no | Commit message |

**Success response** (~100 tokens):
```json
{
  "status": "exported",
  "commit_sha": "a1b2c3d4e5f6",
  "service": "utils",
  "files_changed": 5,
  "functions": 4
}
```

**Error responses**:
- Service not found → 404
- No remote configured → 400
- Not namespace owner → 403

---

## import_namespace

**Description**: Clone a Git repository and create a namespace from the export directory structure. Creates the namespace, all services, functions, and agent definitions.

**Authorization**: Write access (account-level for new namespace creation).

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| git_url | string | yes | HTTPS Git URL to clone |
| git_token | string | no | PAT for private repos |
| git_branch | string | no | Branch to clone (default: `main`) |
| name | string | no | Override namespace name (default: from `namespace.yaml`) |
| conflict | string | no | `fail` (default), `skip`, or `overwrite` |

**Success response** (~150 tokens):
```json
{
  "status": "imported",
  "namespace": "analytics",
  "created": {
    "services": 3,
    "functions": 12,
    "agents": 2
  },
  "skipped": {
    "services": 0,
    "functions": 0,
    "agents": 0
  },
  "warnings": [
    "Agent 'leadgenerator' needs AI API key configuration",
    "Agent 'leadgenerator' needs Discord channel configuration",
    "Function 'fetch-data' declares required_env: ['API_TOKEN']"
  ]
}
```

**Error responses**:
- Git clone fails → 502 with Git error message
- Invalid manifest format → 400 with validation errors
- Namespace already exists (conflict=fail) → 409
- Insufficient permissions → 403

---

## import_service

**Description**: Clone a Git repository and import a single service into an existing namespace.

**Authorization**: Write access to the target namespace.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| git_url | string | yes | HTTPS Git URL to clone |
| git_token | string | no | PAT for private repos |
| service | string | yes | Service name within the repo to import |
| namespace | string | yes | Target namespace |
| conflict | string | no | `fail` (default), `skip`, or `overwrite` |

**Success response** (~100 tokens):
```json
{
  "status": "imported",
  "service": "utils",
  "namespace": "analytics",
  "created": {
    "functions": 4
  },
  "skipped": {
    "functions": 0
  },
  "warnings": []
}
```

**Error responses**:
- Service not found in repo → 404
- Target namespace doesn't exist → 404
- Git clone fails → 502
- Insufficient permissions → 403

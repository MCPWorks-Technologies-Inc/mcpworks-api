# Namespace Git Export - Specification

**Version:** 0.1.0 (Draft)
**Created:** 2026-03-26
**Status:** Draft
**Spec Author:** Simon Carr
**Feature Branch:** `feature/namespace-git-export`

---

## Clarifications

### Session 2026-03-26

- Q: On re-export, should the repo get a full replacement or additive merge? → A: Full replacement — wipe repo working tree, write fresh snapshot, commit the diff. Git preserves history via normal diffing. MCPWorks is source of truth; no stale files from deleted functions.
- Q: One Git remote per namespace or multiple named remotes? → A: One remote per namespace. Keeps the model simple and unambiguous. Users needing multiple destinations can configure Git mirrors on the host side.
- Q: PAT scoped per-account or per-namespace? → A: Per-namespace. Each namespace stores its own PAT independently — different namespaces may push to different repos on different hosts.
- Q: Performance target covers serialization only or full Git round-trip? → A: Serialization only (< 5s). Git network time is outside MCPWorks's control.
- Q: Authorization model for export/import tools? → A: Owner only for configure_git_remote + export. Write access sufficient for import (import just creates entities, export exposes all function code to an external repo).

---

## 1. Overview

### 1.1 Purpose

Namespace Git Export allows users to export a MCPWorks namespace (or individual service) to a portable directory structure suitable for Git version control and cross-instance transfer.

### 1.2 User Value

Today, MCPWorks namespaces exist only as database records. If a user wants to back up their functions, move to a different instance, share their namespace publicly, or review function code in a PR — they can't. Export to Git solves all of these.

### 1.3 Success Criteria

**This spec is successful when:**
- [ ] A user can export a complete namespace to a directory with a single MCP tool call
- [ ] The exported directory can be committed to Git and pushed to GitHub without modification
- [ ] A user can import an exported directory into a fresh MCPWorks instance and get a working namespace
- [ ] Secrets (env var values, API keys, channel tokens) are never included in the export

### 1.4 Scope

**In Scope:**
- Configure a Git remote (URL + PAT) per namespace
- Export namespace to Git remote (serialize + commit + push)
- Export individual service to Git remote
- Import namespace from any Git URL (clone + deserialize + create)
- Import individual service from any Git URL
- Portable YAML manifest format for metadata
- Function code exported as standalone files (handler.py / handler.ts)
- Agent definitions (config, schedules, webhooks — no state, no secrets)
- Env var declarations (names only, never values)
- Provider-agnostic: any Git host that supports HTTPS + PAT

**Out of Scope:**
- Git-first workflow (editing in repo, auto-sync to MCPWorks) — future spec
- Auto-export on change (every mutation becomes a commit) — future spec
- Namespace marketplace / registry — future spec
- Agent state export (encrypted, instance-specific)
- Execution history export
- Account/user export
- SSH key auth for Git remotes (HTTPS + PAT is universal and sufficient)
- Git LFS (function code is text, no large binary support needed)

---

## 2. User Scenarios

### 2.1 Primary Scenario: Back Up a Namespace

**Actor:** Developer using Claude Code with MCPWorks MCP server
**Goal:** Export their namespace to a Git repository for version control
**Context:** Developer has a namespace `analytics` with 3 services and 12 functions

**Workflow:**
1. Developer stores a Git remote URL + PAT: "Configure my analytics namespace to push to `https://github.com/user/analytics-functions.git` with this token"
2. AI calls `configure_git_remote` tool with the URL and PAT (encrypted at rest)
3. Developer asks: "Export my analytics namespace to Git"
4. AI calls `export_namespace` tool with name `analytics`
5. MCPWorks serializes namespace → services → functions → agents into the export directory structure
6. MCPWorks commits and pushes to the configured remote (Git over HTTPS with PAT)
7. Developer sees the commit on GitHub/GitLab/wherever
8. Future changes: developer re-exports, MCPWorks commits the diff

**Success:** Remote repo contains all function code, schemas, and metadata. `git log` shows the export commit. `git diff` between exports shows meaningful changes.
**Failure:** Export fails with clear error if namespace doesn't exist, user lacks access, or Git push fails (bad PAT, repo not found).

### 2.2 Secondary Scenario: Move to a Self-Hosted Instance

**Actor:** Developer migrating from MCPWorks Cloud to self-hosted
**Goal:** Recreate their Cloud namespace on their own server
**Context:** Developer exported their namespace from Cloud, now importing to self-hosted

**Workflow:**
1. Developer connects AI to self-hosted instance's create endpoint
2. Developer asks: "Import the analytics namespace from `https://github.com/user/analytics-functions.git`"
3. AI calls `import_namespace` tool with the Git URL (and optional PAT for private repos)
4. MCPWorks clones the repo, reads the directory structure, creates namespace, services, functions, agents
5. MCPWorks reports: "Created namespace 'analytics' with 3 services, 12 functions, 2 agents"
6. Developer sets environment variable values and agent secrets (prompted for any declared `required_env`)

**Success:** All functions execute correctly on the new instance.
**Failure:** Import fails gracefully if namespace already exists (conflict), with option to merge or overwrite.

### 2.3 Tertiary Scenario: Export a Single Service

**Actor:** Developer sharing a utility service
**Goal:** Export just one service for sharing or reuse
**Context:** Developer has a `utils` service with helper functions they want to share

**Workflow:**
1. Developer asks: "Export the utils service from my analytics namespace to Git"
2. AI calls `export_service` tool with namespace `analytics`, service `utils`
3. MCPWorks commits only that service's functions and metadata to the configured remote
4. Developer shares the repo link

**Success:** Exported service can be imported into any namespace on any instance via its Git URL.

---

## 3. Functional Requirements

### 3.1 Export Format

**REQ-EXP-001: Directory Structure**
- **Description:** Export must produce a self-contained directory with a defined structure
- **Priority:** Must Have
- **Format:**

```
{namespace}/
  namespace.yaml              # Namespace metadata
  services/
    {service-name}/
      service.yaml            # Service metadata
      functions/
        {function-name}/
          function.yaml       # Function metadata, schemas, requirements
          handler.py          # Active version code (or handler.ts)
    ...
  agents/
    {agent-name}/
      agent.yaml              # Agent config (no secrets)
    ...
```

**REQ-EXP-002: Namespace Manifest**
- **Description:** `namespace.yaml` must contain namespace identity and metadata
- **Priority:** Must Have
- **Format:**

```yaml
apiVersion: mcpworks/v1
kind: Namespace
metadata:
  name: analytics
  description: Data analytics functions
  exported_at: "2026-03-26T12:00:00Z"
  exported_from: api.mcpworks.io
  mcpworks_version: "0.1.0"
```

**REQ-EXP-003: Function Manifest**
- **Description:** `function.yaml` must contain all metadata needed to recreate the function
- **Priority:** Must Have
- **Format:**

```yaml
apiVersion: mcpworks/v1
kind: Function
metadata:
  name: analyze-csv
  description: Parse CSV and return summary statistics
spec:
  backend: code_sandbox
  language: python
  requirements:
    - pandas
  tags:
    - data
    - analysis
  public_safe: false
  input_schema:
    type: object
    properties:
      csv_data:
        type: string
        description: Raw CSV content
    required:
      - csv_data
  output_schema:
    type: object
    properties:
      row_count:
        type: integer
      columns:
        type: array
        items:
          type: string
  env:
    required: []
    optional: []
```

**REQ-EXP-004: Function Code as Standalone Files**
- **Description:** Function code must be exported as `handler.py` or `handler.ts`, one file per function
- **Priority:** Must Have
- **Rationale:** Standalone files enable IDE editing, syntax highlighting, linting, and meaningful `git diff`

**REQ-EXP-005: Agent Manifest**
- **Description:** `agent.yaml` must contain agent configuration sufficient to recreate the agent (minus secrets)
- **Priority:** Must Have
- **Format:**

```yaml
apiVersion: mcpworks/v1
kind: Agent
metadata:
  name: leadgenerator
  display_name: Lead Generator
spec:
  ai_engine: openrouter
  ai_model: deepseek/deepseek-v3.2
  system_prompt: |
    You are the MCPWorks Lead Generator...
  tool_tier: standard
  scheduled_tool_tier: execute_only
  auto_channel: discord
  memory_limit_mb: 512
  cpu_limit: 0.5
  heartbeat:
    enabled: false
    interval: null
  orchestration_limits: null
  mcp_servers: null
  schedules:
    - name: daily-harvest
      cron: "0 9 * * *"
      enabled: true
  webhooks:
    - name: inbound-lead
      enabled: true
  channels:
    - type: discord
      # config values are secrets — not exported
      # on import, user must re-configure channel credentials
```

### 3.2 Git Remote Configuration

**REQ-GIT-001: Configure Git Remote**
- **Description:** MCP tool `configure_git_remote` stores a Git remote URL and credentials for a namespace. One remote per namespace; calling again overwrites the previous configuration.
- **Priority:** Must Have
- **Parameters:** `namespace`, `git_url` (HTTPS URL), `git_token` (personal access token), `git_branch` (default: `main`)
- **Storage:** URL stored in plaintext, token encrypted with envelope encryption (KEK/DEK) same as other secrets
- **Acceptance:** Remote configuration persisted. Token verified by a test `git ls-remote` before saving.
- **Rationale:** Git HTTPS + PAT works with every major host (GitHub, GitLab, Gitea, Bitbucket, self-hosted). No provider-specific OAuth. One remote keeps the model simple — users needing multiple destinations configure Git mirrors on the host side.

**REQ-GIT-002: Remove Git Remote**
- **Description:** MCP tool `remove_git_remote` deletes the stored Git remote configuration
- **Priority:** Must Have
- **Parameters:** `namespace`

### 3.3 Export Operations

**REQ-EXP-010: Export Namespace**
- **Description:** MCP tool `export_namespace` serializes a namespace and pushes to its configured Git remote
- **Priority:** Must Have
- **Parameters:** `namespace`, `message` (optional commit message)
- **Behavior:** Clones the remote, replaces all working tree contents (except `.git/`) with a fresh serialization, commits the diff, and pushes. If the remote repo is empty, creates initial commit. Full replacement ensures the repo always reflects the exact namespace state — deleted functions become file deletions in the commit.
- **Returns:** Commit SHA, files changed count, remote URL
- **Acceptance:** All services, functions (active version), and agents exported and pushed. No secrets in output.

**REQ-EXP-011: Export Service**
- **Description:** MCP tool `export_service` serializes a single service and pushes to a Git remote
- **Priority:** Should Have
- **Parameters:** `namespace`, `service`, `git_url` (optional, falls back to namespace remote), `message`
- **Acceptance:** Only the specified service's functions are exported and pushed.

### 3.4 Import Operations

**REQ-IMP-001: Import Namespace**
- **Description:** MCP tool `import_namespace` clones a Git repo and creates a namespace from the export directory
- **Priority:** Must Have
- **Parameters:** `git_url` (HTTPS URL), `git_token` (optional, for private repos), `git_branch` (default: `main`), `name` (optional override), `conflict` (`fail` | `skip` | `overwrite`, default `fail`)
- **Behavior:** Clones the repo to a temp directory, reads the export structure, creates all entities in a single DB transaction, cleans up the temp directory.
- **Acceptance:** Namespace, services, functions, and agents created. Missing env var values reported. Agent secrets (API keys, channel configs) reported as needing configuration.

**REQ-IMP-002: Import Service**
- **Description:** MCP tool `import_service` clones a Git repo and imports a service into an existing namespace
- **Priority:** Should Have
- **Parameters:** `git_url`, `git_token` (optional), `service` (name within the repo), `namespace` (target), `conflict` (`fail` | `skip` | `overwrite`)
- **Acceptance:** Functions created under the target namespace's service.

**REQ-IMP-003: Conflict Resolution**
- **Description:** Import must handle existing entities gracefully
- **Priority:** Must Have
- **Behavior:**
  - `fail` (default): abort if any entity already exists
  - `skip`: skip existing entities, create only new ones
  - `overwrite`: update existing entities with imported data (creates new function versions)

**REQ-IMP-004: Import Report**
- **Description:** Import must return a structured report of what was created, skipped, or failed
- **Priority:** Must Have
- **Format:**

```json
{
  "namespace": "analytics",
  "created": {"services": 3, "functions": 12, "agents": 2},
  "skipped": {"services": 0, "functions": 0, "agents": 0},
  "warnings": [
    "Agent 'leadgenerator' needs AI API key configuration",
    "Agent 'leadgenerator' needs Discord channel configuration",
    "Function 'fetch-data' declares required_env: ['API_TOKEN'] — set via environment variables"
  ]
}
```

### 3.4 Security Requirements

**REQ-SEC-001: No Secret Export**
- **Description:** Export must never include: env var values, agent AI API keys, agent channel configs (bot tokens), encrypted state values, user credentials
- **Priority:** Must Have
- **Rationale:** Exported directories will be committed to Git, potentially public repos. Secrets must stay on the instance.

**REQ-SEC-002: Env Var Declarations Only**
- **Description:** Export includes env var names (required_env, optional_env) but never their values
- **Priority:** Must Have

**REQ-SEC-003: Import Validation**
- **Description:** Import must validate all YAML manifests and function code before creating any entities. Reject malformed input.
- **Priority:** Must Have

**REQ-SEC-004: Authorization**
- **Description:** `configure_git_remote`, `remove_git_remote`, `export_namespace`, and `export_service` require namespace owner access. `import_namespace` and `import_service` require write access to the target namespace (or account-level access for creating new namespaces).
- **Priority:** Must Have
- **Rationale:** Export exposes all function code to an external repository — sensitive operation restricted to owners. Import creates entities, which is a standard write operation.

---

## 4. Non-Functional Requirements

### 4.1 Performance

- **Export serialization:** Must complete in < 5 seconds for namespaces with up to 100 functions (excludes Git network time, which depends on remote host and connection)
- **Import deserialization:** Must complete in < 10 seconds for namespaces with up to 100 functions (excludes Git clone time)
- **Token Efficiency:** Export tool response < 500 tokens (returns path + summary, not file contents)

### 4.2 Compatibility

- **YAML format:** Must be valid YAML 1.2, parseable by PyYAML and any standard YAML library
- **apiVersion field:** All manifests include `apiVersion: mcpworks/v1` for forward compatibility
- **Cross-version:** Import should handle missing optional fields gracefully (forward-compatible)

### 4.3 Reliability

- **Atomic export:** If export fails mid-way, partial directory is cleaned up
- **Atomic import:** If import fails mid-way, no partial entities are created (transaction rollback)

---

## 5. Constraints & Assumptions

### 5.1 Technical Constraints

- Git operations (clone, commit, push) run on the API server in a temp directory, cleaned up after each operation
- Requires `git` binary available in the API container (add to Dockerfile if not present)
- Git HTTPS + PAT auth only — no SSH key support (keeps implementation simple, PATs are universal)
- Code sandbox functions have their code in the DB; non-code-sandbox backends (github_repo) may not have exportable code — export their config only
- PAT stored with envelope encryption (same KEK/DEK pattern as all other secrets)

### 5.2 Assumptions

- MCPWorks-first: the database is the source of truth. Export is a snapshot, not a sync.
- Users will use standard Git tooling to version-control exports. MCPWorks does not manage the Git repo.
- Re-export overwrites the directory. Users rely on Git to see what changed.
- Agent state is not portable. Importing an agent starts it fresh.
- **Risk if wrong:** If users expect Git-first (edit in repo, push to deploy), this spec doesn't cover that. It's explicitly MCPWorks-first with Git as backup/transfer.

---

## 6. Error Scenarios & Edge Cases

### 6.1 Error: Namespace Not Found

**Trigger:** Export called with non-existent namespace
**Expected Behavior:** Return error with message "Namespace 'xyz' not found"
**Recovery:** User corrects the namespace name

### 6.2 Error: Git Push Failure

**Trigger:** Export serializes successfully but push fails (expired PAT, repo deleted, network error)
**Expected Behavior:** Return error with Git stderr message. Serialized data is discarded (temp directory cleaned up). No partial commits on the remote.
**Recovery:** User fixes credentials (`configure_git_remote`) or resolves the remote issue, then re-exports.

### 6.3 Error: Git Clone Failure

**Trigger:** Import cannot clone the source repo (bad URL, expired token, private repo without token)
**Expected Behavior:** Return error with Git stderr message. No entities created.
**Recovery:** User provides correct URL/token.

### 6.4 Error: Import Conflict

**Trigger:** Import finds existing namespace/service/function with same name
**Expected Behavior:** Behavior depends on `conflict` parameter (fail/skip/overwrite)
**Recovery:** User re-runs with appropriate conflict strategy

### 6.3 Edge Case: Empty Namespace

**Scenario:** Namespace exists but has no services or functions
**Expected Behavior:** Export creates directory with only `namespace.yaml`
**Rationale:** Valid state, should not error

### 6.4 Edge Case: Function with No Code

**Scenario:** Function uses a non-code-sandbox backend — no code to export
**Expected Behavior:** Export `function.yaml` with config but no `handler.py`. Note backend type in manifest.
**Rationale:** Not all backends have exportable code

### 6.5 Edge Case: Large System Prompts

**Scenario:** Agent has a 5000+ character system prompt
**Expected Behavior:** System prompt exported as YAML literal block scalar (`|`). No truncation.
**Rationale:** System prompts are the core of agent behavior; must be complete.

### 6.6 Edge Case: Binary or Non-UTF8 Content

**Scenario:** Function code contains non-UTF8 bytes
**Expected Behavior:** Export fails for that function with a clear error. Other functions still export.
**Rationale:** YAML and `.py`/`.ts` files must be valid text.

---

## 7. Token Efficiency Analysis

### 7.1 Tool Definitions

**Estimated tokens for tool schemas:**
- `configure_git_remote`: ~200 tokens (4 params)
- `remove_git_remote`: ~80 tokens (1 param)
- `export_namespace`: ~150 tokens (2 params)
- `export_service`: ~180 tokens (3 params)
- `import_namespace`: ~250 tokens (5 params)
- `import_service`: ~250 tokens (5 params)
- Total: ~1110 tokens for all 6 tools

### 7.2 Typical Responses

**Export response:** ~120 tokens (commit SHA, files changed, remote URL)
**Import response:** ~150 tokens (summary counts + warnings list)

Both well under the 500 token target.

---

## 8. Security Analysis

### 8.1 Threat Model

**Threat:** User exports namespace, commits to public GitHub repo
**Impact:** Confidentiality — if secrets were included, they'd be exposed
**Mitigation:** REQ-SEC-001 ensures no secrets are ever in the export
**Residual Risk:** Low — env var names are visible but not values

**Threat:** Malicious import directory with code injection in YAML
**Impact:** Integrity — could create functions with unexpected behavior
**Mitigation:** REQ-SEC-003 validates all input. Function code is always sandboxed at execution time.
**Residual Risk:** Low — code sandbox provides runtime isolation regardless of code content

### 8.2 PII/Sensitive Data

- Agent system prompts may contain business-sensitive instructions — user's responsibility to manage visibility
- Env var names may hint at integrations (e.g., `STRIPE_API_KEY`) — acceptable, no values exposed

---

## 9. Testing Requirements

### 9.1 Unit Tests

- Serialize/deserialize namespace → YAML → namespace round-trip
- Export produces correct directory structure for various namespace configurations
- Import creates correct DB entities from directory structure
- Conflict resolution (fail/skip/overwrite) behaves correctly
- No secrets in exported YAML (scan output for known patterns)

### 9.2 Integration Tests

- Export real namespace from test DB, import into fresh DB, verify equivalence
- Export namespace with agents, import, verify agent config (minus secrets)
- Export service, import into different namespace

### 9.3 E2E Tests

- Export via MCP tool → commit to git → import via MCP tool on fresh instance → execute function

---

## 10. Future Considerations

### 10.1 Phase 2: Git-First Workflow

- Watch a Git repo, auto-import on push (webhook-triggered)
- `mcpworks.yaml` at repo root defines which namespace to sync
- Bi-directional sync: MCP tool edits auto-commit back to repo
- "GitOps for functions" — edit handler.py in your IDE, push, namespace updates

### 10.2 Phase 2: Auto-Export on Change

- Option to auto-push to Git remote on every function create/update/delete
- Namespace acts as a live mirror to the Git repo
- Every MCP tool mutation becomes a Git commit

### 10.3 Phase 3: Namespace Registry

- Publish namespaces to a public registry
- `mcpworks install analytics/csv-tools` — like npm packages
- Versioned namespace releases
- Import from registry URL without needing a PAT

### 10.4 Known Limitations

- No incremental export (full snapshot each time) — acceptable for v1, Git handles diffing
- No agent state portability — by design, state is instance-specific
- No cross-version migration — import assumes same MCPWorks version; apiVersion field enables future migration

---

## 11. Spec Completeness Checklist

**Before moving to Plan phase:**

- [x] Clear user value proposition stated
- [x] Success criteria defined and measurable
- [x] All functional requirements enumerated
- [x] All constraints documented
- [x] Error scenarios identified
- [x] Security requirements specified
- [x] Performance requirements quantified
- [x] Token efficiency requirements stated
- [x] Testing requirements defined
- [ ] Observability requirements defined
- [x] Reviewed for Constitution compliance
- [ ] Logic checked (internally consistent)
- [ ] Peer reviewed

---

## 12. Approval

**Status:** Draft

**Approvals:**
- [ ] CTO (Simon Carr)

**Approved Date:** —
**Next Review:** —

---

## Changelog

**v0.1.0 (2026-03-26):**
- Initial draft

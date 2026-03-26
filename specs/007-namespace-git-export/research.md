# Research: Namespace Git Export

**Feature**: 007-namespace-git-export
**Date**: 2026-03-26

## R1: Git Library Choice — gitpython vs subprocess

**Decision**: Use subprocess (`git` binary) directly, not gitpython.

**Rationale**:
- gitpython is a wrapper around the git binary anyway — adds a dependency without reducing complexity
- subprocess calls are simpler to debug (exact commands visible in logs)
- The git binary is already needed in the container for clone/push; no point wrapping it
- Our operations are simple: clone, add, commit, push, ls-remote. No need for gitpython's object model.

**Alternatives considered**:
- gitpython: heavier dependency, abstracts away the commands we want to see in logs
- dulwich (pure Python git): no external binary needed, but immature HTTPS auth handling and poor PAT support
- pygit2 (libgit2 bindings): C dependency, complex build in Docker, overkill for our needs

## R2: YAML Library Choice

**Decision**: Use PyYAML (already a transitive dependency via multiple packages).

**Rationale**:
- Already available in the environment (no new dependency)
- `yaml.safe_dump` with `default_flow_style=False` produces clean, readable output
- YAML 1.1 (PyYAML's default) is sufficient; YAML 1.2 differences don't affect our use case

**Alternatives considered**:
- ruamel.yaml: better YAML 1.2 support and comment preservation, but adds a dependency for no practical benefit here
- toml: less readable for nested structures (JSON schemas in function manifests)
- JSON: valid but less human-readable for config files; YAML is the industry standard for Kubernetes-style manifests

## R3: Git Authentication — PAT Embedding

**Decision**: Embed PAT in the clone URL: `https://{token}@{host}/{owner}/{repo}.git`

**Rationale**:
- Universal across all Git hosts (GitHub, GitLab, Gitea, Bitbucket, self-hosted)
- No credential helper configuration needed
- Token only exists in memory during the operation (temp directory + subprocess)
- The URL is never logged — structlog scrubs it before output

**Security considerations**:
- PAT must not appear in Git config files on disk — use URL-embedded auth only
- Temp directories must be cleaned up even on failure (try/finally)
- subprocess calls must not log the full URL (redact token in structured logs)
- PAT stored in DB with envelope encryption (existing KEK/DEK pattern)

**Alternatives considered**:
- Git credential helper: requires filesystem configuration, more moving parts
- SSH keys: not universal (some hosts charge for SSH access), more complex key management
- OAuth device flow: provider-specific, high complexity, poor fit for server-side operations

## R4: Temp Directory Management

**Decision**: Use Python's `tempfile.TemporaryDirectory` with explicit cleanup.

**Rationale**:
- Automatically cleaned up on context manager exit (even on exceptions)
- Unique per-operation (no collision between concurrent exports)
- No persistent disk usage

**Pattern**:
```python
with tempfile.TemporaryDirectory(prefix="mcpworks-export-") as tmpdir:
    # clone, serialize, commit, push
    # tmpdir automatically deleted on exit
```

## R5: Export Commit Strategy

**Decision**: Clone remote → delete all tracked files → write fresh snapshot → commit diff → push.

**Rationale** (from clarification session):
- MCPWorks is source of truth; full replacement ensures no stale files
- Git handles diffing naturally — unchanged files show no diff in the commit
- Deleted functions appear as file deletions in the commit
- `git log -- path/to/handler.py` traces function history across exports

**Commit message format**:
```
MCPWorks export: {namespace} ({date})

{user-provided message or "Automated export"}

Exported by: MCPWorks {version}
Functions: {count}
Agents: {count}
```

## R6: Dockerfile — Git Binary

**Decision**: Add `git` to the existing Dockerfile.

**Rationale**: The API container needs the git binary for clone/commit/push operations. Alpine packages it as `git` (~10MB). Already common in container images.

**Implementation**: Add to the Dockerfile's `apt-get install` or `apk add` line (depending on base image stage).

## R7: Data Model — namespace_git_remotes Table

**Decision**: One row per namespace, storing URL (plaintext) + encrypted PAT + branch.

**Rationale**:
- One remote per namespace (clarification decision)
- PAT per namespace, not per account (clarification decision)
- URL in plaintext for display/debugging; PAT encrypted with existing envelope encryption
- Branch stored to support non-default branch names

**Schema**:
```
namespace_git_remotes:
  id: UUID (PK)
  namespace_id: UUID (FK → namespaces.id, UNIQUE)
  git_url: VARCHAR(500) NOT NULL
  git_branch: VARCHAR(100) NOT NULL DEFAULT 'main'
  token_encrypted: BYTEA NOT NULL
  token_dek_encrypted: BYTEA NOT NULL
  created_at: TIMESTAMPTZ NOT NULL
  updated_at: TIMESTAMPTZ NOT NULL
```

## R8: Import Validation Strategy

**Decision**: Validate all manifests before creating any DB entities.

**Rationale**: Spec requires atomic import (REQ-IMP-001). Validating upfront prevents partial creation followed by rollback on later validation failure.

**Validation order**:
1. Parse `namespace.yaml` — verify apiVersion, required fields
2. Walk `services/` — parse each `service.yaml` and `function.yaml`
3. Verify all `handler.py`/`handler.ts` files are valid UTF-8
4. Walk `agents/` — parse each `agent.yaml`
5. Check for name conflicts against existing DB state (based on conflict param)
6. If all valid → create entities in single DB transaction

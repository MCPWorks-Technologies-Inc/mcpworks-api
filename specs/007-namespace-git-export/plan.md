# Implementation Plan: Namespace Git Export

**Branch**: `007-namespace-git-export` | **Date**: 2026-03-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/007-namespace-git-export/spec.md`

## Summary

Enable MCPWorks namespaces to be exported directly to any Git repository (via HTTPS + PAT) and imported from any Git URL. MCPWorks serializes namespace → services → functions → agents into a portable YAML + code directory structure, commits, and pushes. Import clones and recreates all entities. Provider-agnostic — works with GitHub, GitLab, Gitea, Bitbucket, or any self-hosted Git.

## Technical Context

**Language/Version**: Python 3.11+ (existing codebase)
**Primary Dependencies**: FastAPI (existing), PyYAML, gitpython (or subprocess git calls)
**Storage**: PostgreSQL (existing — new `namespace_git_remotes` table), envelope encryption for PAT storage
**Testing**: pytest (existing)
**Target Platform**: Linux server (Docker container)
**Project Type**: Single backend project (extends existing mcpworks-api)
**Performance Goals**: Serialization < 5s for 100 functions (excludes Git network time)
**Constraints**: Git binary must be available in container; HTTPS + PAT only (no SSH)
**Scale/Scope**: Single-user export/import operations; not designed for concurrent exports of same namespace

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-First | PASS | Spec complete with 5 clarifications resolved |
| II. Token Efficiency | PASS | Export response ~120 tokens, import ~150 tokens. Tool schemas ~1110 tokens total for 6 tools |
| III. Transaction Safety | PASS | Import uses single DB transaction with rollback. Export is idempotent (full replacement). Git push is atomic. |
| IV. Provider Abstraction | PASS | Git HTTPS is provider-agnostic. PAT auth works with all hosts. No provider-specific code. |
| V. API Contracts & Tests | PASS | 6 MCP tools with defined schemas. Unit + integration + E2E test plan in spec. |

| Quality Standard | Status | Notes |
|-----------------|--------|-------|
| Code Quality | PASS | Will follow existing patterns (type hints, ruff, black) |
| Documentation | PASS | YAML manifest format is self-documenting; tool descriptions defined |
| Performance | PASS | Serialization-only SLA; Git network excluded |
| Security | PASS | REQ-SEC-001 through REQ-SEC-004 cover secrets, validation, and authorization |

**Gate: PASSED** — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/007-namespace-git-export/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── mcp-tools.md     # MCP tool contracts
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
src/mcpworks_api/
├── models/
│   └── namespace_git_remote.py    # New model: git remote config per namespace
├── services/
│   ├── git_export.py              # Serialization logic (namespace → YAML/code files)
│   ├── git_import.py              # Deserialization logic (YAML/code files → DB entities)
│   └── git_remote.py              # Git operations (clone, commit, push, ls-remote)
├── schemas/
│   └── git_export.py              # Pydantic schemas for export/import responses
└── mcp/
    └── create_handler.py          # Extend with 6 new MCP tools (existing file)

alembic/versions/
└── YYYYMMDD_000001_add_namespace_git_remotes.py  # Migration

tests/
├── unit/
│   ├── test_git_export.py         # Serialization round-trip tests
│   └── test_git_import.py         # Deserialization + conflict resolution tests
└── integration/
    └── test_git_operations.py     # Git clone/commit/push with test repo
```

**Structure Decision**: Extends existing mcpworks-api layout. Three new service modules separate concerns: serialization (export), deserialization (import), and Git operations (remote). One new model for the git remote config table.

## Complexity Tracking

No constitution violations to justify.

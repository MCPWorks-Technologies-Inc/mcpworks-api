# Tasks: Namespace Git Export

**Input**: Design documents from `/specs/007-namespace-git-export/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/mcp-tools.md, quickstart.md

**Tests**: Included per spec (Section 9 defines unit, integration, and E2E test requirements).

**Organization**: Tasks grouped by user story from spec.md. US1 = Back Up a Namespace (P1), US2 = Move to Self-Hosted / Import (P1), US3 = Export Single Service (P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Add git binary to container, new dependencies

- [x] T001 Add `git` to Dockerfile apt-get/apk install in Dockerfile (already present)
- [x] T002 Add `pyyaml` to dependencies in pyproject.toml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database model and core services that all user stories depend on

- [x] T003 Create NamespaceGitRemote model in src/mcpworks_api/models/namespace_git_remote.py per data-model.md schema (id, namespace_id, git_url, git_branch, token_encrypted, token_dek_encrypted, last_export_at, last_export_sha, created_at, updated_at)
- [x] T004 Create Alembic migration for namespace_git_remotes table in alembic/versions/
- [x] T005 [P] Create Pydantic schemas for export/import responses in src/mcpworks_api/schemas/git_export.py (ConfigureRemoteResponse, ExportResponse, ImportResponse per contracts/mcp-tools.md)
- [x] T006 [P] Create Git operations service in src/mcpworks_api/services/git_remote.py — subprocess wrapper with: clone_repo(url, token, branch, dest), commit_and_push(repo_dir, message, url, token, branch), ls_remote(url, token), all with structlog logging and PAT redaction
- [x] T007 Create namespace serializer in src/mcpworks_api/services/git_export.py — serialize_namespace(namespace, services, functions, agents) → writes YAML manifests + handler files to a directory per REQ-EXP-001 through REQ-EXP-005 format
- [x] T008 Create namespace deserializer in src/mcpworks_api/services/git_import.py — deserialize_namespace(directory) → returns parsed namespace, services, functions, agents data structures; validate_export(directory) → raises on malformed input per REQ-SEC-003

**Checkpoint**: Foundation ready — all user stories can begin

---

## Phase 3: User Story 1 — Back Up a Namespace (Priority: P1) MVP

**Goal**: A user can configure a Git remote for their namespace and export the full namespace (services, functions, agents) with a single MCP tool call. The export commits and pushes to the configured remote.

**Independent Test**: Call `configure_git_remote` with a test repo URL, then call `export_namespace`. Verify the remote repo contains the correct directory structure with namespace.yaml, service.yaml, function.yaml, and handler.py files. Verify no secrets in any exported file.

### Tests for User Story 1

- [ ] T009 [P] [US1] Unit test for serializer round-trip in tests/unit/test_git_export.py — serialize a namespace with 2 services, 3 functions, 1 agent; verify directory structure matches REQ-EXP-001; verify YAML is valid; verify handler.py content matches DB code; verify no secrets (scan for patterns from credential scanner)
- [ ] T010 [P] [US1] Unit test for Git operations in tests/unit/test_git_remote.py — test PAT redaction in log output; test URL construction; test ls_remote error handling

### Implementation for User Story 1

- [ ] T011 [US1] Implement `configure_git_remote` MCP tool handler in src/mcpworks_api/mcp/create_handler.py — validate HTTPS URL, call ls_remote to verify credentials, encrypt PAT with envelope encryption, upsert NamespaceGitRemote row; owner-only authorization per REQ-SEC-004
- [ ] T012 [US1] Implement `remove_git_remote` MCP tool handler in src/mcpworks_api/mcp/create_handler.py — delete NamespaceGitRemote row; owner-only authorization
- [ ] T013 [US1] Implement `export_namespace` MCP tool handler in src/mcpworks_api/mcp/create_handler.py — load namespace + all services/functions/agents from DB, call serializer, clone remote, full replacement (delete working tree, write fresh snapshot), commit with message, push, update last_export_at/sha, return ExportResponse; owner-only authorization
- [ ] T014 [US1] Add structlog events for export operations in src/mcpworks_api/services/git_remote.py — log export_started, export_serialized, export_pushed, export_failed with namespace name and duration (never log PAT or URL with token)

**Checkpoint**: User can configure a remote and export a full namespace to Git

---

## Phase 4: User Story 2 — Import from Git (Priority: P1)

**Goal**: A user can import a namespace from any Git URL. MCPWorks clones the repo, reads the export directory, and creates all entities (namespace, services, functions, agents) in a single transaction.

**Independent Test**: Export a test namespace to a Git repo (from US1), then call `import_namespace` on a fresh account with the repo URL. Verify all entities created match the original. Verify warnings list missing secrets (AI keys, channel configs, env vars).

### Tests for User Story 2

- [ ] T015 [P] [US2] Unit test for deserializer in tests/unit/test_git_import.py — deserialize a directory with 2 services, 3 functions, 1 agent; verify parsed entities match expected; test validation rejects malformed YAML; test validation rejects missing required fields
- [ ] T016 [P] [US2] Unit test for conflict resolution in tests/unit/test_git_import.py — test fail mode raises on existing namespace; test skip mode skips existing entities; test overwrite mode creates new function versions

### Implementation for User Story 2

- [ ] T017 [US2] Implement `import_namespace` MCP tool handler in src/mcpworks_api/mcp/create_handler.py — clone repo to temp dir, call deserializer + validator, create namespace/services/functions/agents in single DB transaction, generate warnings for missing secrets and env vars, return ImportResponse with created/skipped/warnings; write-access authorization per REQ-SEC-004
- [ ] T018 [US2] Implement conflict resolution logic in src/mcpworks_api/services/git_import.py — handle fail/skip/overwrite per REQ-IMP-003; overwrite creates new function versions (not in-place update)

**Checkpoint**: Full round-trip works — export from one instance, import to another

---

## Phase 5: User Story 3 — Export/Import Single Service (Priority: P2)

**Goal**: A user can export or import a single service rather than the entire namespace.

**Independent Test**: Call `export_service` with a specific service name. Verify only that service's functions appear in the commit. Call `import_service` with the repo URL and service name into a different namespace. Verify functions created correctly.

### Implementation for User Story 3

- [ ] T019 [P] [US3] Implement `export_service` MCP tool handler in src/mcpworks_api/mcp/create_handler.py — serialize only the specified service and its functions, commit and push; owner-only authorization
- [ ] T020 [P] [US3] Implement `import_service` MCP tool handler in src/mcpworks_api/mcp/create_handler.py — clone repo, read only the specified service directory, create functions under the target namespace; write-access authorization

**Checkpoint**: Granular service-level export/import works

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Integration tests, documentation, edge cases

- [ ] T021 [P] Integration test: full export → import round-trip in tests/integration/test_git_operations.py — export namespace with services/functions/agents to a test Git repo (use local bare repo), import into fresh namespace, verify all entities match, verify function code executes correctly
- [ ] T022 [P] Integration test: re-export diff in tests/integration/test_git_operations.py — export, modify a function, re-export, verify Git commit shows only the changed function
- [ ] T023 Edge case handling in serializer/deserializer — empty namespace (namespace.yaml only), function with no code (activepieces backend), non-UTF8 code rejection, large system prompts (YAML literal block scalar)
- [ ] T024 Update docs/guide.md with Git export/import section — add to Table of Contents, document the 6 MCP tools with examples
- [ ] T025 Update docs/GETTING-STARTED.md with "Back up your namespace" section after the hello-world example

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 Export (Phase 3)**: Depends on Phase 2
- **US2 Import (Phase 4)**: Depends on Phase 2 (can run parallel with US1, but integration test needs US1)
- **US3 Service Export/Import (Phase 5)**: Depends on Phase 2 (reuses serializer/deserializer from US1/US2)
- **Polish (Phase 6)**: Depends on US1 + US2 minimum

### User Story Dependencies

- **US1 (Export)**: Can start after Foundational — no dependencies on other stories
- **US2 (Import)**: Can start after Foundational — independently testable with a pre-built test directory
- **US3 (Service)**: Can start after Foundational — but reuses serializer/deserializer, so best after US1+US2

### Within Each User Story

- Tests written first, verify they fail
- Models → services → MCP tool handlers
- Core implementation before logging/polish

### Parallel Opportunities

**Phase 2 parallel group**:
```
T005 (schemas) + T006 (git operations) — different files
```

**US1 test parallel group**:
```
T009 (serializer test) + T010 (git ops test) — different files
```

**US2 test parallel group**:
```
T015 (deserializer test) + T016 (conflict test) — same file but independent test classes
```

**US3 parallel group**:
```
T019 (export_service) + T020 (import_service) — different tools, same handler file but different functions
```

**Phase 6 parallel group**:
```
T021 (round-trip test) + T022 (diff test) + T024 (docs) + T025 (docs) — all independent
```

---

## Parallel Example: Foundational Phase

```bash
# After T003 + T004 (model + migration) complete:
Task: "T005 Create Pydantic schemas in src/mcpworks_api/schemas/git_export.py"
Task: "T006 Create Git operations service in src/mcpworks_api/services/git_remote.py"
# Then T007 + T008 can also run in parallel (different service files)
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (Dockerfile + dependency)
2. Complete Phase 2: Foundational (model, migration, schemas, services)
3. Complete Phase 3: US1 — configure remote + export
4. **STOP and VALIDATE**: Export a real namespace to a test GitHub repo
5. Demo: show git log, git diff between exports

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 (Export) → user can back up namespaces to Git → **MVP**
3. US2 (Import) → user can restore/migrate namespaces from Git
4. US3 (Service) → granular service-level operations
5. Polish → integration tests, docs, edge cases

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently testable after foundational phase
- Git operations use subprocess (not gitpython) per research.md R1
- PAT never logged — redact in all structlog output
- Full replacement on re-export per clarification session
- Commit after each task or logical group

# Implementation Plan: Environment Variable Passthrough

**Branch**: `002-env-passthrough` | **Date**: 2026-02-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-env-passthrough/spec.md`

## Summary

Enable sandbox-executed functions to access user-provided secrets (API keys, tokens, etc.) via a stateless HTTP header passthrough. Secrets flow from the MCP client's `.mcp.json` config → HTTP header → server-side validation and filtering → tmpfs file in nsjail sandbox → `os.environ` inside user code → destroyed on exit. Zero secrets are ever stored server-side. Functions declare which env vars they need (`required_env`/`optional_env`), and only declared vars are injected (least privilege).

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0+ (async), Pydantic v2, structlog, MCP Python SDK
**Storage**: PostgreSQL 15+ (env var names only — never values), tmpfs (transient env file during execution)
**Testing**: pytest (unit + integration)
**Target Platform**: Linux server (DigitalOcean droplet, Docker, nsjail)
**Project Type**: Single backend service
**Performance Goals**: < 1ms header parsing overhead, < 1ms file write to tmpfs, zero additional network calls
**Constraints**: Must not store env var values in database/logs/disk. Must be backward compatible (absent header = existing behavior).
**Scale/Scope**: No additional infrastructure. Purely code changes to existing execution pipeline.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Spec-First Development
- **Status**: PASS
- Spec complete at `docs/implementation/specs/env-passthrough.md` and `specs/002-env-passthrough/spec.md`
- Plan (this document) defines HOW
- Tasks will be generated next via `/speckit.tasks`

### II. Token Efficiency & Streaming
- **Status**: PASS
- `_env_status` response: ~80 tokens
- Error responses: ~60 tokens
- Tool description augmentation: ~15 tokens per function
- No streaming needed (all operations are synchronous and sub-millisecond)

### III. Transaction Safety & Security
- **Status**: PASS — Security is the core concern
- Zero persistence: env vars never touch database or disk (outside tmpfs)
- Validation blocklist prevents sandbox escape via env var override (PATH, LD_PRELOAD, PYTHONPATH)
- File-based injection avoids `/proc/self/environ` exposure
- structlog redaction processor as defense-in-depth
- Least privilege: only function-declared vars injected

### IV. Provider Abstraction & Observability
- **Status**: PASS
- `sandbox_env` parameter added to abstract `Backend.execute()` interface (not sandbox-specific)
- Metrics: `env_passthrough_requests_total`, `env_passthrough_errors_total`, `env_passthrough_vars_count`
- Logging: boolean flags and counts only (never names or values)
- Tracing spans in existing call chain

### V. API Contracts & Test Coverage
- **Status**: PASS
- Backward compatible: absent header = empty dict = existing behavior unchanged
- No breaking changes to existing tools
- New optional fields on `make_function`/`update_function`
- Test plan: 17+ unit tests, integration tests, security tests

## Project Structure

### Documentation (this feature)

```text
specs/002-env-passthrough/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research decisions
├── data-model.md        # Data model changes
├── quickstart.md        # Developer quickstart guide
├── contracts/
│   └── env-passthrough-api.md  # API contract
└── tasks.md             # Phase 2 output (next step)
```

### Source Code (files modified/created)

```text
src/mcpworks_api/
├── mcp/
│   ├── env_passthrough.py     # NEW: Header extraction, validation, blocklist
│   ├── transport.py           # MODIFIED: Extract header in call_tool(), pass to handler
│   └── run_handler.py         # MODIFIED: Filter env vars, _env_status tool, description augmentation
├── backends/
│   ├── base.py                # MODIFIED: Add sandbox_env param to Backend.execute()
│   └── sandbox.py             # MODIFIED: Write .sandbox_env.json to exec_dir
├── models/
│   └── function_version.py    # MODIFIED: Add required_env/optional_env columns
└── schemas/
    └── function.py            # MODIFIED: Add env fields to create/response schemas

deploy/nsjail/
├── spawn-sandbox.sh           # MODIFIED: Copy .sandbox_env.json into workspace
└── execute.py                 # MODIFIED: Read env file, inject os.environ, delete file

alembic/versions/
└── 20260219_000001_add_env_declarations_to_function_versions.py  # NEW

tests/unit/
└── test_env_passthrough.py    # NEW: Validation, filtering, blocklist tests
```

**Structure Decision**: Follows existing project layout. Single new module (`env_passthrough.py`) for the core logic. All other changes are modifications to existing files, keeping the change surface minimal.

## Architecture

### Data Flow

```
CLIENT                              SERVER                              SANDBOX
.mcp.json
  headers:
    X-MCPWorks-Env: base64(JSON)
         │
         │ HTTPS/TLS 1.3
         ▼
  MCPTransportMiddleware
  sets _current_request ContextVar
         │
         ▼
  call_tool() [transport.py:225]
  ├── extract_env_vars(request)    ← NEW: decode header, validate
  ├── authenticate(request, db)
  └── handler.dispatch_tool(name, args, sandbox_env=env_dict)
         │
         ▼
  dispatch_tool() [run_handler.py:152]
  ├── load function's required_env/optional_env from FunctionVersion
  ├── filter: only declared vars pass through
  ├── validate: all required vars present → else fast fail
  └── backend.execute(..., sandbox_env=filtered_dict)
         │
         ▼
  SandboxBackend._execute_nsjail() [sandbox.py:311]
  ├── write .sandbox_env.json to exec_dir
  └── spawn nsjail
         │
         ▼
  spawn-sandbox.sh
  ├── copy .sandbox_env.json into tmpfs workspace
  ├── rm source file from exec_dir
  └── run nsjail
         │
         ▼
  execute.py (inside nsjail)
  ├── read /sandbox/.sandbox_env.json
  ├── os.unlink() immediately
  ├── os.environ.update(parsed_env)
  └── exec(user_code)  ← user code reads os.environ["KEY"]
         │
  [process exits → tmpfs unmounted → gone]
```

### Key Design Decisions

1. **New module `env_passthrough.py`** — Isolated, testable validation logic. Not mixed into transport or handler code.

2. **ContextVar threading** — The `Request` is already in `_current_request` ContextVar. Env vars are extracted in `call_tool()` and passed as a parameter, not via ContextVar (explicit > implicit for security-sensitive data).

3. **Filtering in `dispatch_tool()`** — This is where we have the FunctionVersion loaded. Filter happens after auth, after function lookup, before backend execution. Clean separation.

4. **File-based injection** — Follows ORDER-003 exec_token pattern exactly. Proven in production. Same lifecycle: write → copy to workspace → read inside sandbox → delete → tmpfs unmount.

5. **Backward compatibility** — Every change is additive. Absent header = empty dict. NULL `required_env`/`optional_env` = function gets no user env vars (existing behavior). No existing tests break.

## Complexity Tracking

No constitution violations. No complexity justification needed.

| Aspect | Complexity | Justification |
|--------|-----------|---------------|
| New module | 1 new file (~150 lines) | Isolated validation logic, fully unit-testable |
| Schema changes | 2 new columns, 1 migration | Follows existing `requirements` column pattern |
| Pipeline threading | `sandbox_env` param through 4 functions | Same pattern as existing `extra_files` param |
| Sandbox changes | 6 lines in spawn-sandbox.sh, 10 lines in execute.py | Follows ORDER-003 exec_token pattern |

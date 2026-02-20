# Research: Environment Variable Passthrough

**Feature**: 002-env-passthrough
**Date**: 2026-02-19

## R1: MCP Header Transport Mechanism

**Decision**: Use `X-MCPWorks-Env` custom HTTP header with base64url-encoded JSON payload

**Rationale**:
- MCP Streamable HTTP transport natively supports custom `headers` in client config
- Claude Code and Claude Desktop both support `headers` field with `${env:VAR}` expansion
- The `env` field in MCP config is stdio-only — sets process-level env vars for locally spawned servers. For HTTP remotes, it has nowhere to go.
- A per-tool-call metadata approach would require MCP protocol extensions no client supports
- A `set_env` tool call would leak secrets into the LLM conversation context

**Alternatives considered**:
- MCP `env` config field: Only works for stdio transport, not HTTP remotes
- Per-tool-call metadata: Not part of MCP spec, would require custom client support
- `set_env` tool call: Exposes secrets in chat history — unacceptable
- Individual `X-MCPWorks-Env-{NAME}` headers: HTTP header name restrictions, proxy normalization issues. Will support as Phase 2 convenience format.

## R2: Sandbox Injection Mechanism

**Decision**: File-based injection via `.sandbox_env.json` on tmpfs, read by `execute.py`, deleted before user code runs

**Rationale**:
- Follows the proven ORDER-003 exec_token pattern already in production
- nsjail `--env` flags expose values in host `/proc/*/cmdline` and sandbox `/proc/self/environ`
- `os.environ[key] = value` in Python does NOT update `/proc/self/environ` (frozen at `execve(2)` time)
- tmpfs workspace is unmounted on cleanup, providing a hard second barrier

**Alternatives considered**:
- nsjail `--env` flags: Leaks to `/proc/self/environ` inside sandbox and `/proc/*/cmdline` on host
- nsjail `envar:` config: Static config file, not per-execution
- Process environment inheritance: Same `/proc` leakage problem
- Pipe/stdin injection: More complex, no benefit over file-based approach

## R3: Scoping Strategy

**Decision**: Namespace-level scope (per-connection), with function-level `required_env`/`optional_env` filtering server-side

**Rationale**:
- Each namespace is a separate MCP server entry in `.mcp.json` — 1:1 mapping to connection scope
- Service-level scoping from the client would couple client config to server internals
- Function-level filtering via declarations gives least-privilege without client complexity
- Users who need different keys per namespace already configure separate MCP server entries

**Alternatives considered**:
- Service-level client scoping: Requires client to know internal service topology
- Function-level client scoping: Impractical — client doesn't know which functions it will call at connect time
- No filtering (flat passthrough): Violates least privilege — functions would see vars they don't need

## R4: Data Model Extension

**Decision**: Add `required_env` and `optional_env` as `ARRAY(String)` columns on `function_versions` table

**Rationale**:
- FunctionVersion is immutable (append-only) — env declarations are versioned with the code
- ARRAY(String) is native PostgreSQL, efficient for small lists of env var names
- Only names stored, never values — no sensitive data in the database
- Consistent with existing `requirements` column pattern (also `ARRAY(String)`)

**Alternatives considered**:
- JSONB column: Over-engineered for a simple string list
- Separate `env_declarations` table: Unnecessary complexity for a per-version attribute
- Store on Function instead of FunctionVersion: Would break immutability guarantee

## R5: structlog Redaction

**Decision**: Add a structlog processor that strips fields containing env var data before output

**Rationale**:
- structlog processors run on every log event before serialization — global, reliable
- Pattern: strip any field named `sandbox_env`, `env_vars`, or matching `*_secret*`, `*_key*`, `*_token*`
- Existing project uses structlog throughout (not stdlib logging)

**Alternatives considered**:
- Log filtering at output level: Less reliable, could miss new code paths
- Never passing env data to logger: Defense-in-depth says assume developers make mistakes
- Both: Implementation uses both (never pass to logger + processor as safety net)

# Environment Variable Passthrough - Specification

**Version:** 0.1.0 (Draft)
**Created:** 2026-02-19
**Status:** Draft
**Spec Author:** Simon Carr
**Reviewers:** —

---

## 1. Overview

### 1.1 Purpose

Environment Variable Passthrough enables sandbox-executed functions to access user-provided secrets (API keys, tokens, database URLs) without mcpworks ever storing them. The platform acts as a stateless passthrough: secrets arrive in the HTTP request, exist in-memory for the duration of execution, and vanish when the sandbox exits.

### 1.2 User Value

Function authors need their code to call external APIs (OpenAI, Stripe, databases, etc.), but providing secrets to a hosted platform creates liability for both parties. Users want the simplicity of `os.environ["OPENAI_API_KEY"]` inside their function without trusting a third party to store their credentials. This feature solves that by keeping secrets on the client machine and passing them ephemerally per-request.

### 1.3 Success Criteria

**This spec is successful when:**
- [ ] Functions can read user-provided environment variables via `os.environ` inside the sandbox
- [ ] Zero secrets are persisted to disk, database, or logs at any point in the pipeline
- [ ] The client configuration experience requires no mcpworks-specific tooling (standard MCP headers)
- [ ] Functions declare their env var requirements, and the platform enforces least privilege
- [ ] Missing required env vars fail fast with a clear, actionable error before sandbox spawn

### 1.4 Scope

**In Scope:**
- HTTP header-based env var transport from MCP client to server
- Validation and filtering of env vars server-side
- Secure injection into nsjail sandbox via tmpfs file
- Function-level `required_env` / `optional_env` declarations
- Diagnostic `_env_status` tool for AI assistants to check configuration
- Env var requirements surfaced in `tools/list` descriptions
- structlog redaction of all env var data

**Out of Scope:**
- Server-side secret storage or vault (explicitly rejected)
- Encrypted environment profiles (Phase 2, see Section 11)
- Per-service or per-function scoping from the client side (namespace-level only)
- UI/dashboard for env var management (no management needed — nothing is stored)
- Activepieces or nanobot backend env var injection (code_sandbox only for Phase 1)

---

## 2. User Scenarios

### 2.1 Primary Scenario: Function Needs an API Key

**Actor:** Developer using Claude Code with an mcpworks namespace
**Goal:** Execute a function that calls the OpenAI API using their own API key
**Context:** Developer has published a `tools.search` function that requires `OPENAI_API_KEY`. They have their key locally.

**Workflow:**
1. Developer configures `.mcp.json` with the `X-MCPWorks-Env` header containing their base64-encoded env vars
2. Claude Code connects to `acme.run.mcpworks.io` and sends the header on every request
3. AI assistant calls `tools/list`, sees "Required env: OPENAI_API_KEY" in the tool description
4. AI assistant calls `tools.search` with arguments
5. Server extracts env vars from header, filters to only `OPENAI_API_KEY` (what the function declared), writes to tmpfs
6. Sandbox reads file, injects into `os.environ`, deletes file, runs user code
7. User code calls `openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])` and works
8. Sandbox exits, tmpfs unmounts, all traces gone

**Success:** Function executes with the API key, result returned, no secrets persisted
**Failure:** If `OPENAI_API_KEY` missing from header, immediate error: `"missing_env"` with list of required vars and instructions to configure

### 2.2 Secondary Scenario: AI Assistant Diagnoses Missing Env Vars

**Actor:** AI assistant (Claude Code) helping a user
**Goal:** Determine why a function call is failing due to missing configuration
**Context:** User tries to use a function but hasn't configured env vars yet

**Workflow:**
1. AI assistant calls `_env_status` diagnostic tool
2. Server compares declared requirements across all functions against what's in the header
3. Response shows: `configured: []`, `missing_required: ["OPENAI_API_KEY"]`, with actionable guidance
4. AI assistant tells the user exactly what to add to their `.mcp.json`
5. User adds the env var, reconnects, function works

**Success:** AI assistant can self-diagnose and guide user to fix configuration
**Failure:** N/A — `_env_status` always returns useful information

### 2.3 Tertiary Scenario: Multiple Namespaces with Different Keys

**Actor:** Developer managing two namespaces (`acme` and `beta`)
**Goal:** Pass different API keys to different namespaces
**Context:** Each namespace needs different credentials

**Workflow:**
1. Developer configures two MCP server entries in `.mcp.json`, one per namespace
2. Each entry has its own `X-MCPWorks-Env` header with namespace-specific secrets
3. When the AI assistant calls tools on `acme`, it sends `acme`'s env vars
4. When the AI assistant calls tools on `beta`, it sends `beta`'s env vars
5. No cross-contamination because each is a separate HTTP connection

**Success:** Complete isolation between namespaces via standard MCP multi-server config
**Failure:** N/A — scoping is inherent in the connection model

---

## 3. Functional Requirements

### 3.1 Core Capabilities

**REQ-ENV-001: Header-Based Transport**
- **Description:** The server must accept environment variables via a single `X-MCPWorks-Env` HTTP header containing a base64url-encoded JSON object
- **Priority:** Must Have
- **Rationale:** HTTP headers are the standard mechanism for MCP Streamable HTTP transport metadata. Every MCP client that supports remote servers already supports custom headers. Values never enter the LLM context window.
- **Acceptance:** Server correctly decodes base64 → JSON → dict from the header on every `tools/call` request

**REQ-ENV-002: Validation and Blocklist**
- **Description:** The server must validate env var names and values against strict rules and reject dangerous names
- **Priority:** Must Have
- **Rationale:** Prevents override of sandbox-critical variables (PATH, LD_PRELOAD, PYTHONPATH, etc.) that could compromise isolation
- **Acceptance:** Validation rules enforced per Section 3.2; blocked names rejected with clear error

**REQ-ENV-003: Function-Level Declaration**
- **Description:** Functions must declare `required_env` and `optional_env` lists. Only declared vars are injected into the sandbox.
- **Priority:** Must Have
- **Rationale:** Principle of least privilege. A function that only needs `OPENAI_API_KEY` should not receive `DATABASE_URL` even if the client sent it.
- **Acceptance:** Sandbox receives exactly the intersection of (client-provided vars) and (function-declared vars). Undeclared vars are silently dropped.

**REQ-ENV-004: Fast Fail on Missing Required Vars**
- **Description:** If a function declares `required_env: ["X"]` and the client did not provide `X`, execution must fail immediately before spawning a sandbox
- **Priority:** Must Have
- **Rationale:** Spawning a sandbox only to fail inside it wastes resources and returns an opaque error. Pre-flight validation gives a clear, actionable message.
- **Acceptance:** Error response includes `missing_required` list and configuration instructions

**REQ-ENV-005: Secure Sandbox Injection**
- **Description:** Env vars must be injected into the sandbox via a tmpfs file that is read once and deleted before user code runs
- **Priority:** Must Have
- **Rationale:** Using nsjail `--env` flags would expose vars in `/proc/self/environ` inside the sandbox and in host `/proc/*/cmdline`. File-based injection follows the established ORDER-003 exec_token pattern.
- **Acceptance:** After `execute.py` deletes the file and before user code runs, no filesystem artifact contains the env vars. User code accesses them via `os.environ["KEY"]`.

**REQ-ENV-006: Discovery via tools/list**
- **Description:** Env var requirements must be appended to tool descriptions in `tools/list` responses
- **Priority:** Must Have
- **Rationale:** AI assistants read tool descriptions to understand what a tool needs. Including env var requirements lets the assistant inform users proactively.
- **Acceptance:** Tool description includes `Required env: X, Y` and/or `Optional env: Z` lines when the function declares them

**REQ-ENV-007: Diagnostic Tool**
- **Description:** The run endpoint must expose an `_env_status` tool that reports which env vars are configured vs missing across all functions in the namespace
- **Priority:** Should Have
- **Rationale:** Gives AI assistants a way to diagnose configuration issues without trial-and-error execution failures
- **Acceptance:** Returns `configured`, `missing_required`, `missing_optional` lists with human-readable guidance

**REQ-ENV-008: Zero Persistence**
- **Description:** Env vars must never be written to database, log files, error messages, execution records, or any persistent storage
- **Priority:** Must Have
- **Rationale:** The entire liability model depends on this. If we store nothing, we can't leak anything.
- **Acceptance:** Audit of all code paths confirms no persistence. structlog processor strips env var fields. Execution model never receives env data.

### 3.2 Data Requirements

**Validation Rules:**

| Check | Limit | Rationale |
|-------|-------|-----------|
| Decoded payload size | 32 KB max | Prevents memory abuse. ~200 env vars at 160 bytes each. |
| Key count | 64 max | Sane upper bound for any function |
| Key name format | `^[A-Z][A-Z0-9_]{0,127}$` | Standard env var naming |
| Key name blocklist (exact) | `PATH`, `HOME`, `USER`, `SHELL`, `LANG`, `LC_ALL`, `LC_CTYPE`, `TMPDIR`, `TMP`, `TEMP`, `DISPLAY`, `HOSTNAME`, `IFS` | System-critical variables |
| Key name blocklist (prefix) | `LD_`, `PYTHON`, `NSJAIL`, `SSL_`, `MCPWORKS_INTERNAL_` | Sandbox infrastructure |
| Key name reserved prefix | `MCPWORKS_` | Platform-injected vars only |
| Value type | String only | Prevents injection via non-string JSON types |
| Value size | 8 KB per value | Covers PEM certificates |
| Null bytes in values | Rejected | Prevents C string truncation attacks |

**What data is stored (in database):**
- `required_env: list[str]` on FunctionVersion (env var *names* only, never values)
- `optional_env: list[str]` on FunctionVersion (env var *names* only, never values)

**What data is NOT stored:**
- Env var values (never touch database or disk outside tmpfs)
- Which env vars a user has configured (not our business)
- Env var usage history

### 3.3 Integration Requirements

**Upstream Dependencies:**
- MCP Streamable HTTP transport: client must support custom `headers` in server config (already standard)
- Starlette `Request` object: header extraction in transport middleware (already available)

**Downstream Consumers:**
- `SandboxBackend.execute()`: receives filtered env dict, writes to tmpfs
- `spawn-sandbox.sh`: copies env file into nsjail workspace
- `execute.py`: reads file, injects into `os.environ`, deletes file
- `tools/list` handler: reads `required_env`/`optional_env` from FunctionVersion

---

## 4. Non-Functional Requirements

### 4.1 Performance

- **Header parsing overhead:** < 1ms for 32 KB payload (base64 decode + JSON parse + validation)
- **Sandbox injection overhead:** < 1ms (single file write to tmpfs)
- **No additional network calls:** All processing is in-memory within the existing request path
- **Token efficiency:** `_env_status` response < 200 tokens. Error responses < 100 tokens.

### 4.2 Security

- **Authentication:** Env vars only processed for authenticated requests (existing auth gate applies)
- **Authorization:** Env vars scoped to the authenticated namespace. No cross-namespace access.
- **Data Protection:** In-memory only. Never encrypted at rest because never at rest. TLS 1.3 in transit (Caddy).
- **Audit:** Log *that* env vars were provided (boolean) and count, but never log names or values. Log env var validation failures (name only, not value).

### 4.3 Reliability

- **Availability:** Feature is stateless — no additional failure modes beyond existing execution path
- **Error Handling:** Invalid headers → 400 with clear validation error. Missing required vars → structured error before spawn. Malformed env file inside sandbox → silently skipped (defense-in-depth).
- **Recovery:** No state to recover. Each request is independent.
- **Data Integrity:** N/A — no data stored

### 4.4 Scalability

- **Current Scale:** No additional load. Header parsing is negligible.
- **Future Scale:** Per-request in-memory processing scales linearly. No shared state.
- **Bottlenecks:** None introduced. File write to tmpfs is nanoseconds.

---

## 5. Constraints & Assumptions

### 5.1 Technical Constraints

- Must use HTTP headers (not MCP `env` field): the `env` field in MCP config is stdio-only and sets process-level env vars for locally spawned servers. For HTTP remotes, it has nowhere to go.
- Must use file-based sandbox injection (not nsjail `--env`): nsjail `--env` exposes values in host `/proc/*/cmdline` and sandbox `/proc/self/environ`
- Must NOT use a separate `set_env` tool call: would leak secrets into LLM conversation context
- Base64 encoding required: HTTP header values cannot contain newlines; env var values may contain arbitrary strings

### 5.2 Business Constraints

- Timeline: Ship in A0 phase
- Resources: Solo developer
- No additional infrastructure cost (purely code changes to existing pipeline)

### 5.3 Assumptions

- MCP clients support custom `headers` in HTTP server config (verified: Claude Code, Claude Desktop both support this)
- Users can set shell environment variables and run base64 encoding (standard developer capability)
- Functions that need env vars are code_sandbox backend only (Activepieces has its own credential system)
- **Risk if wrong:** If a major MCP client drops header support, we'd need an alternative transport. Mitigation: headers are part of the MCP spec for Streamable HTTP.

---

## 6. Error Scenarios & Edge Cases

### 6.1 Error Scenario: Invalid Base64 Header

**Trigger:** Client sends `X-MCPWorks-Env: not-valid-base64!!!`
**Expected Behavior:** 400 error before tool dispatch
**User Experience:** `{"error": "invalid_env_header", "message": "X-MCPWorks-Env header is not valid base64"}`
**Recovery:** Fix the header value in `.mcp.json`
**Logging:** Log event `env_header_invalid` with request_id (no header value)
**Monitoring:** Counter metric `env_passthrough_errors{type="invalid_base64"}`

### 6.2 Error Scenario: Payload Too Large

**Trigger:** Decoded payload exceeds 32 KB
**Expected Behavior:** 400 error before tool dispatch
**User Experience:** `{"error": "env_payload_too_large", "message": "Env payload too large (35000 bytes, max 32768)"}`
**Recovery:** Reduce number of env vars
**Logging:** Log event `env_header_too_large` with size
**Monitoring:** Counter metric `env_passthrough_errors{type="payload_too_large"}`

### 6.3 Error Scenario: Blocked Env Var Name

**Trigger:** Client sends `{"PATH": "/evil", "OPENAI_API_KEY": "sk-..."}`
**Expected Behavior:** 400 error listing the blocked name
**User Experience:** `{"error": "env_name_blocked", "message": "Env var name 'PATH' is blocked (system variable)"}`
**Recovery:** Remove the blocked variable from config
**Logging:** Log event `env_name_blocked` with blocked name (safe to log — it's a name, not a value)
**Monitoring:** Counter metric `env_passthrough_errors{type="name_blocked"}`

### 6.4 Error Scenario: Missing Required Env Var

**Trigger:** Function declares `required_env: ["OPENAI_API_KEY"]` but client didn't send it
**Expected Behavior:** Structured error before sandbox spawn
**User Experience:**
```json
{
  "error": "missing_env",
  "required": ["OPENAI_API_KEY"],
  "provided": [],
  "action": "Add OPENAI_API_KEY to your MCP server X-MCPWorks-Env header"
}
```
**Recovery:** Add the missing variable to `.mcp.json` header config
**Logging:** Log event `env_missing_required` with function name and missing var names
**Monitoring:** Counter metric `env_passthrough_errors{type="missing_required"}`

### 6.5 Edge Case: No Env Vars Needed

**Scenario:** Function declares no `required_env` or `optional_env`, but client sends env vars anyway
**Expected Behavior:** Env vars silently dropped. Sandbox receives zero user env vars. Function executes normally.
**Rationale:** Least privilege. Functions that don't declare env needs don't get env vars.

### 6.6 Edge Case: Header Absent

**Scenario:** Client doesn't send `X-MCPWorks-Env` header at all
**Expected Behavior:** Empty env dict. Functions with no `required_env` work fine. Functions with `required_env` fail with `missing_env` error.
**Rationale:** Backward compatible. Existing clients without env vars configured continue working.

### 6.7 Edge Case: Function Outputs Its Own Env Vars

**Scenario:** User writes `result = dict(os.environ)` in their function code
**Expected Behavior:** Function returns the env vars in its output. This is allowed.
**Rationale:** The user provided these secrets themselves, from their own machine, to their own function. We are not protecting users from their own code — we are protecting our server from storing their secrets.

### 6.8 Edge Case: Env Var Value Contains Special Characters

**Scenario:** Database URL with `@`, `#`, newlines; PEM certificate with multi-line content
**Expected Behavior:** Works correctly. JSON encoding handles all Unicode. Base64 encoding handles the JSON.
**Rationale:** No character restrictions on values beyond null bytes and the 8 KB size limit.

---

## 7. Token Efficiency Analysis

### 7.1 Tool Definitions

**`_env_status` tool schema:** ~50 tokens
```json
{
  "name": "_env_status",
  "description": "Check which environment variables are configured and which are missing",
  "inputSchema": {"type": "object", "properties": {}}
}
```

**No additional tool schemas.** Env var requirements are embedded in existing tool descriptions, not separate tools.

### 7.2 Typical Responses

**`_env_status` response (all configured):** ~80 tokens
```json
{
  "configured": ["OPENAI_API_KEY", "DATABASE_URL"],
  "missing_required": [],
  "missing_optional": ["DEBUG"]
}
```

**`missing_env` error:** ~60 tokens
```json
{
  "error": "missing_env",
  "required": ["OPENAI_API_KEY"],
  "provided": [],
  "action": "Add OPENAI_API_KEY to your MCP server headers"
}
```

**Tool description overhead:** ~15 tokens per function with env declarations
```
\n\nRequired env: OPENAI_API_KEY\nOptional env: DEBUG
```

### 7.3 Worst Case

**`_env_status` with many functions:** ~300 tokens (20 functions with varying requirements)
**Mitigation:** Group by status, deduplicate var names across functions

---

## 8. Security Analysis

### 8.1 Threat Model

**Threat:** Env vars logged by structlog
**Impact:** Confidentiality
**Mitigation:** structlog processor strips any field matching `sandbox_env`, `env_vars`, or containing `secret`/`key`/`token` patterns from log output
**Residual Risk:** Low

**Threat:** Env vars visible in `/proc/self/environ` inside sandbox
**Impact:** Confidentiality (function code could read other env vars)
**Mitigation:** File-based injection via `os.environ[key] = value` in Python. Linux `/proc/self/environ` is frozen at `execve(2)` time — it does NOT reflect later `setenv(3)` calls. User-injected vars do not appear there.
**Residual Risk:** Low

**Threat:** Env vars persist in tmpfs after execution
**Impact:** Confidentiality
**Mitigation:** `execute.py` deletes `.sandbox_env.json` immediately after reading. Even if process crashes before deletion, `spawn-sandbox.sh` trap handler unmounts the entire tmpfs.
**Residual Risk:** Low

**Threat:** Cross-execution env var leakage
**Impact:** Confidentiality
**Mitigation:** Each execution gets a unique workspace directory backed by its own tmpfs mount. nsjail `mode: ONCE` — one process per invocation. Zero shared mutable state.
**Residual Risk:** Low

**Threat:** Malicious function exfiltrates env vars to external endpoint
**Impact:** Confidentiality (user's own secrets)
**Mitigation:** Existing sandbox network restrictions (free tier: zero outbound; builder tier: egress proxy allowlist). The user's own function, with the user's own secrets — the risk is accepted and documented.
**Residual Risk:** Medium (by design — user trusts their own functions)

**Threat:** Header intercepted in transit
**Impact:** Confidentiality
**Mitigation:** TLS 1.3 enforced by Caddy. HSTS headers.
**Residual Risk:** Low

**Threat:** Server memory retains env vars after response
**Impact:** Confidentiality
**Mitigation:** `sandbox_env` dict is a local variable in the async call chain. Released when coroutine completes. Python GC reclaims memory. For defense-in-depth, `dict.clear()` after writing file.
**Residual Risk:** Low

**Threat:** Blocked env var names bypassed via encoding tricks
**Impact:** Integrity (sandbox escape via LD_PRELOAD override)
**Mitigation:** Validation uses exact-match and prefix-match on the decoded string. No normalization that could be exploited. Key pattern `^[A-Z][A-Z0-9_]{0,127}$` prevents non-ASCII tricks.
**Residual Risk:** Low

### 8.2 PII/Sensitive Data

**What sensitive data is involved:**
- API keys, tokens, database URLs: In-memory only, never persisted, never logged
- Env var *names* (in function declarations): Stored in database. Not sensitive — they're labels like "OPENAI_API_KEY", not values.

### 8.3 Compliance

**Relevant regulations:**
- PIPEDA (Canada): No personal data stored. Env vars are transient. No compliance obligation for data we don't retain.
- GDPR (if EU customers): Same. Right to deletion is trivially satisfied — there's nothing to delete.
- SOC 2: "We don't store secrets" is the strongest possible audit answer for credential management controls.

---

## 9. Observability Requirements

### 9.1 Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `env_passthrough_requests_total` | Counter | Requests with `X-MCPWorks-Env` header present |
| `env_passthrough_vars_count` | Histogram | Number of env vars per request |
| `env_passthrough_errors_total` | Counter (labeled by `type`) | Validation failures by category |
| `env_passthrough_missing_required_total` | Counter | Executions blocked due to missing required vars |

### 9.2 Logging

**What must be logged:**
- `env_passthrough_received`: Boolean flag that env vars were present, count of vars (never names or values)
- `env_validation_error`: Error type and rejected key name (never value)
- `env_missing_required`: Function name, list of missing var names
- `env_injected`: Execution ID, count of vars injected into sandbox (never names or values)

**What must NOT be logged:**
- Env var values (never, under any circumstances)
- The raw `X-MCPWorks-Env` header content
- The decoded JSON payload
- The contents of `.sandbox_env.json`

### 9.3 Tracing

**Operations to trace:**
- Header extraction and validation (span within `call_tool`)
- Env var filtering by function declaration (span within `dispatch_tool`)
- File write to tmpfs (span within `_execute_nsjail`)

### 9.4 Alerting

| Alert | Condition | Severity |
|-------|-----------|----------|
| High env validation error rate | > 50 errors/minute | Warning |
| Blocked name attempted | Any `LD_*` or `PYTHON*` attempt | Info (may indicate attack) |

---

## 10. Testing Requirements

### 10.1 Unit Tests

**Must test:**
- `extract_env_vars()`: valid base64 JSON → correct dict
- `extract_env_vars()`: invalid base64 → `EnvPassthroughError`
- `extract_env_vars()`: valid base64, invalid JSON → `EnvPassthroughError`
- `extract_env_vars()`: payload too large → `EnvPassthroughError`
- `extract_env_vars()`: too many keys → `EnvPassthroughError`
- `extract_env_vars()`: blocked exact name (PATH) → `EnvPassthroughError`
- `extract_env_vars()`: blocked prefix name (LD_PRELOAD) → `EnvPassthroughError`
- `extract_env_vars()`: reserved prefix (MCPWORKS_) → `EnvPassthroughError`
- `extract_env_vars()`: invalid key format (lowercase, special chars) → `EnvPassthroughError`
- `extract_env_vars()`: value too large → `EnvPassthroughError`
- `extract_env_vars()`: null byte in value → `EnvPassthroughError`
- `extract_env_vars()`: absent header → empty dict
- `extract_env_vars()`: non-string value types → `EnvPassthroughError`
- Env filtering: function with `required_env` receives only those vars
- Env filtering: function with no declarations receives no user vars
- Env filtering: undeclared vars silently dropped
- Missing required var detection: correct error with var names

### 10.2 Integration Tests

**Must test:**
- Full pipeline: header → extraction → filtering → sandbox file write → sandbox execution → `os.environ` access in user code → result returned
- Dev mode (subprocess): env vars available in subprocess execution
- Error propagation: invalid header returns structured error to MCP client
- Backward compatibility: requests without `X-MCPWorks-Env` header work for functions with no env requirements

### 10.3 E2E Tests

**User workflows to test:**
- Happy path: Configure header, call function that needs env var, verify it works
- Missing env: Call function without required env var, verify actionable error
- `_env_status` tool: Verify it correctly reports configured vs missing vars
- `tools/list`: Verify env requirements appear in tool descriptions

### 10.4 Security Tests

**Must test:**
- Blocked names cannot bypass validation
- Env vars do not appear in execution records or logs
- Env vars do not persist after sandbox exit
- structlog processor correctly strips env-related fields

---

## 11. Future Considerations

### 11.1 Phase 2: Encrypted Environment Profiles

**Not in this spec, but planned:**

Users who want cross-device secret sharing without re-entering could use encrypted profiles:
- Client encrypts env vars locally, uploads encrypted blob to mcpworks
- mcpworks stores the opaque blob (cannot decrypt it)
- Client sends profile ID + decryption key in headers per-request
- Server decrypts in-memory, injects into sandbox, discards all three

This preserves zero-knowledge while enabling multi-device workflows. Ship only if users request it.

### 11.2 Phase 2: Individual Header Format

Support `X-MCPWorks-Env-{NAME}: {value}` as an alternative to the single base64 blob. More human-readable for simple cases. Server supports both, preferring the encoded form.

### 11.3 Phase 2: Activepieces Backend Env Vars

Activepieces has its own credential/connection system. If users need env var passthrough for Activepieces functions, design a bridge. Not needed for A0.

### 11.4 Known Limitations

- **No env var rotation notification:** If a user rotates an API key, they update their local config. We have no way to notify them if a function starts failing due to an expired key. Acceptable — standard developer workflow.
- **No env var sharing between namespaces:** Each namespace is a separate MCP server entry. Users who want the same key in multiple namespaces must configure it in each. Acceptable — explicit is better than implicit.
- **Base64 encoding is not human-friendly:** Mitigated by documentation with helper commands. Phase 2 individual headers provide an alternative.

---

## 12. Client Configuration Reference

### 12.1 Claude Code / Claude Desktop (.mcp.json)

```json
{
  "mcpServers": {
    "acme": {
      "type": "http",
      "url": "https://acme.run.mcpworks.io/mcp",
      "headers": {
        "Authorization": "Bearer ${MCPWORKS_API_KEY}",
        "X-MCPWorks-Env": "${MCPWORKS_ACME_ENV}"
      }
    }
  }
}
```

### 12.2 Shell Environment Setup

```bash
# Encode env vars as base64 JSON
export MCPWORKS_ACME_ENV=$(echo -n '{"OPENAI_API_KEY":"sk-proj-...","DATABASE_URL":"postgres://..."}' | base64 -w0)

# Or from a .env file (helper one-liner)
export MCPWORKS_ACME_ENV=$(python3 -c "
import json, base64, sys
env = {}
for line in open(sys.argv[1]):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip('\"')
print(base64.b64encode(json.dumps(env).encode()).decode())
" .env.acme)
```

### 12.3 Using System Environment References

For users who prefer not to have secrets in any file:

```json
{
  "headers": {
    "X-MCPWorks-Env": "${MCPWORKS_ACME_ENV}"
  }
}
```

Where `MCPWORKS_ACME_ENV` is set in the user's shell profile. The `.mcp.json` file contains zero secrets.

---

## 13. Spec Completeness Checklist

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
- [x] Observability requirements defined
- [x] Reviewed for Constitution compliance
- [ ] Logic checked (internally consistent)
- [ ] Peer reviewed (if team > 1)

---

## 14. Approval

**Status:** Draft

**Approvals:**
- [ ] CTO (Simon Carr)
- [ ] Security Review

**Approved Date:** —
**Next Review:** —

---

## Changelog

**v0.1.0 (2026-02-19):**
- Initial draft based on architecture discussion with sandbox-engineer and CTO-architect agents

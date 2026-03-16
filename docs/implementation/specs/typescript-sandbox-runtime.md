# TypeScript Sandbox Runtime - Specification

**Version:** 0.1.0 (Draft)
**Created:** 2026-03-15
**Status:** Draft
**Spec Author:** Simon Carr + Claude Opus 4.6
**Reviewers:** CTO

---

## 1. Overview

### 1.1 Purpose

Add TypeScript/JavaScript as a second supported language for the Code Sandbox backend. LLMs can already author Python functions via `make_function`; this spec extends the same backend (`code_sandbox`) to accept TypeScript, transpile it, and execute it in a Node.js runtime under the same nsjail isolation that Python uses today.

### 1.2 User Value

LLMs produce TypeScript as readily as Python. Many MCPWorks users work in TypeScript-dominant stacks (Next.js, tRPC, Cloudflare Workers). Forcing Python-only excludes them and forces LLMs to context-switch languages. TypeScript support doubles the addressable audience with minimal infrastructure change.

### 1.3 Success Criteria

**This spec is successful when:**
- [ ] An LLM can call `make_function(backend="code_sandbox", language="typescript", code="...")` and get a working function
- [ ] TypeScript functions execute under nsjail with identical isolation guarantees to Python
- [ ] At least 3 TypeScript templates are available (hello-world-ts, api-connector-ts, json-transformer-ts)
- [ ] All existing Python functions continue working with zero changes
- [ ] TypeScript function cold start < 200ms, warm execution overhead < 15ms

### 1.4 Scope

**In Scope:**
- Node.js 22 LTS runtime in sandbox image
- esbuild transpilation (TS to JS, pre-execution)
- `language` parameter on `make_function` / `update_function`
- TypeScript executor (analogous to Python's `executor.py`)
- npm package allowlist (pre-installed in sandbox image)
- TypeScript function templates
- seccomp policy adjustments for V8 engine
- FunctionVersion model: `language` column

**Out of Scope:**
- Deno or Bun runtimes (evaluate in A2)
- Dynamic `npm install` at execution time
- TypeScript-specific SDK (reuse HTTP-based SDK contract)
- Frontend/browser APIs (DOM, window, etc.)
- WebAssembly execution
- Multi-file TypeScript projects (single-file functions only, same as Python)

---

## 2. User Scenarios

### 2.1 Primary Scenario: LLM Creates a TypeScript Function

**Actor:** AI Assistant (Claude, GPT, Codex)
**Goal:** Create and execute a TypeScript function via MCP tools
**Context:** User has a namespace and service already configured

**Workflow:**
1. LLM calls `make_function(service="utils", name="greet", backend="code_sandbox", language="typescript", code="export default function main(input: Record<string, any>) { return { greeting: `Hello, ${input.name || 'World'}!` }; }")`
2. API validates TypeScript syntax via esbuild parse (fast, no full tsc)
3. API stores code as TypeScript in FunctionVersion (language="typescript")
4. LLM (or user) calls `execute_function(service="utils", name="greet", input={"name": "Simon"})`
5. Sandbox receives TypeScript code, esbuild transpiles to JS, Node.js executes
6. Result returned: `{"greeting": "Hello, Simon!"}`

**Success:** Function created and executed in < 500ms total
**Failure:** Syntax error returned at creation time; runtime error returned at execution time

### 2.2 Secondary Scenario: LLM Uses a TypeScript Template

**Actor:** AI Assistant
**Goal:** Clone and customize a TypeScript template

**Workflow:**
1. LLM calls `list_templates()` — sees both Python and TypeScript templates
2. LLM calls `describe_template(name="api-connector-ts")` — gets TypeScript template with fetch-based HTTP
3. LLM calls `make_function(service="integrations", name="github-api", template="api-connector-ts")`
4. LLM calls `update_function(service="integrations", name="github-api", code="<customized version>")` to tailor it

### 2.3 Edge Scenario: LLM Omits Language Parameter

**Actor:** AI Assistant
**Goal:** Create a function without specifying language

**Workflow:**
1. LLM calls `make_function(service="utils", name="hello", backend="code_sandbox", code="def main(input): ...")`
2. API detects no `language` parameter — defaults to `"python"` (backward compatible)
3. Python execution proceeds exactly as today

---

## 3. Functional Requirements

### 3.1 Language Parameter

**REQ-TS-001: Language field on make_function and update_function**
- **Description:** Add optional `language` parameter to `make_function` and `update_function` MCP tools. Accepted values: `"python"` (default), `"typescript"`.
- **Priority:** Must Have
- **Rationale:** Allows LLMs to specify which runtime to use without changing the backend model
- **Acceptance:** `make_function(language="typescript", code="...")` stores and executes TypeScript

**REQ-TS-002: Language field on FunctionVersion model**
- **Description:** Add `language` column to `function_versions` table. Type: `String(20)`, default `"python"`, not null. Alembic migration required.
- **Priority:** Must Have
- **Rationale:** Each version must know its language for execution routing
- **Acceptance:** Existing rows migrate with `language="python"`; new TS versions get `language="typescript"`

**REQ-TS-003: Backward compatibility**
- **Description:** All existing API calls without `language` parameter must default to `"python"` and behave identically to today
- **Priority:** Must Have
- **Acceptance:** Full Python test suite passes without changes

### 3.2 TypeScript Validation

**REQ-TS-010: Syntax validation at creation time**
- **Description:** Validate TypeScript syntax using esbuild's `transform` API (parse-only mode). This is fast (~5ms) and catches syntax errors before storing.
- **Priority:** Must Have
- **Rationale:** Fail fast — don't store broken code
- **Acceptance:** `make_function` with syntax-invalid TS returns validation error

**REQ-TS-011: Dangerous pattern detection**
- **Description:** Apply TypeScript-equivalent dangerous pattern checks:
  - `child_process` (subprocess equivalent)
  - `eval(` (code injection)
  - `Function(` (dynamic function creation)
  - `require('fs')` or `import fs` (direct filesystem access)
  - `process.env` reads beyond declared env vars
  - `Deno`, `Bun` global references (not available)
- **Priority:** Must Have
- **Rationale:** Defense-in-depth; seccomp is the real protection, but these catch obvious misuse early
- **Acceptance:** Warnings generated for dangerous patterns (same behavior as Python)

**REQ-TS-012: Code size limit**
- **Description:** Same 1MB limit as Python
- **Priority:** Must Have

### 3.3 TypeScript Execution

**REQ-TS-020: Transpilation**
- **Description:** Before execution, transpile TypeScript to JavaScript using esbuild. esbuild runs on the host (Worker Manager), NOT inside the sandbox. Only the resulting JS is injected into the sandbox.
- **Priority:** Must Have
- **Rationale:** esbuild is ~100x faster than tsc (~5ms for typical function). Running transpilation on the host avoids bloating the sandbox image and reduces attack surface.
- **Acceptance:** TypeScript with type annotations, interfaces, enums, and generics transpiles correctly

**REQ-TS-021: Execution wrapper**
- **Description:** Create a TypeScript execution wrapper analogous to Python's `_wrap_code()`. The wrapper must:
  1. Read `input.json` from the execution directory
  2. Read `context.json` if present
  3. Read `.sandbox_env.json` if present, populate `process.env`
  4. Import the user's transpiled code
  5. Detect entry point (priority order):
     - `export default function main(input)` or `export default function handler(input, context)`
     - `module.exports.main` or `module.exports.handler`
     - Top-level `result = ...` or `output = ...` assignment (via wrapper eval)
  6. Capture stdout/stderr
  7. Write `output.json` with `{success, result, stdout, stderr, error, error_type}`
- **Priority:** Must Have
- **Acceptance:** All 4 entry point patterns work correctly

**REQ-TS-022: Entry point convention**
- **Description:** TypeScript functions use these entry points (documented in `make_function` tool description):
  ```typescript
  // Pattern 1: Default export (preferred)
  export default function main(input: Record<string, any>): any {
    return { greeting: `Hello, ${input.name}!` };
  }

  // Pattern 2: Handler with context (for agent orchestration)
  export default function handler(
    input: Record<string, any>,
    context: { state: Record<string, any> }
  ): any {
    return { result: context.state.someKey };
  }

  // Pattern 3: CommonJS export
  module.exports.main = function(input) { return { ok: true }; };

  // Pattern 4: Simple assignment (for quick scripts)
  const result = { computed: 42 };
  ```
- **Priority:** Must Have

**REQ-TS-023: Async support**
- **Description:** Support `async` entry points. If the entry point returns a Promise, await it before writing output.
- **Priority:** Must Have
- **Rationale:** Most real-world TypeScript uses async/await (fetch, database, etc.)

**REQ-TS-024: Timeout enforcement**
- **Description:** Same tier-based timeouts as Python. Enforced at two levels:
  1. nsjail `time_limit` (hard kill)
  2. Worker Manager `asyncio.wait_for` (graceful timeout with +5s grace)
- **Priority:** Must Have

### 3.4 Node.js Sandbox Image

**REQ-TS-030: Node.js installation**
- **Description:** Install Node.js 22 LTS (Alpine-based static binary) into the sandbox root filesystem at `/usr/local/bin/node`. No npm binary needed inside sandbox (packages pre-installed).
- **Priority:** Must Have
- **Rationale:** Node 22 is current LTS; static binary avoids libc dependencies in the minimal sandbox root
- **Acceptance:** `/usr/local/bin/node --version` works inside nsjail sandbox

**REQ-TS-031: Pre-installed npm packages**
- **Description:** Install the following packages into the sandbox root at `/opt/mcpworks/sandbox-root/node_modules/`:

  **Core (always available):**
  - No external packages required for basic functions — Node.js built-ins cover: `crypto`, `url`, `querystring`, `path`, `buffer`, `util`, `events`, `stream`, `zlib`

  **Data processing:**
  - `lodash` (utility functions)
  - `date-fns` (date manipulation)
  - `uuid` (UUID generation)
  - `zod` (runtime validation)
  - `csv-parse` / `csv-stringify` (CSV handling)
  - `yaml` (YAML parsing)
  - `cheerio` (HTML parsing)
  - `marked` (Markdown parsing)

  **Network (Builder tier+ only):**
  - Node.js built-in `fetch` (Node 22 has stable fetch)
  - `axios` (HTTP client, for those who prefer it)

  **Encoding/Crypto:**
  - `jsonwebtoken` (JWT)
  - `bcrypt` (hashing)
  - `base64url`

  **Format:**
  - `xml2js` (XML parsing)
  - `ajv` (JSON Schema validation)

- **Priority:** Must Have
- **Rationale:** Mirror the Python approach — pre-installed, allowlisted packages only
- **Acceptance:** `require('lodash')` works inside sandbox; unlisted packages fail with clear error

**REQ-TS-032: Package allowlist validation**
- **Description:** Validate `requirements` field against the TypeScript package allowlist at function creation time. Reject unknown packages with error listing available packages.
- **Priority:** Must Have
- **Acceptance:** `make_function(language="typescript", requirements=["malicious-pkg"])` returns validation error

**REQ-TS-033: list_packages tool update**
- **Description:** The `list_packages` MCP tool must accept an optional `language` parameter and return packages for that language. Default: return both. Example: `list_packages(language="typescript")` returns only TS packages.
- **Priority:** Should Have

### 3.5 seccomp Policy for V8

**REQ-TS-040: Additional syscalls for Node.js/V8**
- **Description:** V8 requires additional syscalls beyond the Python allowlist. Add these to the seccomp policy when executing TypeScript:
  - `mmap` with `PROT_WRITE|PROT_EXEC` (V8 JIT compilation) — **critical, Python doesn't need this**
  - `prctl` with `PR_SET_NAME` (V8 thread naming)
  - `sched_getaffinity` (V8 thread pool sizing)
  - `prlimit64` (Node.js resource checking)
  - `eventfd2` (libuv event loop)
  - `pipe2` (libuv)
  - `dup`, `dup2` (stdout/stderr redirection)
  - `ioctl` with `TIOCGWINSZ` only (terminal size query)

  All other seccomp restrictions remain identical to Python.
- **Priority:** Must Have
- **Rationale:** V8's JIT compiler fundamentally requires `PROT_WRITE|PROT_EXEC` mmap. Without it, Node.js crashes immediately. This is the single biggest security difference from Python.
- **Risk Mitigation:** JIT W^X is an accepted trade-off — all major cloud sandbox providers (Cloudflare Workers, Deno Deploy, AWS Lambda) allow it. The other 5 defense layers (namespaces, cgroups, network isolation, filesystem isolation, capability dropping) prevent exploitation.
- **Acceptance:** Node.js starts and executes code without seccomp violations

**REQ-TS-041: Separate seccomp profiles**
- **Description:** Maintain two seccomp profiles:
  - `config/seccomp-python.policy` — current Python allowlist (rename from `seccomp.policy`)
  - `config/seccomp-node.policy` — Python allowlist + V8 additions

  The spawn script selects the profile based on language.
- **Priority:** Must Have
- **Rationale:** Don't weaken Python's security by adding V8 syscalls to it

### 3.6 Templates

**REQ-TS-050: TypeScript templates**
- **Description:** Add these TypeScript templates alongside existing Python templates:

  **hello-world-ts:**
  ```typescript
  export default function main(input: Record<string, any>) {
    const name = input.name || "World";
    return { greeting: `Hello, ${name}!`, message: "Your TypeScript sandbox is working." };
  }
  ```

  **api-connector-ts (requires network):**
  ```typescript
  export default async function main(input: Record<string, any>) {
    const { url, method = "GET", headers = {}, body } = input;
    if (!url) return { error: "url is required" };

    const response = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    const text = await response.text();
    return {
      status_code: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      body: text.slice(0, 10000),
      ok: response.ok,
    };
  }
  ```

  **json-transformer-ts:**
  ```typescript
  import { z } from "zod";

  export default function main(input: Record<string, any>) {
    const { data, operations = [] } = input;
    if (!data) return { error: "data is required" };

    let result = structuredClone(data);
    for (const op of operations) {
      if (op.type === "pick") result = pick(result, op.keys);
      else if (op.type === "rename") result = rename(result, op.mapping);
      else if (op.type === "filter" && Array.isArray(result)) {
        result = result.filter((item: any) => item[op.key] === op.value);
      }
    }
    return { transformed: result };
  }

  function pick(obj: any, keys: string[]) {
    return Object.fromEntries(keys.filter(k => k in obj).map(k => [k, obj[k]]));
  }

  function rename(obj: any, mapping: Record<string, string>) {
    return Object.fromEntries(Object.entries(obj).map(([k, v]) => [mapping[k] || k, v]));
  }
  ```

- **Priority:** Must Have
- **Acceptance:** All 3 templates clone and execute successfully

**REQ-TS-051: Template language field**
- **Description:** Add `language` field to `FunctionTemplate` class. Templates listed without language filter show all; with `language="typescript"` shows only TS templates.
- **Priority:** Should Have

### 3.7 MCP Tool Interface Changes

**REQ-TS-060: make_function tool description update**
- **Description:** Update the `make_function` tool schema:
  - Add `language` property: `{"type": "string", "enum": ["python", "typescript"], "description": "Programming language. Defaults to 'python'. Use 'typescript' for TypeScript/JavaScript functions."}`
  - Update `code` description to mention both languages and their entry points
  - Update `requirements` description to mention language-specific packages
- **Priority:** Must Have

**REQ-TS-061: update_function language immutability**
- **Description:** The `language` of a function cannot be changed via `update_function`. If a user wants to switch languages, they must create a new function. This prevents confusing version histories where v1 is Python and v2 is TypeScript.
- **Priority:** Must Have
- **Rationale:** Mixed-language version histories break rollback (can't rollback a TS function to a Python version)

**REQ-TS-062: describe_function language display**
- **Description:** `describe_function` response must include `language` field showing the active version's language.
- **Priority:** Must Have

---

## 4. Non-Functional Requirements

### 4.1 Performance

- **Transpilation:** esbuild transpile < 10ms for typical functions (< 50KB source)
- **Cold Start:** Node.js cold start < 200ms inside sandbox (acceptable — Python is 50-100ms)
- **Warm Execution:** Pre-warmed Node.js executor overhead < 15ms (matches Python target)
- **Token Efficiency:** No change — TypeScript tool responses same size as Python

### 4.2 Security

- **Isolation:** Identical to Python: PID/NET/MNT/UTS/IPC namespaces, cgroups v2, seccomp-bpf
- **JIT Security:** V8 JIT requires W^X mmap — accepted trade-off, mitigated by other 5 layers
- **Package Security:** Pre-installed packages audited via `npm audit`; weekly audit in CI
- **Credential Scanning:** Same patterns apply: detect `sk-`, `mcpw_`, bearer tokens in TS code
- **No eval/Function:** Defense-in-depth pattern detection for `eval(`, `new Function(`, `vm.runInNewContext`

### 4.3 Reliability

- **Failure Isolation:** A Node.js crash/OOM must not affect Python sandboxes or the Worker Manager
- **Graceful Degradation:** If Node.js binary is missing, TypeScript functions fail with clear error; Python continues working
- **Error Messages:** TypeScript compilation errors returned in same `error`/`error_type` format as Python

### 4.4 Scalability

- **Pool Strategy (Phase 1):** No pre-warmed Node.js pool. Cold start on each TypeScript execution. Monitor demand.
- **Pool Strategy (Phase 2):** If TypeScript usage exceeds 20% of executions, add pre-warmed Node.js pool alongside Python pool
- **Sandbox Image Size:** Node.js 22 static binary adds ~50MB to sandbox root. Acceptable.

---

## 5. Constraints & Assumptions

### 5.1 Technical Constraints

- **esbuild on host only:** esbuild runs on the Worker Manager (host), not inside the sandbox. This keeps the sandbox image minimal and prevents esbuild from being used as an attack vector.
- **No TypeScript type checking:** esbuild strips types but doesn't type-check. This is intentional — full tsc is 10-100x slower and LLM-authored code rarely benefits from strict type checking at creation time.
- **Single-file functions:** Same as Python — no multi-file projects, no local imports between files.
- **No npm at runtime:** All packages must be pre-installed in the sandbox image. No `npm install` during execution.

### 5.2 Business Constraints

- **Timeline:** Target A1 milestone (post March 16 review date)
- **Resources:** Solo developer
- **Risk:** Must not break existing Python functions or delay A0 completion

### 5.3 Assumptions

- **LLM TypeScript quality:** LLMs produce functional TypeScript at comparable quality to Python
- **V8 syscall stability:** Node.js 22 LTS won't introduce new required syscalls during its support window
- **Package demand:** The initial allowlist covers 80%+ of LLM-authored TypeScript use cases
- **Risk if wrong:** If V8 needs additional syscalls, we update the seccomp profile — low risk

---

## 6. Error Scenarios & Edge Cases

### 6.1 Error Scenario: TypeScript Syntax Error

**Trigger:** LLM submits invalid TypeScript to `make_function`
**Expected Behavior:** esbuild parse catches error, returns structured validation error
**User Experience:** `{"valid": false, "errors": ["Syntax error: Expected ';' at line 5"]}`
**Recovery:** LLM fixes code and retries
**Logging:** Validation failure logged (no PII)

### 6.2 Error Scenario: Missing Package

**Trigger:** Code uses `import foo from 'unavailable-pkg'`
**Expected Behavior:** Node.js throws `MODULE_NOT_FOUND` at runtime
**User Experience:** `{"success": false, "error": "Cannot find module 'unavailable-pkg'", "error_type": "ModuleNotFoundError"}`
**Recovery:** LLM checks `list_packages(language="typescript")` and rewrites

### 6.3 Error Scenario: V8 JIT Seccomp Violation

**Trigger:** seccomp policy missing a required V8 syscall
**Expected Behavior:** Process killed with exit code 159 (seccomp)
**User Experience:** `{"success": false, "error": "Sandbox security violation", "error_type": "SecurityError"}`
**Logging:** Violation logged to security_events table
**Recovery:** Ops investigates, updates seccomp profile if legitimate V8 need

### 6.4 Edge Case: JavaScript (not TypeScript)

**Scenario:** LLM submits plain JavaScript with `language="typescript"`
**Expected Behavior:** Works fine — esbuild passes JavaScript through, Node.js executes it
**Rationale:** TypeScript is a superset of JavaScript; no reason to reject valid JS

### 6.5 Edge Case: Mixed Language Rollback

**Scenario:** User creates v1 as Python, tries to update v2 as TypeScript
**Expected Behavior:** Rejected — language is immutable per function (REQ-TS-061)
**User Experience:** `{"error": "Cannot change function language. Create a new function for TypeScript."}`

### 6.6 Edge Case: Top-Level Await

**Scenario:** LLM writes `const data = await fetch('...')` at top level
**Expected Behavior:** Wrapper detects top-level await and wraps in async IIFE, same as Python's async detection
**Rationale:** Node 22 supports top-level await in ESM, but our wrapper uses CommonJS for simplicity. Detect and wrap.

---

## 7. Token Efficiency Analysis

### 7.1 Tool Definition Changes

**make_function tool schema grows by ~80 tokens** (adding `language` property + updated descriptions). Acceptable.

### 7.2 Typical Responses

No change — function execution responses are language-agnostic. Same `{success, result, stdout, stderr}` format.

### 7.3 list_packages Response

Grows by ~200 tokens when both languages returned. Mitigated by optional `language` filter parameter.

---

## 8. Security Analysis

### 8.1 Threat: V8 JIT Code Injection

**Threat:** Attacker crafts TypeScript that exploits V8 JIT compilation to execute arbitrary native code
**Impact:** Potential sandbox escape (critical)
**Mitigation:**
1. seccomp still blocks dangerous syscalls (mount, ptrace, unshare, etc.)
2. Network namespace prevents data exfiltration
3. PID namespace prevents process enumeration
4. Filesystem is read-only except /tmp and /sandbox
5. No capabilities granted
6. nsjail time_limit kills long-running exploits
**Residual Risk:** Medium — V8 JIT is an accepted attack surface, mitigated by defense-in-depth. Same risk profile as Cloudflare Workers, AWS Lambda.

### 8.2 Threat: Prototype Pollution

**Threat:** TypeScript code pollutes global prototypes (`Object.prototype.isAdmin = true`)
**Impact:** Affects only the current sandbox (isolated process)
**Mitigation:** Each execution gets a fresh Node.js process (no shared state between executions)
**Residual Risk:** Low

### 8.3 PII/Sensitive Data

Same as Python — no change:
- Input/output not logged by default (ORDER-020)
- Error messages truncated and PII-scrubbed (ORDER-023)
- Environment variables passed via file, never logged

---

## 9. Observability Requirements

### 9.1 Metrics

- `sandbox_executions_total{language="typescript"}` — counter of TS executions
- `sandbox_execution_duration_seconds{language="typescript"}` — execution time histogram
- `sandbox_transpile_duration_seconds` — esbuild transpilation time
- `sandbox_violations_total{language="typescript"}` — seccomp violations from Node.js

### 9.2 Logging

**Additional structured log fields:**
- `language: "typescript"` on all execution log entries
- `transpile_ms: <duration>` on execution start

**Must NOT log:** TypeScript source code, transpiled JavaScript, input/output data

### 9.3 Alerting

- Alert if TypeScript seccomp violations exceed 5/hour (may indicate missing syscall)
- Alert if esbuild transpilation failures exceed 10% (may indicate esbuild bug or attack)

---

## 10. Implementation Plan

### 10.1 Phase 1: Model & Validation (1 day)

1. Alembic migration: add `language` column to `function_versions` (default "python")
2. Update `FunctionVersion` model with `language` field and validation
3. Update `SandboxBackend.validate()` to handle TypeScript (esbuild parse)
4. Add esbuild as a host dependency (pip: `esbuild` Python wrapper, or shell out to binary)

### 10.2 Phase 2: Execution (2-3 days)

1. Create `ts_executor_wrapper.js` — Node.js equivalent of Python's `_wrap_code()`
2. Update `SandboxBackend._execute_dev_mode()` to detect language and use `node` instead of `python3`
3. Update `SandboxBackend._execute_nsjail()` to pass language to spawn script
4. Update `spawn-sandbox.sh` to select Python or Node.js binary and seccomp profile
5. Create `config/seccomp-node.policy` with V8 additions

### 10.3 Phase 3: Sandbox Image (1 day)

1. Add Node.js 22 LTS static binary to sandbox root Dockerfile
2. Pre-install npm packages into `/opt/mcpworks/sandbox-root/node_modules/`
3. Run `npm audit` on installed packages
4. Test Node.js execution inside nsjail

### 10.4 Phase 4: MCP Interface (1 day)

1. Update `make_function` tool schema with `language` parameter
2. Update `update_function` to reject language changes
3. Update `describe_function` to include language
4. Update `list_packages` with language filter
5. Add TypeScript templates to `templates.py`
6. Update `FunctionTemplate` with `language` field

### 10.5 Phase 5: Testing (1-2 days)

1. Unit tests: TS validation, transpilation, wrapper
2. Integration tests: full create → execute flow for all 4 entry points
3. Security tests: seccomp violations, sandbox isolation
4. Regression tests: all existing Python tests still pass

**Total estimate: 6-8 days**

---

## 11. Testing Requirements

### 11.1 Unit Tests

- TypeScript syntax validation (valid code, invalid code, edge cases)
- esbuild transpilation (types stripped, enums compiled, JSX not supported)
- Execution wrapper (all 4 entry points, async detection, stdout/stderr capture)
- Dangerous pattern detection for TypeScript
- Package allowlist validation for TypeScript
- Language immutability on update

### 11.2 Integration Tests

- Create TypeScript function → execute → verify output
- Create from TypeScript template → execute → verify
- TypeScript function with network access (Builder tier)
- TypeScript function with environment variables
- TypeScript function with context (agent orchestration)
- Mixed namespace: Python and TypeScript functions coexist

### 11.3 Security Tests

- Node.js cannot escape PID namespace
- Node.js cannot access network (Free tier)
- Node.js cannot read host filesystem
- Node.js killed on seccomp violation (attempted forbidden syscall)
- Node.js killed on timeout
- Node.js killed on OOM

### 11.4 Regression Tests

- All existing Python test suite passes unchanged
- Python execution performance unchanged

---

## 12. Future Considerations

### 12.1 Phase 2 Enhancements

- **Pre-warmed Node.js pool:** If TS usage exceeds 20% of executions, add warm Node.js pool for <10ms latency
- **Deno runtime option:** Deno's built-in TypeScript support and security model could simplify the stack
- **WebAssembly functions:** WASM as a third "language" option for portable, secure execution
- **Multi-file projects:** Allow `import` from sibling files in the same function

### 12.2 Known Limitations

- **No type checking:** esbuild strips types without checking them. LLMs must produce correct types. Acceptable because: (a) runtime errors catch type mismatches, (b) LLMs are reasonably good at TypeScript types, (c) tsc is too slow for per-execution use.
- **Cold start penalty:** ~150ms extra vs Python. Acceptable for A1; warm pool planned for A2 if needed.
- **Limited packages:** ~20 pre-installed packages vs Python's 60+. Will expand based on user demand.

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
- [ ] Logic checked (internally consistent)
- [ ] Peer reviewed

---

## 14. Approval

**Status:** Draft

**Approvals:**
- [ ] CTO (Simon Carr)
- [ ] Security Review (seccomp changes, V8 JIT risk)

**Approved Date:** —
**Next Review:** —

---

## Changelog

**v0.1.0 (2026-03-15):**
- Initial draft

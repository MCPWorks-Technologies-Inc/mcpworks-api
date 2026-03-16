# TypeScript Sandbox Runtime — Implementation Plan

**Version:** 1.0.0
**Created:** 2026-03-16
**Status:** Active
**Source Specification:** `../specs/typescript-sandbox-runtime.md`

---

## Overview

This plan translates the TypeScript Sandbox Runtime specification into concrete code changes. It is organized into 5 phases with explicit file-level change lists, ordered by dependency chain.

**Dependency chain:**
```
Phase 1 (Model)  →  Phase 2 (Packages)  →  Phase 3 (Execution)  →  Phase 4 (MCP Interface)  →  Phase 5 (Docker/Deploy)
     ↓                     ↓                      ↓                        ↓
  Alembic migration    packages_node.py       execute.js              Tool schemas
  FunctionVersion      validate_requirements  spawn-sandbox.sh        Templates
  Pydantic schema      list_packages          sandbox.py              Tests
```

---

## Phase 1: Data Model — `language` Field

**Goal:** Every FunctionVersion knows its language. All existing data defaults to `"python"`.

### 1A. Alembic Migration

**New file:** `alembic/versions/20260316_000001_add_language_to_function_versions.py`

```python
"""Add language column to function_versions.

Revision ID: <auto>
"""
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    op.add_column(
        "function_versions",
        sa.Column("language", sa.String(20), nullable=False, server_default="python"),
    )

def downgrade() -> None:
    op.drop_column("function_versions", "language")
```

**Notes:**
- `server_default="python"` backfills all existing rows automatically
- No data migration needed — every existing version is Python
- Keep the check constraint simple: no DB-level enum, validated in app layer

### 1B. FunctionVersion Model

**File:** `src/mcpworks_api/models/function_version.py`

**Changes:**
```python
# After line 28 (ALLOWED_BACKENDS)
ALLOWED_LANGUAGES = {"python", "typescript"}

# New column after `backend` (around line 64)
language: Mapped[str] = mapped_column(
    String(20),
    nullable=False,
    server_default="python",
)

# New validator
@validates("language")
def validate_language(self, key: str, value: str) -> str:
    if value not in ALLOWED_LANGUAGES:
        raise ValueError(f"Language must be one of {ALLOWED_LANGUAGES}")
    return value
```

### 1C. Pydantic Schema

**File:** `src/mcpworks_api/schemas/function.py`

**Changes:**
```python
# FunctionVersionCreate — add field after `backend`
ALLOWED_LANGUAGES = {"python", "typescript"}

language: str = Field(
    "python",
    description="Programming language (python or typescript)",
)

@field_validator("language")
@classmethod
def validate_language(cls, v: str) -> str:
    if v not in ALLOWED_LANGUAGES:
        raise ValueError(f"Language must be one of {ALLOWED_LANGUAGES}")
    return v

# FunctionVersionResponse — add field
language: str = "python"
```

### 1D. FunctionService

**File:** `src/mcpworks_api/services/function.py`

**Changes:**
- `create()`: Add `language: str = "python"` parameter, pass to FunctionVersion constructor
- `create_version()`: Add `language: str | None = None` parameter. If None, inherit from active version. If provided, verify it matches existing versions (language immutability — REQ-TS-061)
- `describe()`: Include `language` in `active_version_details` dict
- `get_version_detail()`: Include `language` in response dict

**Language immutability logic in `create_version()`:**
```python
if language is not None:
    existing_versions = function.versions
    if existing_versions:
        existing_lang = existing_versions[0].language
        if language != existing_lang:
            raise ValueError(
                f"Cannot change function language from '{existing_lang}' to '{language}'. "
                "Create a new function for a different language."
            )
```

### Phase 1 Test Checklist

- [ ] Migration applies and rolls back cleanly
- [ ] Existing FunctionVersions have `language="python"` after migration
- [ ] New Python function version gets `language="python"` by default
- [ ] New TypeScript function version gets `language="typescript"`
- [ ] Language change across versions is rejected
- [ ] Invalid language value is rejected
- [ ] `describe()` includes language field

---

## Phase 2: Package Registry

**Goal:** TypeScript functions have their own package allowlist, validated at creation time.

### 2A. Node.js Package Registry

**New file:** `src/mcpworks_api/sandbox/packages_node.py`

Structure mirrors `packages.py` exactly:

```python
"""Allow-listed Node.js package registry for TypeScript sandbox execution.

All packages are pre-installed in the sandbox Docker image.
To add a new package:
1. Add it to NODE_PACKAGE_REGISTRY below
2. Add the npm package name to the Dockerfile node-sandbox-builder stage
3. Rebuild and deploy
"""

from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class NodePackageInfo:
    npm_name: str
    description: str
    category: str
    aliases: tuple[str, ...] = ()

NODE_PACKAGE_REGISTRY: dict[str, NodePackageInfo] = {
    # ── Data Processing ──
    "lodash": NodePackageInfo(
        npm_name="lodash",
        description="Utility functions for arrays, objects, strings",
        category="utilities",
    ),
    "date-fns": NodePackageInfo(
        npm_name="date-fns",
        description="Modern date utility library",
        category="datetime",
    ),
    "uuid": NodePackageInfo(
        npm_name="uuid",
        description="RFC-compliant UUID generation",
        category="utilities",
    ),
    "zod": NodePackageInfo(
        npm_name="zod",
        description="TypeScript-first schema validation",
        category="validation",
    ),
    "csv-parse": NodePackageInfo(
        npm_name="csv-parse",
        description="CSV parser with streaming support",
        category="data_formats",
    ),
    "csv-stringify": NodePackageInfo(
        npm_name="csv-stringify",
        description="CSV serializer",
        category="data_formats",
    ),
    "yaml": NodePackageInfo(
        npm_name="yaml",
        description="YAML parser and serializer",
        category="data_formats",
    ),
    "cheerio": NodePackageInfo(
        npm_name="cheerio",
        description="HTML parser (jQuery-like API for server)",
        category="text",
    ),
    "marked": NodePackageInfo(
        npm_name="marked",
        description="Markdown to HTML converter",
        category="text",
    ),
    # ── Network (Builder tier+) ──
    "axios": NodePackageInfo(
        npm_name="axios",
        description="HTTP client (alternative to built-in fetch)",
        category="http",
    ),
    # ── Crypto & Auth ──
    "jsonwebtoken": NodePackageInfo(
        npm_name="jsonwebtoken",
        description="JSON Web Token signing and verification",
        category="security",
    ),
    "bcryptjs": NodePackageInfo(
        npm_name="bcryptjs",
        description="Password hashing (pure JS, no native deps)",
        category="security",
        aliases=("bcrypt",),
    ),
    # ── Formats ──
    "xml2js": NodePackageInfo(
        npm_name="xml2js",
        description="XML to JavaScript object converter",
        category="data_formats",
    ),
    "ajv": NodePackageInfo(
        npm_name="ajv",
        description="JSON Schema validator (fast)",
        category="validation",
    ),
    # ── AI & LLM ──
    "openai": NodePackageInfo(
        npm_name="openai",
        description="OpenAI API client",
        category="ai",
    ),
    "@anthropic-ai/sdk": NodePackageInfo(
        npm_name="@anthropic-ai/sdk",
        description="Anthropic Claude API client",
        category="ai",
        aliases=("anthropic",),
    ),
}
```

### 2B. Unified Validation Interface

**File:** `src/mcpworks_api/sandbox/packages.py`

**Add at bottom:**
```python
def validate_requirements_for_language(
    requirements: list[str],
    language: str = "python",
) -> tuple[list[str], list[str]]:
    """Dispatch requirement validation to the correct language registry."""
    if language == "typescript":
        from mcpworks_api.sandbox.packages_node import validate_node_requirements
        return validate_node_requirements(requirements)
    return validate_requirements(requirements)
```

**File:** `src/mcpworks_api/sandbox/packages_node.py`

**Add validation functions** (same pattern as Python):
```python
def validate_node_requirements(requirements: list[str]) -> tuple[list[str], list[str]]:
    """Validate npm package requirements against the Node.js allow-list."""
    # Same logic as validate_requirements but using NODE_PACKAGE_REGISTRY
    ...

def get_node_registry_by_category() -> dict[str, list[dict[str, str]]]:
    ...

def get_all_npm_names() -> list[str]:
    ...
```

### 2C. Update create_handler.py list_packages

**File:** `src/mcpworks_api/mcp/create_handler.py`

**Changes to `_list_packages` method:**
- Accept optional `language` argument
- If `language="typescript"`, return Node.js packages
- If `language="python"` or omitted, return Python packages
- If `language="all"`, return both grouped by language

**Changes to `list_packages` tool schema:**
- Add `language` property: `{"type": "string", "enum": ["python", "typescript", "all"], "description": "Filter by language. Default: python"}`

### Phase 2 Test Checklist

- [ ] `validate_node_requirements()` accepts valid packages, rejects unknown
- [ ] Alias resolution works (e.g., `"bcrypt"` → `"bcryptjs"`)
- [ ] `list_packages(language="typescript")` returns only Node.js packages
- [ ] `list_packages()` defaults to Python (backward compatible)
- [ ] `validate_requirements_for_language()` dispatches correctly

---

## Phase 3: Execution Engine

**Goal:** TypeScript code transpiles on the host and executes inside nsjail with Node.js.

### 3A. TypeScript Validation in SandboxBackend

**File:** `src/mcpworks_api/backends/sandbox.py`

**Changes to `validate()`:**

Add language parameter and TypeScript validation path:

```python
async def validate(
    self,
    code: str | None,
    config: dict[str, Any] | None,
    language: str = "python",
) -> ValidationResult:
    if language == "typescript":
        return await self._validate_typescript(code)
    # ... existing Python validation ...

async def _validate_typescript(self, code: str | None) -> ValidationResult:
    errors = []
    warnings = []

    if not code:
        errors.append("Code is required for code_sandbox backend")
        return ValidationResult(valid=False, errors=errors)

    if len(code) > 1024 * 1024:
        errors.append("Code exceeds maximum size (1MB)")

    # Syntax check via esbuild (fast, ~5ms)
    try:
        result = await self._esbuild_check(code)
        if not result.success:
            errors.extend(result.errors)
    except FileNotFoundError:
        # esbuild not installed — skip syntax check in dev
        warnings.append("esbuild not available; syntax not validated")

    # Dangerous patterns (defense-in-depth)
    TS_DANGEROUS = [
        "child_process", "eval(", "new Function(",
        "vm.runInNewContext", "vm.runInThisContext",
        "require('fs')", "import fs ",
    ]
    for pattern in TS_DANGEROUS:
        if pattern in code:
            warnings.append(f"Potentially dangerous pattern: {pattern}")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
```

**esbuild integration** — two options (pick one during implementation):

Option A: Shell out to esbuild binary (simpler, install via npm in API venv):
```python
async def _esbuild_check(self, code: str) -> ...:
    proc = await asyncio.create_subprocess_exec(
        "esbuild", "--bundle", "--platform=node", "--format=cjs",
        "--sourcefile=function.ts", "--loader=ts",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(code.encode()), timeout=10)
    ...
```

Option B: Python esbuild wrapper package (`esbuild` on PyPI).

**Recommendation:** Option A — shell out to the binary. Install esbuild via npm globally on the API container. It's a single static binary, no Node.js runtime needed on the host for this.

### 3B. TypeScript Execution Wrapper

**New file:** `deploy/nsjail/execute.js`

This is the Node.js equivalent of `execute.py`. Runs INSIDE the sandbox.

```javascript
#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const SANDBOX_DIR = "/sandbox";
const INPUT_PATH = path.join(SANDBOX_DIR, "input.json");
const OUTPUT_PATH = path.join(SANDBOX_DIR, "output.json");
const CODE_PATH = path.join(SANDBOX_DIR, "user_code.js");  // Pre-transpiled
const ENV_PATH = path.join(SANDBOX_DIR, ".sandbox_env.json");
const CONTEXT_PATH = path.join(SANDBOX_DIR, "context.json");
const TOKEN_PATH = path.join(SANDBOX_DIR, ".exec_token");
const CALL_LOG_PATH = path.join(SANDBOX_DIR, ".call_log");

const MAX_STDOUT = 64 * 1024;
const MAX_STDERR = 64 * 1024;
const MAX_OUTPUT = 1024 * 1024;

function truncate(text, max, label) {
  if (text.length <= max) return text;
  return text.slice(0, max) + `\n\n... [${label} truncated at ${max} bytes]`;
}

function writeOutput(obj) {
  let serialized = JSON.stringify(obj, (_, v) =>
    typeof v === "bigint" ? v.toString() : v
  );
  if (serialized.length > MAX_OUTPUT) {
    obj = {
      success: false, result: null,
      stdout: truncate(obj.stdout || "", MAX_STDOUT, "stdout"),
      stderr: truncate(obj.stderr || "", MAX_STDERR, "stderr"),
      error: `Output too large (${serialized.length} bytes, limit ${MAX_OUTPUT})`,
      error_type: "OutputSizeError", call_log: [],
    };
    serialized = JSON.stringify(obj);
  }
  fs.writeFileSync(OUTPUT_PATH, serialized);
}

async function main() {
  // Delete execution token
  try { fs.unlinkSync(TOKEN_PATH); } catch {}

  // Load env vars, delete file
  try {
    const envData = JSON.parse(fs.readFileSync(ENV_PATH, "utf-8"));
    fs.unlinkSync(ENV_PATH);
    Object.assign(process.env, envData);
  } catch {}

  // Read input
  let inputData = {};
  try { inputData = JSON.parse(fs.readFileSync(INPUT_PATH, "utf-8")); } catch {}

  // Read context
  let contextData = {};
  try { contextData = JSON.parse(fs.readFileSync(CONTEXT_PATH, "utf-8")); } catch {}

  // Capture stdout/stderr
  let capturedStdout = "";
  let capturedStderr = "";
  const origWrite = process.stdout.write.bind(process.stdout);
  const origErrWrite = process.stderr.write.bind(process.stderr);
  process.stdout.write = (chunk) => { capturedStdout += chunk; return true; };
  process.stderr.write = (chunk) => { capturedStderr += chunk; return true; };

  let result = null;
  let error = null;
  let errorType = null;
  let success = true;

  try {
    // Require user code (pre-transpiled JS)
    const userModule = require(CODE_PATH);

    // Detect entry point
    const entryFn = userModule.default?.main
      || userModule.default
      || userModule.main
      || userModule.handler;

    if (typeof entryFn === "function") {
      const fnResult = entryFn(inputData, contextData);
      result = fnResult instanceof Promise ? await fnResult : fnResult;
    } else if (userModule.result !== undefined) {
      result = userModule.result;
    } else if (userModule.output !== undefined) {
      result = userModule.output;
    } else if (userModule.default && typeof userModule.default !== "function") {
      result = userModule.default;
    }
  } catch (e) {
    success = false;
    error = e.message || String(e);
    errorType = e.constructor?.name || "Error";
    capturedStderr += e.stack || "";
  } finally {
    process.stdout.write = origWrite;
    process.stderr.write = origErrWrite;
  }

  // Read call log
  let callLog = [];
  try {
    callLog = fs.readFileSync(CALL_LOG_PATH, "utf-8")
      .split("\n").filter(Boolean);
  } catch {}

  writeOutput({
    success, result,
    stdout: truncate(capturedStdout, MAX_STDOUT, "stdout"),
    stderr: truncate(capturedStderr, MAX_STDERR, "stderr"),
    error, error_type: errorType, call_log: callLog,
  });
}

main().catch((e) => {
  writeOutput({
    success: false, result: null, stdout: "", stderr: e.stack || String(e),
    error: e.message, error_type: "FatalError", call_log: [],
  });
  process.exit(1);
});
```

**Key differences from Python `execute.py`:**
- No `_harden_sandbox()` equivalent — Node.js doesn't have Python's introspection surface (no `sys._getframe`, no `gc.get_objects`, no ctypes). Defense-in-depth is handled by seccomp + nsjail.
- `require()` instead of `exec()` — safer, provides proper module scoping
- Async by default — `main()` is async, awaits the user function if it returns a Promise
- User code is pre-transpiled to `.js` on the host (esbuild runs before sandbox entry)

### 3C. Transpilation Step in SandboxBackend

**File:** `src/mcpworks_api/backends/sandbox.py`

**Add transpilation method:**
```python
async def _transpile_typescript(self, code: str) -> tuple[str, list[str]]:
    """Transpile TypeScript to JavaScript using esbuild.

    Runs on the host, NOT inside the sandbox. Returns (js_code, errors).
    """
    proc = await asyncio.create_subprocess_exec(
        "esbuild", "--bundle=false", "--platform=node",
        "--format=cjs", "--target=node22",
        "--sourcefile=function.ts", "--loader=ts",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(code.encode()), timeout=10
    )
    if proc.returncode != 0:
        return "", [stderr.decode().strip()]
    return stdout.decode(), []
```

**Changes to `_execute_dev_mode()` and `_execute_nsjail()`:**

Both methods need a language dispatch. Extract the common pattern:

```python
async def execute(self, code, config, input_data, account, execution_id,
                  timeout_ms=30000, extra_files=None, sandbox_env=None,
                  context=None, language="python"):
    # ... existing validation ...

    # Transpile TypeScript on host before sandbox entry
    if language == "typescript":
        js_code, errors = await self._transpile_typescript(code)
        if errors:
            return ExecutionResult(
                success=False, output=None,
                error="; ".join(errors), error_type="TranspileError",
            )
        code = js_code  # Use transpiled JS from here on

    # ... rest of execution (dev_mode or nsjail) ...
```

**Changes to `_execute_dev_mode()` for TypeScript:**
- Write code to `user_code.js` instead of `user_code.py`
- Run `node /path/to/execute.js` wrapper instead of `python3` wrapper
- Or: write the transpiled code directly and run `node user_code.js` with the JS wrapper prepended

**Changes to `_execute_nsjail()` for TypeScript:**
- Write transpiled JS as `user_code.js`
- Pass `language` argument to spawn-sandbox.sh

### 3D. Spawn Script Updates

**File:** `deploy/nsjail/spawn-sandbox.sh`

**Changes:**

Add `LANGUAGE` as 7th argument (after `EXEC_TOKEN_FILE`):

```bash
LANGUAGE="${7:-python}"  # Default: python for backward compatibility
```

File copy section — dispatch based on language:

```bash
if [ "${LANGUAGE}" = "typescript" ]; then
    # Copy transpiled JS (code_path already points to .js file)
    cp "${CODE_PATH}" "${WORKSPACE}/user_code.js"
    cp /opt/mcpworks/bin/execute.js "${WORKSPACE}/.e.js"
else
    cp "${CODE_PATH}" "${WORKSPACE}/user_code.py"
    cp /opt/mcpworks/bin/execute.pyc "${WORKSPACE}/.e"
fi
```

nsjail command — select runtime:

```bash
if [ "${LANGUAGE}" = "typescript" ]; then
    # Node.js seccomp policy (includes V8 JIT syscalls)
    SECCOMP_POLICY="/etc/mcpworks/seccomp-node.policy"

    ${NSJAIL_PREFIX} "${NSJAIL}" \
        "${NSJAIL_ARGS[@]}" \
        --seccomp_policy "${SECCOMP_POLICY}" \
        --execute_fd \
        -- \
        /usr/local/bin/node --max-old-space-size="${MEMORY}" /sandbox/.e.js
else
    ${NSJAIL_PREFIX} "${NSJAIL}" \
        "${NSJAIL_ARGS[@]}" \
        --execute_fd \
        -- \
        /usr/local/bin/python3 -S /sandbox/.e
fi
```

**Note:** `--max-old-space-size` limits V8 heap to match the tier memory limit. Without this, V8 defaults to ~1.5GB regardless of cgroup limits.

Also remove the Python-specific `_ctypes`/`_posixsubprocess` bind mounts when running TypeScript (they reference Python `.so` paths that don't exist for Node):

```bash
if [ "${LANGUAGE}" != "typescript" ]; then
    # Python-specific: hide dangerous C extensions
    NSJAIL_ARGS+=(--bindmount_ro "${WORKSPACE}/.empty:...")
    ...
fi
```

### 3E. Node.js Seccomp Policy

**New file:** `deploy/nsjail/seccomp-node.policy`

Start from the existing `seccomp.policy` and add V8-required syscalls. The key additions:

```c
/* V8 JIT compilation requires writable+executable memory mappings.
 * This is the single most significant security difference from Python.
 * Mitigated by: PID/NET/MNT/UTS/IPC namespaces, cgroups, UID mapping,
 * chroot, capability dropping, network isolation.
 * Same risk profile as Cloudflare Workers, AWS Lambda, Deno Deploy. */

/* Already in Python policy — no change needed:
 *   mmap, mprotect, clone, clone3, eventfd2, pipe2, dup, dup2,
 *   prctl, sched_getaffinity, prlimit64, ioctl
 *
 * The Python policy already allows all syscalls V8 needs.
 * After careful review: no additions required.
 */
```

**IMPORTANT FINDING:** After reviewing the existing seccomp policy, it already allows every syscall that V8/Node.js requires:
- `mmap` with `mprotect` — already allowed (needed by numpy BLAS)
- `prctl` — already allowed
- `sched_getaffinity` — already allowed
- `prlimit64` — already allowed
- `eventfd2` — already allowed
- `pipe2` — already allowed
- `dup`, `dup2` — already allowed
- `ioctl` — already allowed

**Decision:** Use the SAME seccomp policy for both Python and Node.js. The existing Python policy is already permissive enough for V8 because numpy/scipy BLAS libraries need the same JIT-style memory mappings.

This simplifies implementation significantly — no separate seccomp file needed. However, still rename the existing file for clarity:
- `seccomp.policy` → keep as-is (don't break existing deploys)
- Document in the file header that it supports both Python and Node.js

### 3F. sandbox.py Execute Dispatch

**File:** `src/mcpworks_api/backends/sandbox.py`

**Full change list for `execute()`:**

1. Add `language` parameter (default `"python"`)
2. Transpile TS → JS if `language="typescript"`
3. Pass language through to `_execute_dev_mode()` / `_execute_nsjail()`

**For `_execute_dev_mode()`:**

```python
async def _execute_dev_mode(self, ..., language="python"):
    # ...
    if language == "typescript":
        code_file = exec_dir / "user_code.js"
        # Write wrapper that loads the user code
        wrapper_code = self._wrap_ts_code(code)
        code_file.write_text(wrapper_code)
        cmd = ["node", str(code_file)]
    else:
        code_file = exec_dir / "user_code.py"
        wrapped_code = self._wrap_code(code)
        code_file.write_text(wrapped_code)
        cmd = ["python3", str(code_file), str(input_file), str(output_file)]

    process = await asyncio.create_subprocess_exec(
        *cmd, ...
    )
```

**New method `_wrap_ts_code()`:**
```python
def _wrap_ts_code(self, code: str) -> str:
    """Wrap transpiled JS with execution harness for dev mode."""
    # Inline the execute.js logic, adapted for dev mode
    # (reads input/output from argv paths like Python wrapper)
    ...
```

**For `_execute_nsjail()`:**

```python
async def _execute_nsjail(self, ..., language="python"):
    # Write code file with correct extension
    if language == "typescript":
        (exec_dir / "user_code.js").write_text(code)  # Already transpiled
    else:
        (exec_dir / "user_code.py").write_text(code)

    # Pass language to spawn script
    process = await asyncio.create_subprocess_exec(
        str(self.spawn_script),
        execution_id,
        tier,
        str(code_file),
        str(exec_dir / "input.json"),
        namespace,
        str(token_file),
        language,  # NEW 7th arg
        ...
    )
```

**Update `supported_languages` property:**
```python
@property
def supported_languages(self) -> list[str]:
    return ["python", "typescript"]
```

**Update `description` property:**
```python
@property
def description(self) -> str:
    if self._dev_mode:
        return "Code sandbox (development mode - NOT SECURE)"
    return "Secure Python/TypeScript code execution sandbox"
```

### Phase 3 Test Checklist

- [ ] esbuild transpilation works (types stripped, enums compiled)
- [ ] esbuild catches syntax errors
- [ ] TypeScript dangerous patterns detected
- [ ] Dev mode: TypeScript function executes with `node`
- [ ] Dev mode: All 4 entry point patterns work
- [ ] Dev mode: Async entry point awaited correctly
- [ ] Dev mode: stdout/stderr captured
- [ ] Dev mode: Timeout kills Node.js process
- [ ] Dev mode: output.json written correctly
- [ ] nsjail mode: spawn-sandbox.sh selects Node.js binary
- [ ] nsjail mode: V8 starts without seccomp violations
- [ ] nsjail mode: Node.js respects memory limit via `--max-old-space-size`
- [ ] nsjail mode: Environment variables injected correctly

---

## Phase 4: MCP Interface & Templates

**Goal:** LLMs can create and execute TypeScript functions through the MCP tool interface.

### 4A. make_function Tool Schema

**File:** `src/mcpworks_api/mcp/create_handler.py`

**Changes to `get_tools()` make_function entry:**

Add `language` property to inputSchema:
```python
"language": {
    "type": "string",
    "enum": ["python", "typescript"],
    "description": (
        "Programming language for the function. Default: 'python'. "
        "Use 'typescript' for TypeScript/JavaScript functions. "
        "Language cannot be changed after creation."
    ),
},
```

Update `code` description to include TypeScript entry points:
```python
"description": (
    "Source code for code_sandbox backend. "
    "NEVER hardcode API keys, tokens, secrets, or credentials in code. "
    "\n\nPython entry points: "
    "1) 'result = ...' 2) 'def main(input):' 3) 'def handler(input, context):' "
    "\n\nTypeScript entry points: "
    "1) 'export default function main(input) { ... }' "
    "2) 'export default function handler(input, context) { ... }' "
    "3) 'module.exports.main = function(input) { ... }' "
    "4) 'const result = ...' "
),
```

Update `requirements` description:
```python
"description": (
    "Packages needed (must be from the allowed list). "
    "Use list_packages to see available packages for your language. "
    "Python: ['httpx', 'pandas'] | TypeScript: ['axios', 'zod']"
),
```

### 4B. update_function Tool Schema

**File:** `src/mcpworks_api/mcp/create_handler.py`

- Do NOT add `language` to update_function — language is immutable
- Update `code` description to mention both languages

### 4C. _make_function Handler

**File:** `src/mcpworks_api/mcp/create_handler.py`

**Changes to `_make_function()` method:**

```python
language = args.get("language", "python")
if language not in ("python", "typescript"):
    return "Invalid language. Must be 'python' or 'typescript'."

# Validate requirements against correct language registry
if requirements:
    validated, errors = validate_requirements_for_language(requirements, language)
    if errors:
        return f"Invalid requirements: {'; '.join(errors)}"
    requirements = validated

# Validate code with language-aware backend
validation = await backend.validate(code, config, language=language)

# Pass language to service
fn = await self.function_service.create(
    ..., language=language, ...
)
```

### 4D. _update_function Handler

**File:** `src/mcpworks_api/mcp/create_handler.py`

Validate requirements against the function's existing language:
```python
# Get existing function to determine language
fn = await self.function_service.get_by_name(...)
active_version = fn.get_active_version_obj()
language = active_version.language if active_version else "python"

if requirements:
    validated, errors = validate_requirements_for_language(requirements, language)
    ...
```

### 4E. describe_function Response

**File:** `src/mcpworks_api/mcp/create_handler.py`

In `_describe_function()`, the response already calls `self.function_service.describe()` which will include `language` after Phase 1 changes.

### 4F. Run Handler

**File:** `src/mcpworks_api/mcp/run_handler.py`

When executing a function, pass language to the backend:
```python
result = await backend.execute(
    code=version.code,
    ...,
    language=version.language,  # NEW
)
```

Also: when generating the dynamic tool list for the run server, include `language` in the tool description so the LLM knows what language each function uses.

### 4G. Templates

**File:** `src/mcpworks_api/templates.py`

**Changes to `FunctionTemplate`:**
```python
def __init__(self, ..., language: str = "python"):
    ...
    self.language = language
```

**Add 3 TypeScript templates** (code from spec REQ-TS-050):
- `hello-world-ts`
- `api-connector-ts`
- `json-transformer-ts`

Each with `language="typescript"` and appropriate npm `requirements`.

**Update `list_templates` and `get_template`:**
- `to_dict()` and `to_full_dict()` include `language` field
- Optional `language` filter on `list_templates()`

### 4H. Execution Metrics

**File:** `src/mcpworks_api/middleware/execution_metrics.py`

Add `language` label to Prometheus metrics:
```python
# Existing: sandbox_executions_total{tier, status, namespace}
# New:      sandbox_executions_total{tier, status, namespace, language}
```

### Phase 4 Test Checklist

- [ ] `make_function(language="typescript")` creates TS function
- [ ] `make_function()` without language defaults to Python
- [ ] `update_function` on TS function validates against Node.js package list
- [ ] `update_function` cannot change language
- [ ] `describe_function` shows language
- [ ] `list_packages(language="typescript")` returns Node.js packages
- [ ] `list_templates` shows both Python and TypeScript templates
- [ ] `describe_template(name="hello-world-ts")` returns TS template
- [ ] Run server executes TypeScript function correctly
- [ ] Metrics include language label

---

## Phase 5: Docker Image & Deployment

**Goal:** Production image includes Node.js 22 and pre-installed npm packages.

### 5A. Dockerfile — New Stage

**File:** `Dockerfile`

Add after sandbox-builder stage (before nsjail-builder):

```dockerfile
# =============================================================================
# Stage 1b: Node.js sandbox packages — pre-installed npm packages
# =============================================================================
FROM node:22-slim AS node-sandbox-builder

WORKDIR /node-packages

# Install packages into a flat node_modules directory
COPY deploy/nsjail/package.json .
RUN npm install --production --no-optional \
    && rm -rf /node-packages/node_modules/.package-lock.json
```

**New file:** `deploy/nsjail/package.json`
```json
{
  "name": "mcpworks-sandbox-packages",
  "private": true,
  "dependencies": {
    "lodash": "4.17.21",
    "date-fns": "4.1.0",
    "uuid": "11.1.0",
    "zod": "3.24.4",
    "csv-parse": "5.6.0",
    "csv-stringify": "6.5.2",
    "yaml": "2.7.1",
    "cheerio": "1.0.0",
    "marked": "15.0.7",
    "axios": "1.9.0",
    "jsonwebtoken": "9.0.2",
    "bcryptjs": "3.0.2",
    "xml2js": "0.6.2",
    "ajv": "8.17.1",
    "openai": "5.8.0",
    "@anthropic-ai/sdk": "0.52.0"
  }
}
```

### 5B. Dockerfile — Production Stage

**File:** `Dockerfile` (production stage)

Add Node.js binary:
```dockerfile
# Copy Node.js binary from official image (no npm needed in sandbox)
COPY --from=node:22-slim /usr/local/bin/node /opt/mcpworks/sandbox-root/usr/local/bin/node

# Copy pre-installed npm packages
COPY --from=node-sandbox-builder /node-packages/node_modules /opt/mcpworks/sandbox-root/node_modules

# Copy TypeScript execution wrapper
COPY deploy/nsjail/execute.js /opt/mcpworks/bin/execute.js
```

Install esbuild on the host (for transpilation):
```dockerfile
# esbuild for TypeScript transpilation (runs on host, not in sandbox)
RUN npm install -g esbuild@0.25.0 || true
```

**Note:** This requires npm on the host image. Since the host already has Python, adding Node.js (just for esbuild) to the host is a choice. Alternative: download the esbuild binary directly (it's a single Go binary):
```dockerfile
RUN curl -fsSL https://esbuild.github.io/dl/v0.25.0 | sh \
    && mv esbuild /usr/local/bin/esbuild
```

### 5C. nsjail Config — Node.js Bind Mounts

**File:** `deploy/nsjail/python.cfg`

Add Node.js bind mount (read-only):
```protobuf
mount {
    src: "/opt/mcpworks/sandbox-root/usr/local/bin/node"
    dst: "/usr/local/bin/node"
    is_bind: true
    rw: false
}

mount {
    src: "/opt/mcpworks/sandbox-root/node_modules"
    dst: "/usr/local/lib/node_modules"
    is_bind: true
    rw: false
}
```

Set `NODE_PATH` in nsjail environment so `require()` finds packages:
```protobuf
envar: "NODE_PATH=/usr/local/lib/node_modules"
```

### 5D. Spawn Script — NODE_PATH

**File:** `deploy/nsjail/spawn-sandbox.sh`

For TypeScript execution, add `NODE_PATH` to the nsjail args:
```bash
if [ "${LANGUAGE}" = "typescript" ]; then
    NSJAIL_ARGS+=(--env "NODE_PATH=/usr/local/lib/node_modules")
fi
```

### Phase 5 Test Checklist

- [ ] Docker image builds successfully with Node.js stage
- [ ] `node --version` works inside nsjail sandbox
- [ ] `require('lodash')` works inside sandbox
- [ ] `require('nonexistent')` fails with clear error
- [ ] esbuild binary works on host
- [ ] Full end-to-end: create TS function → execute → get result
- [ ] Python functions still work (regression)
- [ ] Image size increase is acceptable (~50-80MB for Node.js + packages)

---

## Complete File Change List

### Modified Files (15)

| File | Phase | Changes |
|------|-------|---------|
| `src/mcpworks_api/models/function_version.py` | 1 | Add `language` column, `ALLOWED_LANGUAGES`, validator |
| `src/mcpworks_api/schemas/function.py` | 1 | Add `language` field to create/response schemas |
| `src/mcpworks_api/services/function.py` | 1 | Thread `language` through create/create_version/describe |
| `src/mcpworks_api/sandbox/packages.py` | 2 | Add `validate_requirements_for_language()` dispatcher |
| `src/mcpworks_api/backends/sandbox.py` | 3 | TS validation, transpilation, execute dispatch, wrap_ts_code |
| `src/mcpworks_api/backends/base.py` | 3 | Add `language` param to `execute()` and `validate()` signatures |
| `deploy/nsjail/spawn-sandbox.sh` | 3 | Language arg, Node.js binary selection, NODE_PATH |
| `deploy/nsjail/python.cfg` | 5 | Node.js bind mounts |
| `deploy/nsjail/seccomp.policy` | 3 | Header comment update (no syscall changes needed) |
| `src/mcpworks_api/mcp/create_handler.py` | 4 | Tool schemas, make/update/describe handlers |
| `src/mcpworks_api/mcp/run_handler.py` | 4 | Pass `language` to backend.execute() |
| `src/mcpworks_api/templates.py` | 4 | `language` field, 3 TS templates |
| `src/mcpworks_api/middleware/execution_metrics.py` | 4 | Add `language` label to metrics |
| `src/mcpworks_api/backends/__init__.py` | 3 | Update docstring |
| `Dockerfile` | 5 | Node.js stage, esbuild, execute.js copy |

### New Files (4)

| File | Phase | Purpose |
|------|-------|---------|
| `alembic/versions/20260316_000001_add_language_to_function_versions.py` | 1 | DB migration |
| `src/mcpworks_api/sandbox/packages_node.py` | 2 | Node.js package allowlist |
| `deploy/nsjail/execute.js` | 3 | Node.js execution wrapper (runs inside sandbox) |
| `deploy/nsjail/package.json` | 5 | npm package manifest for sandbox image |

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| V8 needs syscall not in policy | Execution fails | Low | Existing policy already covers V8 needs; smoketest catches gaps |
| esbuild unavailable in prod | TS creation fails, Python unaffected | Low | Health check includes esbuild binary presence |
| Node.js OOM ignores cgroup | Resource exhaustion | Medium | `--max-old-space-size` flag + cgroup v2 as backstop |
| npm package CVE | Security vulnerability | Medium | Weekly `npm audit` in CI, same as Python `pip audit` |
| Language immutability too strict | User frustration | Low | Clear error message; creating a new function is trivial |

---

## Rollout Plan

1. **Dev mode first:** Implement and test all changes with `SANDBOX_DEV_MODE=true` (no nsjail)
2. **Smoketest:** Run existing Python smoketest + new Node.js smoketest in Docker
3. **Staging deploy:** Deploy to prod with TypeScript behind feature flag (`FEATURE_TS_SANDBOX=true`)
4. **Remove flag:** Once confirmed working, remove flag and announce in changelog

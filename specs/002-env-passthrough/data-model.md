# Data Model: Environment Variable Passthrough

**Feature**: 002-env-passthrough
**Date**: 2026-02-19

## Entity Changes

### FunctionVersion (modified)

Existing entity in `function_versions` table. Two new columns added.

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `required_env` | `ARRAY(String)` | Yes | Env var names the function requires. Execution fails if any are missing from request. |
| `optional_env` | `ARRAY(String)` | Yes | Env var names the function can use. Silently omitted if not in request. |

**Validation rules**:
- Each name must match `^[A-Z][A-Z0-9_]{0,127}$`
- Max 20 names per list (combined `required_env` + `optional_env`)
- Names must not be in the blocklist (PATH, LD_*, PYTHON*, MCPWORKS_*, etc.)
- Names must not duplicate between `required_env` and `optional_env`
- `NULL` means the function declares no env var needs (default, backward compatible)

**Migration**: `20260219_000001_add_env_declarations_to_function_versions.py`

```sql
ALTER TABLE function_versions ADD COLUMN required_env VARCHAR[] DEFAULT NULL;
ALTER TABLE function_versions ADD COLUMN optional_env VARCHAR[] DEFAULT NULL;
```

### No New Entities

No new tables are created. Env var values are never persisted — they exist only in-memory during request processing and in a tmpfs file during sandbox execution.

## Transient Data Structures (Not Persisted)

### EnvPassthroughPayload (in-memory only)

Decoded from the `X-MCPWorks-Env` HTTP header. Lives in the `call_tool()` coroutine's local scope.

```python
# Type: dict[str, str]
# Example:
{
    "OPENAI_API_KEY": "sk-proj-...",
    "DATABASE_URL": "postgres://...",
}
```

**Lifecycle**:
1. Extracted from HTTP header in `call_tool()`
2. Filtered by function's `required_env`/`optional_env` in `dispatch_tool()`
3. Written to `.sandbox_env.json` in tmpfs by `SandboxBackend._execute_nsjail()`
4. Read by `execute.py` inside sandbox, injected into `os.environ`, file deleted
5. All references released when coroutine completes

### SandboxEnvFile (tmpfs only)

Written to `{workspace}/.sandbox_env.json` inside the tmpfs mount.

```json
{"OPENAI_API_KEY": "sk-proj-...", "DATABASE_URL": "postgres://..."}
```

**Lifecycle**:
1. Written by `sandbox.py` before spawning nsjail
2. Copied into workspace by `spawn-sandbox.sh`
3. Read and deleted by `execute.py` before user code runs
4. tmpfs unmounted by `cleanup()` trap on exit

## State Transitions

### Function Env Declaration Lifecycle

```
FunctionVersion created without env declarations
    → required_env: NULL, optional_env: NULL
    → All env vars from request silently dropped (function gets none)

FunctionVersion created with declarations
    → required_env: ["OPENAI_API_KEY"], optional_env: ["DEBUG"]
    → Only declared vars injected; missing required vars → fast fail

FunctionVersion updated (new version created)
    → New version can change declarations
    → Old version's declarations unchanged (immutable)
```

### Request-Level Env Var Flow

```
Header absent → empty dict → functions with no required_env work fine
                            → functions with required_env fail with missing_env error

Header present, valid → decoded dict
    → filter by function declarations
        → all required present → inject into sandbox → execute
        → required missing → fail fast with missing_env error
        → optional missing → silently omit, execute with what's available

Header present, invalid → 400 error before tool dispatch
```

## Relationships

```
Account ──1:N──> Namespace ──1:N──> Service ──1:N──> Function ──1:N──> FunctionVersion
                                                                            │
                                                                    required_env[]
                                                                    optional_env[]
```

No new relationships. The env declarations are attributes of FunctionVersion.

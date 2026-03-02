"""
MCP Platform Stress Test — Manual End-to-End
=============================================

Exercises the full create → execute → update → delete lifecycle via the
MCP connector (mcpworks-create + mcpworks-run), hitting a live production
or staging environment.

Usage (from Claude Code with MCP connectors configured):
    Run this file via mcp__mcpworks-run__execute, or paste sections into
    the execute sandbox interactively.

    Alternatively, use it as a reference script — each section is labeled
    and can be run independently.

First run: 2026-03-01 (post allowlist migration deploy)
"""

# ── CONFIG ──────────────────────────────────────────────────────────────
SERVICE = "tools"
FUNCTION_PREFIX = "stresstest_"
FUNCTIONS = {
    "counter": {
        "description": "Count to N and return stats",
        "code": """
import time
def main(input_data):
    n = input_data.get("n", 10000)
    start = time.time()
    total = sum(range(n))
    elapsed = time.time() - start
    return {"sum": total, "n": n, "elapsed_ms": round(elapsed * 1000, 2)}
""",
        "input_schema": {
            "type": "object",
            "properties": {"n": {"type": "integer", "default": 10000}},
        },
    },
    "memory": {
        "description": "Allocate and process a large list to test memory handling",
        "code": """
import sys
def main(input_data):
    size = input_data.get("size", 100000)
    data = list(range(size))
    total = sum(data)
    return {"size": size, "sum": total, "list_memory_bytes": sys.getsizeof(data)}
""",
        "input_schema": {
            "type": "object",
            "properties": {"size": {"type": "integer", "default": 100000}},
        },
    },
    "json_serde": {
        "description": "Serialize and deserialize nested JSON payloads",
        "code": """
import json, time
def main(input_data):
    depth = input_data.get("depth", 5)
    width = input_data.get("width", 10)
    def build(d):
        if d == 0:
            return "leaf"
        return {f"key_{i}": build(d - 1) for i in range(width)}
    start = time.time()
    obj = build(depth)
    serialized = json.dumps(obj)
    json.loads(serialized)
    elapsed = time.time() - start
    return {"depth": depth, "width": width, "json_bytes": len(serialized), "elapsed_ms": round(elapsed * 1000, 2)}
""",
        "input_schema": {
            "type": "object",
            "properties": {
                "depth": {"type": "integer", "default": 5},
                "width": {"type": "integer", "default": 10},
            },
        },
    },
    "fibonacci": {
        "description": "Compute Fibonacci via matrix exponentiation",
        "code": """
import time, sys
def mat_mult(A, B):
    return [
        [A[0][0]*B[0][0] + A[0][1]*B[1][0], A[0][0]*B[0][1] + A[0][1]*B[1][1]],
        [A[1][0]*B[0][0] + A[1][1]*B[1][0], A[1][0]*B[0][1] + A[1][1]*B[1][1]],
    ]
def mat_pow(M, n):
    if n == 1:
        return M
    if n % 2 == 0:
        half = mat_pow(M, n // 2)
        return mat_mult(half, half)
    return mat_mult(M, mat_pow(M, n - 1))
def main(input_data):
    n = input_data.get("n", 1000)
    sys.set_int_max_str_digits(100000)
    start = time.time()
    if n <= 1:
        fib = n
    else:
        R = mat_pow([[1, 1], [1, 0]], n)
        fib = R[0][1]
    elapsed = time.time() - start
    s = str(fib)
    return {"n": n, "digits": len(s), "first_20": s[:20], "last_20": s[-20:], "elapsed_ms": round(elapsed * 1000, 2)}
""",
        "input_schema": {
            "type": "object",
            "properties": {"n": {"type": "integer", "default": 1000}},
        },
    },
    "crasher": {
        "description": "Intentionally raises RuntimeError — tests error handling",
        "code": """
def main(input_data):
    raise RuntimeError("intentional crash for testing")
""",
        "input_schema": {"type": "object"},
    },
}

# ── UPDATE VARIANT ──────────────────────────────────────────────────────
# Used for the "update and re-execute" step — replaces counter v1
COUNTER_V2_CODE = """
import time
def main(input_data):
    n = input_data.get("n", 10000)
    chunks = input_data.get("chunks", 4)
    start = time.time()
    chunk_size = n // chunks
    results = []
    for i in range(chunks):
        lo = i * chunk_size
        hi = lo + chunk_size if i < chunks - 1 else n
        results.append(sum(range(lo, hi)))
    total = sum(results)
    elapsed = time.time() - start
    return {"sum": total, "n": n, "chunks": chunks, "elapsed_ms": round(elapsed * 1000, 2), "version": 2}
"""

# ── TEST PROCEDURE ──────────────────────────────────────────────────────
#
# The test is designed to be run interactively via Claude Code with
# mcpworks MCP connectors.  Each step maps to MCP tool calls.
#
# STEP 1: CREATE FUNCTIONS
# ────────────────────────
# For each entry in FUNCTIONS:
#   mcp__mcpworks-create__make_function(
#       service=SERVICE,
#       name=f"{FUNCTION_PREFIX}{key}",
#       backend="code_sandbox",
#       description=val["description"],
#       code=val["code"],
#       input_schema=val["input_schema"],
#       tags=["stress", "test"],
#       created_by="Claude Opus 4.6",
#   )
# Expected: All return version 1, no errors.
#
# STEP 2: EXECUTE — PARALLEL HAPPY PATH
# ──────────────────────────────────────
# Run all non-crasher functions in parallel via mcp__mcpworks-run__execute:
#   counter(n=500000)        → expect {"sum": 124999750000, ...}
#   memory(size=500000)      → expect {"sum": 124999750000, "list_memory_bytes": ~4000056}
#   json_serde(depth=4, width=15)  → expect {"json_bytes": ~918470, ...}
#   fibonacci(n=10000)       → expect {"digits": 2090, ...}
#
# STEP 3: EXECUTE — ERROR HANDLING
# ────────────────────────────────
# Run crasher:
#   crasher()  → expect {"error": "intentional crash for testing", "error_type": "RuntimeError"}
#
# STEP 4: UPDATE FUNCTION (VERSION BUMP)
# ──────────────────────────────────────
# Update counter with COUNTER_V2_CODE via mcp__mcpworks-create__update_function.
# Expected: version bumps to 2.
#
# STEP 5: EXECUTE UPDATED VERSION
# ───────────────────────────────
# Run counter(n=1000000) — should use v2 code with chunks support.
# Expected: {"sum": 499999500000, "chunks": 4, "version": 2, ...}
#
# STEP 6: MULTI-FUNCTION CHAINING
# ───────────────────────────────
# Single sandbox execution that imports and calls multiple functions:
#   from functions import stresstest_counter, stresstest_memory, stresstest_json_serde
#   r1 = stresstest_counter(n=250000)
#   r2 = stresstest_memory(size=250000)
#   r3 = stresstest_json_serde(depth=3, width=20)
#   result = {"counter": r1, "memory": r2, "json": r3}
# Expected: All three results returned in one response.
#
# STEP 7: BATCH LOOP EXECUTION
# ────────────────────────────
# Single sandbox that loops over multiple inputs:
#   from functions import stresstest_fibonacci
#   result = [stresstest_fibonacci(n=n) for n in [100, 1000, 5000, 10000, 25000]]
# Expected: List of 5 results with increasing digit counts.
#
# STEP 8: DESCRIBE — VERIFY VERSION HISTORY
# ─────────────────────────────────────────
# mcp__mcpworks-create__describe_function(service=SERVICE, name="stresstest_counter")
# Expected: active_version=2, versions list shows [v2, v1].
#
# STEP 9: DELETE ALL TEST FUNCTIONS
# ─────────────────────────────────
# For each function:
#   mcp__mcpworks-create__delete_function(service=SERVICE, name=...)
# Expected: All deleted successfully.
#
# STEP 10: VERIFY DELETION
# ────────────────────────
# Try to import a deleted function in the sandbox:
#   from functions import stresstest_counter  → ImportError
# And list functions to confirm originals remain:
#   mcp__mcpworks-create__list_functions(service=SERVICE)
# Expected: Only pre-existing functions remain.
#
# ── SCORECARD ───────────────────────────────────────────────────────────
#
# | Operation                 | Count | Pass Criteria                        |
# |---------------------------|-------|--------------------------------------|
# | Create function           |   5   | All return version 1                 |
# | Execute (happy path)      |   4   | Correct math results, <500ms each   |
# | Execute (error handling)  |   1   | Structured error, no crash           |
# | Update function           |   1   | Version bumps to 2                  |
# | Execute updated version   |   1   | Returns v2 output                   |
# | Multi-function chaining   |   1   | 3 results in one sandbox call        |
# | Batch loop execution      |   1   | 5 results returned as list           |
# | Describe (version history)|   1   | Shows v2 active, [v2, v1] history   |
# | Delete function           |   5   | All deleted                          |
# | Verify deletion           |   1   | ImportError + list confirms cleanup  |
# |---------------------------|-------|--------------------------------------|
# | TOTAL                     |  21   |                                      |
#
# ── BASELINE RESULTS (2026-03-01) ──────────────────────────────────────
#
# Environment: production (api.mcpworks.io)
# Commit: b9b3f6f (post allowlist migration)
#
# | Function        | Input              | Result                          | Time    |
# |-----------------|--------------------|---------------------------------|---------|
# | counter v1      | n=500,000          | sum=124,999,750,000             | 12.7ms  |
# | counter v2      | n=1,000,000        | sum=499,999,500,000 (4 chunks)  | 19.9ms  |
# | memory          | size=500,000       | 4,000,056 bytes allocated       | <50ms   |
# | memory          | size=1,000,000     | 8,000,056 bytes allocated       | <50ms   |
# | json_serde      | depth=4, width=15  | 918,470 bytes JSON              | 94.1ms  |
# | json_serde      | depth=5, width=10  | 1,822,210 bytes JSON            | 173.7ms |
# | fibonacci       | n=10,000           | 2,090 digits                    | 0.18ms  |
# | fibonacci       | n=50,000           | 10,450 digits                   | 3.0ms   |
# | crasher         | (none)             | RuntimeError caught, structured | N/A     |
# | multi-chain     | 3 functions        | All returned in one call         | <50ms   |
# | batch fib loop  | n=100..25000       | 5 results, 21..5225 digits      | <1ms ea |

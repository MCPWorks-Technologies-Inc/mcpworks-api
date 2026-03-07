#!/usr/bin/env python3
"""MCPWorks Sandbox Execution Wrapper.

Runs INSIDE the nsjail sandbox. Stdlib only (no API packages visible).
Reads /sandbox/input.json, executes /sandbox/user_code.py,
writes structured output to /sandbox/output.json.

Supports three result patterns (matching dev-mode _wrap_code):
  1. `result = ...`       — explicit result variable
  2. `output = ...`       — alias for result
  3. `def main(input_data)` — callable that receives input
"""

import json
import sys
import traceback
from io import StringIO

SANDBOX_DIR = "/sandbox"
INPUT_PATH = f"{SANDBOX_DIR}/input.json"
OUTPUT_PATH = f"{SANDBOX_DIR}/output.json"
CODE_PATH = f"{SANDBOX_DIR}/user_code.py"
TOKEN_PATH = f"{SANDBOX_DIR}/.exec_token"
ENV_PATH = f"{SANDBOX_DIR}/.sandbox_env.json"

# Output size limits (defense-in-depth against json-bomb / stdout-flood)
MAX_STDOUT_BYTES = 64 * 1024  # 64 KB per stream
MAX_STDERR_BYTES = 64 * 1024  # 64 KB per stream
MAX_OUTPUT_JSON_BYTES = 1024 * 1024  # 1 MB total output


def run():
    # ORDER-003: Delete execution token file if present.
    # Token is never exposed to user code (SECURITY_AUDIT.md FINDING-03).
    try:
        import os

        os.unlink(TOKEN_PATH)
    except FileNotFoundError:
        pass

    # ENV PASSTHROUGH: Read user-provided env vars, delete file, inject into os.environ.
    # File lifecycle: written to tmpfs by spawn-sandbox.sh, read here, unlinked immediately.
    try:
        import os as _os

        with open(ENV_PATH) as f:
            _env_data = json.load(f)
        _os.unlink(ENV_PATH)
        if isinstance(_env_data, dict):
            _os.environ.update(_env_data)
        del _env_data
    except (FileNotFoundError, Exception):
        pass

    # Read input data
    try:
        with open(INPUT_PATH) as f:
            input_data = json.load(f)
    except Exception:
        input_data = {}

    # Read user code
    try:
        with open(CODE_PATH) as f:
            code = f.read()
    except Exception as e:
        _write_output(success=False, error=str(e), error_type="FileError")
        return

    # Capture stdout/stderr
    old_stdout, old_stderr = sys.stdout, sys.stderr
    captured_stdout = StringIO()
    captured_stderr = StringIO()
    sys.stdout = captured_stdout
    sys.stderr = captured_stderr

    result = None
    error = None
    error_type = None
    success = True

    try:
        exec_globals = {"input_data": input_data, "__name__": "__main__"}
        exec(code, exec_globals)

        # Get result: check explicit variable, then callable main()
        if "result" in exec_globals:
            result = exec_globals["result"]
        elif "output" in exec_globals:
            result = exec_globals["output"]
        elif callable(exec_globals.get("main")):
            result = exec_globals["main"](input_data)

    except Exception as e:
        success = False
        error = str(e)
        error_type = type(e).__name__
        traceback.print_exc(file=captured_stderr)

    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    _write_output(
        success=success,
        result=result,
        stdout=_truncate(captured_stdout.getvalue(), MAX_STDOUT_BYTES, "stdout"),
        stderr=_truncate(captured_stderr.getvalue(), MAX_STDERR_BYTES, "stderr"),
        error=error,
        error_type=error_type,
    )


def _truncate(text, max_bytes, label):
    """Truncate text to max_bytes, appending a notice if truncated."""
    if len(text) <= max_bytes:
        return text
    return text[:max_bytes] + f"\n\n... [{label} truncated at {max_bytes} bytes]"


def _write_output(
    success=False,
    result=None,
    stdout="",
    stderr="",
    error=None,
    error_type=None,
):
    output = {
        "success": success,
        "result": result,
        "stdout": stdout,
        "stderr": stderr,
        "error": error,
        "error_type": error_type,
    }
    try:
        serialized = json.dumps(output, default=str)

        # If total output exceeds 1MB, replace result with error
        if len(serialized) > MAX_OUTPUT_JSON_BYTES:
            output = {
                "success": False,
                "result": None,
                "stdout": _truncate(stdout, MAX_STDOUT_BYTES, "stdout"),
                "stderr": _truncate(stderr, MAX_STDERR_BYTES, "stderr"),
                "error": f"Output too large ({len(serialized)} bytes, limit {MAX_OUTPUT_JSON_BYTES})",
                "error_type": "OutputSizeError",
            }
            serialized = json.dumps(output, default=str)

        with open(OUTPUT_PATH, "w") as f:
            f.write(serialized)
    except Exception:
        # Last resort: write minimal error to stderr
        sys.stderr.write(f"Failed to write output: {output}\n")


if __name__ == "__main__":
    # Add /sandbox to sys.path for code-mode functions/ package
    if SANDBOX_DIR not in sys.path:
        sys.path.insert(0, SANDBOX_DIR)
    run()

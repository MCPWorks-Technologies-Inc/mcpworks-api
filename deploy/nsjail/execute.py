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


def run():
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
        stdout=captured_stdout.getvalue(),
        stderr=captured_stderr.getvalue(),
        error=error,
        error_type=error_type,
    )


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
        with open(OUTPUT_PATH, "w") as f:
            json.dump(output, f, default=str)
    except Exception:
        # Last resort: write minimal error to stderr
        sys.stderr.write(f"Failed to write output: {output}\n")


if __name__ == "__main__":
    # Add /sandbox to sys.path for code-mode functions/ package
    if SANDBOX_DIR not in sys.path:
        sys.path.insert(0, SANDBOX_DIR)
    run()

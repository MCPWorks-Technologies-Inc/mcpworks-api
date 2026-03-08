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
CALL_LOG_PATH = f"{SANDBOX_DIR}/.call_log"

# Output size limits (defense-in-depth against json-bomb / stdout-flood)
MAX_STDOUT_BYTES = 64 * 1024  # 64 KB per stream
MAX_STDERR_BYTES = 64 * 1024  # 64 KB per stream
MAX_OUTPUT_JSON_BYTES = 1024 * 1024  # 1 MB total output


def _harden_sandbox():
    """Apply pre-exec security restrictions (FINDING-17/18/19/20).

    Called once before user code runs. All restrictions are best-effort:
    nsjail + seccomp are the primary security boundary.
    """
    import signal

    # FINDING-17: Block stack frame traversal.
    _real_getframe = sys._getframe

    def _restricted_getframe(depth=0):
        if depth > 0:
            raise RuntimeError("Access to caller frames is restricted")
        return _real_getframe(0)

    sys._getframe = _restricted_getframe
    if hasattr(sys, "_current_frames"):
        sys._current_frames = lambda: {}

    # FINDING-19: Block signal handler overrides.
    # nsjail's time_limit sends SIGKILL (uncatchable), but user code could
    # override SIGTERM/SIGALRM/SIGINT to resist graceful cleanup.
    _real_signal = signal.signal

    def _blocked_signal(signum, handler):
        allowed = {signal.SIGPIPE}
        if signum in allowed:
            return _real_signal(signum, handler)
        raise RuntimeError(f"Overriding signal {signum} is not permitted")

    signal.signal = _blocked_signal
    signal.alarm = lambda *_a: 0
    if hasattr(signal, "setitimer"):
        signal.setitimer = lambda *_a: (0.0, 0.0)

    # FINDING-18: Block subprocess and os.exec*/os.system/os.popen.
    # Prevents reverse shell creation. nsjail allows execve (Python needs it),
    # but we block the Python-level interfaces to subprocess.
    import os
    import types

    def _blocked(*_a, **_kw):
        raise RuntimeError("Subprocess execution is not permitted in sandbox")

    for attr in (
        "system",
        "popen",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
    ):
        if hasattr(os, attr):
            setattr(os, attr, _blocked)

    # Poison subprocess module — must happen BEFORE freezing sys.modules
    _fake_subprocess = types.ModuleType("subprocess")
    _fake_subprocess.run = _blocked
    _fake_subprocess.Popen = _blocked
    _fake_subprocess.call = _blocked
    _fake_subprocess.check_call = _blocked
    _fake_subprocess.check_output = _blocked
    _fake_subprocess.getoutput = _blocked
    _fake_subprocess.getstatusoutput = _blocked
    sys.modules["subprocess"] = _fake_subprocess

    # FINDING-08: Block /proc/net and /proc/self/mountinfo reads.
    # nsjail can't bind-mount over procfs subdirectories, so we intercept
    # open() to block paths that leak network topology and mount info.
    import builtins

    _real_open = builtins.open
    _blocked_prefixes = ("/proc/net/", "/proc/self/net/", "/proc/1/net/")
    _blocked_paths = (
        "/proc/self/mountinfo",
        "/proc/1/mountinfo",
        "/proc/self/mounts",
        "/proc/1/mounts",
    )

    def _restricted_open(file, *args, **kwargs):
        if isinstance(file, str):
            if any(file.startswith(p) for p in _blocked_prefixes):
                raise PermissionError(f"Access denied: {file}")
            if file in _blocked_paths:
                raise PermissionError(f"Access denied: {file}")
        return _real_open(file, *args, **kwargs)

    builtins.open = _restricted_open

    # FINDING-20: Freeze existing sys.modules entries.
    # New imports still work, but user code cannot replace already-loaded
    # modules (e.g., replacing 'json' to intercept output serialization,
    # or un-poisoning 'subprocess').
    _frozen_keys = frozenset(sys.modules.keys())

    class _FrozenModules(dict):
        def __setitem__(self, key, value):
            if key in _frozen_keys:
                return
            super().__setitem__(key, value)

        def __delitem__(self, key):
            if key in _frozen_keys:
                return
            super().__delitem__(key)

        def pop(self, key, *args):
            if key in _frozen_keys:
                return self.get(key)
            return super().pop(key, *args)

    sys.modules = _FrozenModules(sys.modules)


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

    # Apply all sandbox hardening before exec
    _harden_sandbox()

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

    # FINDING-04: Read call log from file directly (trusted code, not user code).
    # This replaces the appended capture snippet for file-based billing.
    call_log = _read_call_log()

    _write_output(
        success=success,
        result=result,
        stdout=_truncate(captured_stdout.getvalue(), MAX_STDOUT_BYTES, "stdout"),
        stderr=_truncate(captured_stderr.getvalue(), MAX_STDERR_BYTES, "stderr"),
        error=error,
        error_type=error_type,
        call_log=call_log,
    )


def _read_call_log():
    """FINDING-04: Read billing call log from trusted file path.

    This is called by execute.py after user code, not by user code itself.
    User code can still write to the file, but can no longer monkey-patch
    the reader function or replace the module that produces the log.
    """
    try:
        with open(CALL_LOG_PATH) as f:
            return [ln.strip() for ln in f if ln.strip()]
    except Exception:
        return []


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
    call_log=None,
):
    output = {
        "success": success,
        "result": result,
        "stdout": stdout,
        "stderr": stderr,
        "error": error,
        "error_type": error_type,
        "call_log": call_log or [],
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

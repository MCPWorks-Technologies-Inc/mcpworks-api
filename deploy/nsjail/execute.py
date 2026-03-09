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


def _is_blocked_path(path):
    if not isinstance(path, str | bytes):
        return False
    p = path.decode("utf-8", errors="replace") if isinstance(path, bytes) else path
    _prefixes = ("/proc/net/", "/proc/self/net/", "/proc/1/net/")
    _paths = (
        "/proc/self/mountinfo",
        "/proc/1/mountinfo",
        "/proc/self/mounts",
        "/proc/1/mounts",
    )
    if any(p.startswith(pfx) for pfx in _prefixes):
        return True
    return p in _paths


def _harden_sandbox():
    """Apply pre-exec security restrictions (FINDING-17/18/19/20/22).

    Called once before user code runs. All restrictions are defense-in-depth:
    nsjail + seccomp are the primary security boundary.

    FINDING-22 bypass mitigations:
    - ctypes/_ctypes poisoned (eliminates libc.system, dup2, PyFrame_LocalsToFast)
    - os.open/os.read restricted (closes low-level /proc bypass)
    - Closures eliminated where possible (prevents __closure__ extraction)
    - FrozenModules hardened against dict.__setitem__ bypass
    """
    import signal

    # FINDING-17 + F-27: Block stack frame traversal for user code.
    # F-22: class-based callable (no __closure__ to extract).
    # F-26: __getattribute__ blocks direct _f access.
    # F-27: Allow _getframe(depth>0) from stdlib (collections.namedtuple needs
    # _getframe(1) for module detection — blocking it breaks socket, urllib,
    # ssl, pathlib, asyncio, dataclasses, and all networking packages).
    _STDLIB_PREFIXES = ("/usr/local/lib/", "/usr/lib/", "/opt/mcpworks/site-packages/")
    _real_getframe = sys._getframe

    class _RestrictedGetframe:
        __slots__ = ("_f",)

        def __init__(self, f):
            object.__setattr__(self, "_f", f)

        def __call__(self, depth=0):
            _f = object.__getattribute__(self, "_f")
            # +1 to all depths: skip this wrapper's own stack frame
            if depth > 0:
                caller = _f(1)  # actual caller of sys._getframe()
                if caller.f_code.co_filename.startswith(_STDLIB_PREFIXES):
                    return _f(depth + 1)
                raise RuntimeError("Access to caller frames is restricted")
            return _f(1)

        def __getattribute__(self, name):
            if name == "_f":
                raise AttributeError("Access denied")
            return object.__getattribute__(self, name)

    sys._getframe = _RestrictedGetframe(_real_getframe)
    del _real_getframe
    if hasattr(sys, "_current_frames"):
        sys._current_frames = lambda: {}

    # FINDING-19: Block signal handler overrides.
    # F-22: class-based callable (no closure). F-26: __getattribute__ guard.
    _real_signal = signal.signal

    class _RestrictedSignal:
        __slots__ = ("_f", "_allowed")

        def __init__(self, f):
            object.__setattr__(self, "_f", f)
            object.__setattr__(
                self,
                "_allowed",
                frozenset({signal.SIGPIPE, signal.SIGINT}),
            )

        def __call__(self, signum, handler):
            _f = object.__getattribute__(self, "_f")
            allowed = object.__getattribute__(self, "_allowed")
            if signum in allowed:
                return _f(signum, handler)
            raise RuntimeError(f"Overriding signal {signum} is not permitted")

        def __getattribute__(self, name):
            if name in ("_f", "_allowed"):
                raise AttributeError("Access denied")
            return object.__getattribute__(self, name)

    signal.signal = _RestrictedSignal(_real_signal)
    del _real_signal
    signal.alarm = lambda *_a: 0
    if hasattr(signal, "setitimer"):
        signal.setitimer = lambda *_a: (0.0, 0.0)

    # FINDING-18 + F-29: Block subprocess, os.exec*/os.system/os.popen, AND posix module.
    import os
    import posix
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
        "posix_spawn",
        "posix_spawnp",
        "fork",
        "forkpty",
    ):
        if hasattr(os, attr):
            setattr(os, attr, _blocked)

    # F-29: Block posix module — same C functions as os.* but not wrapped by os.
    for attr in (
        "system",
        "popen",
        "execv",
        "execve",
        "fork",
        "forkpty",
        "spawnv",
        "spawnve",
        "posix_spawn",
        "posix_spawnp",
    ):
        if hasattr(posix, attr):
            setattr(posix, attr, _blocked)

    # Poison subprocess module — must happen BEFORE freezing sys.modules
    _fake_subprocess = types.ModuleType("subprocess")

    def _subprocess_not_found(*_a, **_kw):
        raise FileNotFoundError("Subprocess execution is not available in sandbox")

    _fake_subprocess.run = _subprocess_not_found
    _fake_subprocess.Popen = _subprocess_not_found
    _fake_subprocess.call = _subprocess_not_found
    _fake_subprocess.check_call = _subprocess_not_found
    _fake_subprocess.check_output = _subprocess_not_found
    _fake_subprocess.getoutput = _subprocess_not_found
    _fake_subprocess.getstatusoutput = _subprocess_not_found
    _fake_subprocess.PIPE = -1
    _fake_subprocess.STDOUT = -2
    _fake_subprocess.DEVNULL = -3

    class _SubprocessError(Exception):
        pass

    class _CalledProcessError(_SubprocessError):
        def __init__(self, returncode=None, cmd=None, output=None, stderr=None):
            self.returncode = returncode
            self.cmd = cmd
            self.output = output
            self.stderr = stderr

    class _TimeoutExpired(_SubprocessError):
        def __init__(self, cmd=None, timeout=None, output=None, stderr=None):
            self.cmd = cmd
            self.timeout = timeout
            self.output = output
            self.stderr = stderr

    class _CompletedProcess:
        def __init__(self, args=None, returncode=None, stdout=None, stderr=None):
            self.args = args
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    _fake_subprocess.SubprocessError = _SubprocessError
    _fake_subprocess.CalledProcessError = _CalledProcessError
    _fake_subprocess.TimeoutExpired = _TimeoutExpired
    _fake_subprocess.CompletedProcess = _CompletedProcess
    _fake_subprocess._args_from_interpreter_flags = lambda: []
    _fake_subprocess._optim_args_from_interpreter_flags = lambda: []
    sys.modules["subprocess"] = _fake_subprocess

    # F-30: Poison _posixsubprocess — the C extension that subprocess.Popen
    # uses for fork_exec. Even if real subprocess is recovered, it can't spawn.
    _fake_posixsub = types.ModuleType("_posixsubprocess")
    _fake_posixsub.fork_exec = _blocked
    sys.modules["_posixsubprocess"] = _fake_posixsub

    # F-31: Disable gc.get_objects/get_referrers/get_referents — prevents
    # scanning the GC heap to recover real built-in functions.
    import gc

    gc.get_objects = _blocked
    gc.get_referrers = _blocked
    gc.get_referents = _blocked

    # FINDING-22 + F-25: Poison ctypes — eliminates libc.system(), dup2(),
    # PyFrame_LocalsToFast(), and all direct C function calls.
    # F-25: _ctypes .so is also hidden via bind-mount in spawn-sandbox.sh,
    # but we poison importlib.util too as defense-in-depth against recovery
    # via importlib.util.spec_from_file_location().
    import importlib.machinery as _im
    import importlib.util as _iu

    _real_spec_from_file = _iu.spec_from_file_location

    class _RestrictedSpecFromFile:
        __slots__ = ("_f",)

        def __init__(self, f):
            object.__setattr__(self, "_f", f)

        def __call__(self, name, location=None, *args, **kwargs):
            if location and isinstance(location, str) and "_ctypes" in location:
                raise ImportError("Loading _ctypes is not permitted in sandbox")
            return object.__getattribute__(self, "_f")(name, location, *args, **kwargs)

        def __getattribute__(self, name):
            if name == "_f":
                raise AttributeError("Access denied")
            return object.__getattribute__(self, name)

    _iu.spec_from_file_location = _RestrictedSpecFromFile(_real_spec_from_file)
    del _real_spec_from_file

    _real_ext_loader = _im.ExtensionFileLoader
    _BLOCKED_EXTENSIONS = frozenset({"_ctypes", "_ctypes_test"})

    class ExtensionFileLoader(_real_ext_loader):
        def __init__(self, name, path, *_a, **_kw):
            if name in _BLOCKED_EXTENSIONS:
                raise ImportError(f"Loading {name} is not permitted in sandbox")
            super().__init__(name, path, *_a, **_kw)

    _im.ExtensionFileLoader = ExtensionFileLoader

    class _CTypeDummy:
        _type_ = "l"

        def __init__(self, v=0):
            self.value = v

    def _sizeof_stub(obj):
        _sizes = {
            "c": 1,
            "b": 1,
            "B": 1,
            "h": 2,
            "H": 2,
            "i": 4,
            "I": 4,
            "l": 8,
            "L": 8,
            "q": 8,
            "Q": 8,
            "f": 4,
            "d": 8,
            "P": 8,
        }
        t = getattr(obj, "_type_", None)
        if t and t in _sizes:
            return _sizes[t]
        return 8

    _safe_types = {
        "c_bool": type("c_bool", (_CTypeDummy,), {"_type_": "?"}),
        "c_char": type("c_char", (_CTypeDummy,), {"_type_": "c"}),
        "c_wchar": type("c_wchar", (_CTypeDummy,), {"_type_": "u"}),
        "c_byte": type("c_byte", (_CTypeDummy,), {"_type_": "b"}),
        "c_ubyte": type("c_ubyte", (_CTypeDummy,), {"_type_": "B"}),
        "c_short": type("c_short", (_CTypeDummy,), {"_type_": "h"}),
        "c_ushort": type("c_ushort", (_CTypeDummy,), {"_type_": "H"}),
        "c_int": type("c_int", (_CTypeDummy,), {"_type_": "i"}),
        "c_uint": type("c_uint", (_CTypeDummy,), {"_type_": "I"}),
        "c_long": type("c_long", (_CTypeDummy,), {"_type_": "l"}),
        "c_ulong": type("c_ulong", (_CTypeDummy,), {"_type_": "L"}),
        "c_longlong": type("c_longlong", (_CTypeDummy,), {"_type_": "q"}),
        "c_ulonglong": type("c_ulonglong", (_CTypeDummy,), {"_type_": "Q"}),
        "c_int8": type("c_int8", (_CTypeDummy,), {"_type_": "b"}),
        "c_int16": type("c_int16", (_CTypeDummy,), {"_type_": "h"}),
        "c_int32": type("c_int32", (_CTypeDummy,), {"_type_": "i"}),
        "c_int64": type("c_int64", (_CTypeDummy,), {"_type_": "q"}),
        "c_uint8": type("c_uint8", (_CTypeDummy,), {"_type_": "B"}),
        "c_uint16": type("c_uint16", (_CTypeDummy,), {"_type_": "H"}),
        "c_uint32": type("c_uint32", (_CTypeDummy,), {"_type_": "I"}),
        "c_uint64": type("c_uint64", (_CTypeDummy,), {"_type_": "Q"}),
        "c_float": type("c_float", (_CTypeDummy,), {"_type_": "f"}),
        "c_double": type("c_double", (_CTypeDummy,), {"_type_": "d"}),
        "c_longdouble": type("c_longdouble", (_CTypeDummy,), {"_type_": "d"}),
        "c_char_p": type("c_char_p", (_CTypeDummy,), {"_type_": "P"}),
        "c_wchar_p": type("c_wchar_p", (_CTypeDummy,), {"_type_": "P"}),
        "c_void_p": type("c_void_p", (_CTypeDummy,), {"_type_": "P"}),
        "c_size_t": type("c_size_t", (_CTypeDummy,), {"_type_": "L"}),
        "c_ssize_t": type("c_ssize_t", (_CTypeDummy,), {"_type_": "l"}),
        "sizeof": _sizeof_stub,
        "POINTER": lambda tp: type(f"LP_{getattr(tp, '__name__', 'void')}", (), {}),
        "CFUNCTYPE": lambda restype, *argtypes: type(
            "CFuncPtr", (), {"restype": restype, "argtypes": argtypes}
        ),
        "PYFUNCTYPE": lambda restype, *argtypes: type(
            "PyFuncPtr", (), {"restype": restype, "argtypes": argtypes}
        ),
        "Structure": type("Structure", (), {}),
        "Union": type("Union", (), {}),
        "Array": type("Array", (), {}),
        "addressof": lambda _obj: 0,
        "string_at": lambda _addr, _size=-1: b"",
        "py_object": type("py_object", (_CTypeDummy,), {"_type_": "O"}),
        "cast": lambda _obj, _typ: _typ(),
        "pointer": lambda _obj: _CTypeDummy(),
        "byref": lambda _obj, _offset=0: _CTypeDummy(),
    }

    for mod_name in (
        "ctypes",
        "ctypes.util",
        "ctypes.wintypes",
        "ctypes.macholib",
        "_ctypes",
    ):
        _fake_ct = types.ModuleType(mod_name)
        _fake_ct.CDLL = _blocked
        _fake_ct.cdll = _blocked
        _fake_ct.pythonapi = _blocked
        _fake_ct.LibraryLoader = _blocked
        for _attr, _val in _safe_types.items():
            setattr(_fake_ct, _attr, _val)
        if mod_name == "ctypes.util":
            _fake_ct.find_library = lambda _name: None
        sys.modules[mod_name] = _fake_ct

    # FINDING-08 + F-22: Block /proc/net and /proc/self/mountinfo reads.
    # Restrict both builtins.open AND os.open/os.read/io.open to prevent
    # the os.open() bypass discovered in Round 6.
    import builtins

    # F-26: All _Restricted* classes use __getattribute__ to block direct
    # attribute access to _f. Attackers must use object.__getattribute__()
    # which is harder to discover. With _ctypes.so removed from disk (F-25),
    # recovering the real function is harmless (no libc.system or
    # PyFrame_LocalsToFast available).
    _real_open = builtins.open

    class _RestrictedOpen:
        __slots__ = ("_f",)

        def __init__(self, f):
            object.__setattr__(self, "_f", f)

        def __call__(self, file, *args, **kwargs):
            if _is_blocked_path(file):
                raise PermissionError(f"Access denied: {file}")
            return object.__getattribute__(self, "_f")(file, *args, **kwargs)

        def __getattribute__(self, name):
            if name == "_f":
                raise AttributeError("Access denied")
            return object.__getattribute__(self, name)

    builtins.open = _RestrictedOpen(_real_open)
    del _real_open

    _real_os_open = os.open

    class _RestrictedOsOpen:
        __slots__ = ("_f",)

        def __init__(self, f):
            object.__setattr__(self, "_f", f)

        def __call__(self, path, flags, mode=0o777, *args, **kwargs):
            if _is_blocked_path(path):
                raise PermissionError(f"Access denied: {path}")
            return object.__getattribute__(self, "_f")(path, flags, mode, *args, **kwargs)

        def __getattribute__(self, name):
            if name == "_f":
                raise AttributeError("Access denied")
            return object.__getattribute__(self, name)

    os.open = _RestrictedOsOpen(_real_os_open)
    del _real_os_open

    import io

    _real_io_open = io.open

    class _RestrictedIoOpen:
        __slots__ = ("_f",)

        def __init__(self, f):
            object.__setattr__(self, "_f", f)

        def __call__(self, file, *args, **kwargs):
            if _is_blocked_path(file):
                raise PermissionError(f"Access denied: {file}")
            return object.__getattribute__(self, "_f")(file, *args, **kwargs)

        def __getattribute__(self, name):
            if name == "_f":
                raise AttributeError("Access denied")
            return object.__getattribute__(self, name)

    io.open = _RestrictedIoOpen(_real_io_open)
    del _real_io_open

    # FINDING-20 + F-22: Protect poisoned modules from being restored.
    #
    # Previous approach used _FrozenModules (dict subclass replacing sys.modules)
    # but this broke C extension imports (asyncio, _asyncio, etc.) because
    # CPython's interp->modules pointer doesn't update when sys.modules is
    # reassigned from Python code — C extensions use PyImport_GetModuleDict()
    # which reads the stale pointer.
    #
    # New approach: hook builtins.__import__ to block re-import of poisoned
    # modules. The poisoned stubs remain in sys.modules. User code calling
    # `import ctypes` gets the poisoned stub. Direct sys.modules manipulation
    # via dict.__setitem__ is a known C-level bypass that requires ctypes
    # (chicken-and-egg with _ctypes.so removed from disk via bind-mount).
    # F-30: Use __slots__ class to avoid closure leak of _real_import.
    # Previous closure-based _guarded_import leaked via __closure__[1].cell_contents.
    # F-28 note: object.__getattribute__ can still recover _f from __slots__,
    # but _posixsubprocess is poisoned and posix.system is blocked, so
    # recovering __import__ alone doesn't enable shell access.
    _POISONED_MODULES = frozenset(
        {
            "ctypes",
            "ctypes.util",
            "ctypes.wintypes",
            "ctypes.macholib",
            "_ctypes",
            "_ctypes_test",
            "_posixsubprocess",
        }
    )

    class _GuardedImport:
        __slots__ = ("_f",)

        def __init__(self, f):
            object.__setattr__(self, "_f", f)

        def __call__(self, name, *args, **kwargs):
            if name in _POISONED_MODULES:
                existing = sys.modules.get(name)
                if existing is not None:
                    return existing
                raise ImportError(f"Module {name} is not available in sandbox")
            return object.__getattribute__(self, "_f")(name, *args, **kwargs)

        def __getattribute__(self, name):
            if name == "_f":
                raise AttributeError("Access denied")
            return object.__getattribute__(self, name)

    builtins.__import__ = _GuardedImport(builtins.__import__)


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

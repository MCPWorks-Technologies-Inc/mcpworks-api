"""Environment variable passthrough for sandbox execution.

Extracts user-provided env vars from the X-MCPWorks-Env HTTP header,
validates them, filters by function declarations, and returns a
sanitized dict for injection into the nsjail sandbox.

Security properties:
- Env vars are NEVER logged (structlog processor strips the field)
- Env vars are NEVER persisted to disk outside the tmpfs workspace
- Env vars are NEVER stored in the database
- Blocklisted names prevent override of sandbox-critical variables
"""

import base64
import json
import re
from typing import Any

from starlette.requests import Request

HEADER_NAME = "X-MCPWorks-Env"

MAX_DECODED_BYTES = 32 * 1024
MAX_KEY_COUNT = 64
MAX_VALUE_BYTES = 8 * 1024
KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")

BLOCKED_PREFIXES = (
    "LD_",
    "PYTHON",
    "NSJAIL",
    "SSL_",
    "MCPWORKS_INTERNAL_",
)

BLOCKED_EXACT = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "SHELL",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "TMP",
        "TEMP",
        "DISPLAY",
        "DBUS_SESSION_BUS_ADDRESS",
        "XDG_RUNTIME_DIR",
        "HOSTNAME",
        "IFS",
    }
)

RESERVED_PREFIX = "MCPWORKS_"


class EnvPassthroughError(ValueError):
    """Raised when env var header is malformed or violates policy."""


def extract_env_vars(request: Request) -> dict[str, str]:
    """Extract and validate env vars from the request header.

    Returns an empty dict if the header is absent.
    Raises EnvPassthroughError if the header is present but invalid.
    """
    raw = request.headers.get(HEADER_NAME)
    if not raw:
        return {}

    if raw.startswith("base64:"):
        raw = raw[7:]

    try:
        decoded = base64.b64decode(raw, validate=True)
    except Exception:
        raise EnvPassthroughError(f"{HEADER_NAME} header is not valid base64")

    if len(decoded) > MAX_DECODED_BYTES:
        raise EnvPassthroughError(
            f"Env payload too large ({len(decoded)} bytes, max {MAX_DECODED_BYTES})"
        )

    try:
        env = json.loads(decoded)
    except json.JSONDecodeError:
        raise EnvPassthroughError(f"{HEADER_NAME} decoded content is not valid JSON")

    if not isinstance(env, dict):
        raise EnvPassthroughError(f"{HEADER_NAME} must be a JSON object, got {type(env).__name__}")

    if len(env) > MAX_KEY_COUNT:
        raise EnvPassthroughError(f"Too many env vars ({len(env)}, max {MAX_KEY_COUNT})")

    sanitized: dict[str, str] = {}
    for key, value in env.items():
        _validate_key(key)
        _validate_value(key, value)
        sanitized[key] = str(value)

    return sanitized


def filter_env_for_function(
    env_vars: dict[str, str],
    required_env: list[str] | None,
    optional_env: list[str] | None,
) -> dict[str, str]:
    """Filter env vars to only those declared by the function.

    Returns the intersection of provided vars and declared vars.
    Functions with no declarations get no user env vars.
    """
    if not env_vars:
        return {}

    declared = set()
    if required_env:
        declared.update(required_env)
    if optional_env:
        declared.update(optional_env)

    if not declared:
        return {}

    return {k: v for k, v in env_vars.items() if k in declared}


def check_required_env(
    env_vars: dict[str, str],
    required_env: list[str] | None,
) -> list[str]:
    """Check that all required env vars are present.

    Returns list of missing required var names (empty = all present).
    """
    if not required_env:
        return []

    return [name for name in required_env if name not in env_vars]


def _validate_key(key: str) -> None:
    if not isinstance(key, str):
        raise EnvPassthroughError(f"Env var key must be a string, got {type(key).__name__}")

    if not KEY_PATTERN.match(key):
        raise EnvPassthroughError(
            f"Invalid env var name: '{key}'. Must match ^[A-Z][A-Z0-9_]{{{{0,127}}}}$"
        )

    if key in BLOCKED_EXACT:
        raise EnvPassthroughError(f"Env var name '{key}' is blocked (system variable)")

    for prefix in BLOCKED_PREFIXES:
        if key.startswith(prefix):
            raise EnvPassthroughError(
                f"Env var name '{key}' is blocked (prefix '{prefix}' is reserved)"
            )

    if key.startswith(RESERVED_PREFIX):
        raise EnvPassthroughError(
            f"Env var name '{key}' is blocked (prefix '{RESERVED_PREFIX}' is reserved for platform use)"
        )


def _validate_value(key: str, value: Any) -> None:
    if not isinstance(value, str):
        raise EnvPassthroughError(
            f"Env var '{key}' value must be a string, got {type(value).__name__}"
        )

    if len(value.encode("utf-8")) > MAX_VALUE_BYTES:
        raise EnvPassthroughError(
            f"Env var '{key}' value too large ({len(value.encode('utf-8'))} bytes, max {MAX_VALUE_BYTES})"
        )

    if "\x00" in value:
        raise EnvPassthroughError(f"Env var '{key}' contains null byte")

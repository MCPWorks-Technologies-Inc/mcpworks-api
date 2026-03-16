"""Code-mode package generator for the run endpoint.

Generates a ``functions/`` Python package from database function records.
The agent imports and calls these wrappers inside the sandbox subprocess,
achieving on-demand tool discovery without loading all definitions into context.

See: https://www.anthropic.com/engineering/code-execution-with-mcp
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcpworks_api.models import Function, FunctionVersion


def _sanitize(name: str) -> str:
    """Convert a name to a valid Python identifier (hyphens → underscores)."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower())


_NO_DEFAULT = object()  # module-level sentinel for comparison


def _params_from_schema(schema: dict[str, Any] | None) -> list[tuple[str, Any, str]]:
    """Extract (param_name, default_or_sentinel, description) from JSON Schema.

    Returns a list of ``(name, default, desc)`` tuples.  ``default`` is the
    sentinel ``_NO_DEFAULT`` when the property has no default value.
    """
    if not schema or "properties" not in schema:
        return []
    required = set(schema.get("required", []))
    required_params: list[tuple[str, Any, str]] = []
    optional_params: list[tuple[str, Any, str]] = []
    for key, prop in schema["properties"].items():
        default = prop.get("default", _NO_DEFAULT)
        desc = prop.get("description", "")
        if key in required and default is _NO_DEFAULT:
            required_params.append((_sanitize(key), _NO_DEFAULT, desc))
        else:
            if default is _NO_DEFAULT:
                default = None
            optional_params.append((_sanitize(key), default, desc))
    return required_params + optional_params


def _generate_wrapper(
    func: Function,
    version: FunctionVersion,
    service_name: str,
) -> str:
    """Generate Python source for a single function wrapper."""
    safe_name = _sanitize(func.name)
    qualified = f"{service_name}.{func.name}"
    desc = func.description or f"Execute {qualified}"

    # TypeScript functions can't be exec'd as Python — generate a stub
    if getattr(version, "language", "python") == "typescript":
        return f'''def {safe_name}(**kwargs):
    """{desc} [TypeScript — use execute_typescript tool instead]"""
    raise RuntimeError(
        "{qualified} is a TypeScript function and cannot be called from Python code-mode. "
        "Use the execute_typescript tool instead."
    )
'''

    code_file = f"_code/{_sanitize(service_name)}__{safe_name}.py"

    params = _params_from_schema(version.input_schema)
    # Build signature
    sig_parts: list[str] = []
    for pname, default, _desc in params:
        if default is _NO_DEFAULT:
            sig_parts.append(pname)
        else:
            sig_parts.append(f"{pname}={default!r}")
    if not sig_parts:
        sig_parts.append("**kwargs")

    sig = ", ".join(sig_parts)

    # Build input_data dict from args
    if params:
        dict_entries = ", ".join(f'"{p[0]}": {p[0]}' for p in params)
        input_line = f"    input_data = {{{dict_entries}}}"
    else:
        input_line = "    input_data = dict(kwargs)"

    return f'''def {safe_name}({sig}):
    """{desc}"""
    from functions._registry import _track_call
    _track_call("{qualified}")
{input_line}
    import pathlib as _pl
    _code_path = _pl.Path(__file__).parent / "{code_file}"
    _g = {{"input_data": input_data, "__name__": "__exec__"}}
    exec(_code_path.read_text(), _g)
    if "result" in _g:
        return _g["result"]
    if "output" in _g:
        return _g["output"]
    if callable(_g.get("main")):
        return _g["main"](input_data)
    return None
'''


def _generate_service_module(
    service_name: str,
    funcs: list[tuple[Function, FunctionVersion]],
) -> str:
    """Generate a service module with all function wrappers."""
    lines = [f'"""Functions in the {service_name} service."""\n']
    for func, version in funcs:
        lines.append(_generate_wrapper(func, version, service_name))
    return "\n".join(lines)


def _generate_init(
    namespace: str,
    services: dict[str, list[tuple[Function, FunctionVersion]]],
) -> str:
    """Generate functions/__init__.py with catalog docstring and re-exports."""
    doc_lines = [f"Available functions in the '{namespace}' namespace:", ""]
    imports: list[str] = []

    for svc_name, funcs in sorted(services.items()):
        safe_svc = _sanitize(svc_name)
        doc_lines.append(f"  [{svc_name}]")
        for func, version in funcs:
            safe_name = _sanitize(func.name)
            params = _params_from_schema(version.input_schema)
            if params:
                sig = ", ".join(
                    f"{p[0]}={p[1]!r}" if p[1] is not _NO_DEFAULT else p[0] for p in params
                )
            else:
                sig = "**kwargs"
            desc = func.description or ""
            doc_lines.append(f"    {safe_name}({sig}) — {desc}")
            imports.append(f"from functions.{safe_svc} import {safe_name}")
        doc_lines.append("")

    docstring = "\n".join(doc_lines)
    import_block = "\n".join(imports)

    return f'"""\n{docstring}\n"""\n\n{import_block}\n'


_REGISTRY_SOURCE = '''\
"""Internal call tracking for billing metadata."""
import os as _os

_CALL_LOG_PATH = "/sandbox/.call_log"
_call_log: list[str] = []


def _track_call(function_name: str) -> None:
    _call_log.append(function_name)
    try:
        with open(_CALL_LOG_PATH, "a") as _f:
            _f.write(function_name + "\\n")
    except Exception:
        pass


def _get_call_log() -> list[str]:
    try:
        with open(_CALL_LOG_PATH) as _f:
            return [ln.strip() for ln in _f if ln.strip()]
    except Exception:
        return list(_call_log)
'''


def generate_functions_package(
    functions: list[tuple[Function, FunctionVersion]],
    namespace: str,
) -> dict[str, str]:
    """Generate a ``functions/`` Python package from database records.

    Args:
        functions: ``(Function, FunctionVersion)`` tuples from DB.
        namespace: Namespace name (for the docstring).

    Returns:
        Mapping of relative file paths → file content strings.
        Write these into the sandbox ``exec_dir`` before running code.
    """
    files: dict[str, str] = {}

    # Group by service
    services: dict[str, list[tuple[Function, FunctionVersion]]] = {}
    for func, version in functions:
        svc_name = func.service.name
        services.setdefault(svc_name, []).append((func, version))

    # _registry.py
    files["functions/_registry.py"] = _REGISTRY_SOURCE

    # Per-service modules + raw code files
    for svc_name, funcs in services.items():
        safe_svc = _sanitize(svc_name)
        files[f"functions/{safe_svc}.py"] = _generate_service_module(svc_name, funcs)

        for func, version in funcs:
            if getattr(version, "language", "python") == "typescript":
                continue
            safe_name = _sanitize(func.name)
            code = version.code or ""
            files[f"functions/_code/{safe_svc}__{safe_name}.py"] = code

    # __init__.py (must come after services are built)
    files["functions/__init__.py"] = _generate_init(namespace, services)

    return files

"""TypeScript code-mode package generator for the run endpoint.

Generates a ``functions/`` Node.js package from database function records.
The agent imports and calls these wrappers inside the Node.js sandbox,
mirroring the Python code_mode.py approach.

TypeScript functions are called directly (their code is executed as-is).
Python functions are wrapped with HTTP-style call stubs that invoke
the Python sandbox internally (via the call log / billing path).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcpworks_api.models import Function, FunctionVersion


def _sanitize(name: str) -> str:
    """Convert a name to a valid JS identifier (hyphens → underscores)."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower())


def _generate_ts_wrapper(
    func: Function,
    version: FunctionVersion,
    service_name: str,
) -> str:
    """Generate JS source for a TypeScript function wrapper.

    For TypeScript functions: require the raw code file directly.
    For Python functions: generate a stub that logs the call but
    returns an error explaining the function is Python-only.
    """
    safe_name = _sanitize(func.name)
    qualified = f"{service_name}.{func.name}"
    desc = func.description or f"Execute {qualified}"

    if version.language == "typescript":
        code_file = f"./_code/{_sanitize(service_name)}__{safe_name}.js"
        return f"""/** {desc} */
function {safe_name}(input) {{
  const _trackCall = require("./_registry")._trackCall;
  _trackCall("{qualified}");
  const mod = require("{code_file}");
  const fn = mod.default || mod.main || mod.handler;
  if (typeof fn === "function") {{
    return fn(input, {{}});
  }}
  if (mod.result !== undefined) return mod.result;
  if (mod.output !== undefined) return mod.output;
  return null;
}}
module.exports.{safe_name} = {safe_name};
"""
    else:
        return f"""/** {desc} (Python function — not callable from TypeScript code-mode) */
function {safe_name}() {{
  throw new Error(
    "{qualified} is a Python function and cannot be called from TypeScript code-mode. " +
    "Use the Python execute tool instead, or rewrite the function in TypeScript."
  );
}}
module.exports.{safe_name} = {safe_name};
"""


def _generate_ts_service_module(
    service_name: str,
    funcs: list[tuple[Function, FunctionVersion]],
) -> str:
    """Generate a service module with all function wrappers."""
    lines = [f'// Functions in the {service_name} service\n"use strict";\n']
    for func, version in funcs:
        lines.append(_generate_ts_wrapper(func, version, service_name))
    return "\n".join(lines)


def _generate_ts_init(
    namespace: str,
    services: dict[str, list[tuple[Function, FunctionVersion]]],
) -> str:
    """Generate functions/index.js with re-exports and catalog."""
    doc_lines = [f"Available functions in the '{namespace}' namespace:"]
    exports: list[str] = []

    for svc_name, funcs in sorted(services.items()):
        safe_svc = _sanitize(svc_name)
        doc_lines.append(f"\n  [{svc_name}]")
        for func, version in funcs:
            safe_name = _sanitize(func.name)
            lang_tag = f" [{version.language}]"
            desc = func.description or ""
            doc_lines.append(f"    {safe_name}(input){lang_tag} — {desc}")
            exports.append(
                f'const {{ {safe_name} }} = require("./{safe_svc}");\n'
                f"module.exports.{safe_name} = {safe_name};"
            )

    catalog = "\\n".join(doc_lines)

    return f""""use strict";
/**
 * {catalog}
 */

{chr(10).join(exports)}
"""


_REGISTRY_SOURCE_JS = """\
"use strict";
const fs = require("fs");
const CALL_LOG_PATH = "/sandbox/.call_log";
const callLog = [];

function _trackCall(functionName) {
  callLog.push(functionName);
  try {
    fs.appendFileSync(CALL_LOG_PATH, functionName + "\\n");
  } catch {}
}

function _getCallLog() {
  try {
    return fs.readFileSync(CALL_LOG_PATH, "utf-8")
      .split("\\n").filter(Boolean);
  } catch {
    return [...callLog];
  }
}

module.exports._trackCall = _trackCall;
module.exports._getCallLog = _getCallLog;
"""


def generate_ts_functions_package(
    functions: list[tuple[Function, FunctionVersion]],
    namespace: str,
) -> dict[str, str]:
    """Generate a ``functions/`` Node.js package from database records.

    Args:
        functions: ``(Function, FunctionVersion)`` tuples from DB.
        namespace: Namespace name (for the docstring).

    Returns:
        Mapping of relative file paths to file content strings.
    """
    files: dict[str, str] = {}

    services: dict[str, list[tuple[Function, FunctionVersion]]] = {}
    for func, version in functions:
        svc_name = func.service.name
        services.setdefault(svc_name, []).append((func, version))

    files["functions/_registry.js"] = _REGISTRY_SOURCE_JS

    for svc_name, funcs in services.items():
        safe_svc = _sanitize(svc_name)
        files[f"functions/{safe_svc}.js"] = _generate_ts_service_module(svc_name, funcs)

        for func, version in funcs:
            safe_name = _sanitize(func.name)
            code = version.code or ""
            files[f"functions/_code/{safe_svc}__{safe_name}.js"] = code

    files["functions/index.js"] = _generate_ts_init(namespace, services)

    return files

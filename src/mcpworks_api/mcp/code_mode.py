"""Code-mode package generator for the run endpoint.

Generates a ``functions/`` Python package from database function records.
The agent imports and calls these wrappers inside the sandbox subprocess,
achieving on-demand tool discovery without loading all definitions into context.

See: https://www.anthropic.com/engineering/code-execution-with-mcp
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from mcpworks_api import url_builder

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

    # TypeScript functions: call via HTTP to the run server (cross-language bridge)
    if getattr(version, "language", "python") == "typescript":
        params = _params_from_schema(version.input_schema)
        sig_parts_ts: list[str] = []
        for pname, default, _desc in params:
            if default is _NO_DEFAULT:
                sig_parts_ts.append(pname)
            else:
                sig_parts_ts.append(f"{pname}={default!r}")
        if not sig_parts_ts:
            sig_parts_ts.append("**kwargs")
        sig_ts = ", ".join(sig_parts_ts)

        if params:
            dict_entries_ts = ", ".join(f'"{p[0]}": {p[0]}' for p in params)
            input_line_ts = f"    _input = {{{dict_entries_ts}}}"
        else:
            input_line_ts = "    _input = dict(kwargs)"

        return f'''def {safe_name}({sig_ts}):
    """{desc} [TypeScript — called via cross-language bridge]"""
    from functions._registry import _track_call
    _track_call("{qualified}")
{input_line_ts}
    from functions._ts_bridge import _call_ts_function
    return _call_ts_function("{qualified}", _input)
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
    import pathlib as _pl, json as _json
    _code_path = _pl.Path(__file__).parent / "{code_file}"
    _ctx = {{}}
    _ctx_path = _pl.Path("/sandbox/context.json")
    if _ctx_path.exists():
        try:
            _ctx = _json.loads(_ctx_path.read_text())
        except Exception:
            pass
    _g = {{"input_data": input_data, "__name__": "__exec__"}}
    exec(_code_path.read_text(), _g)
    if "result" in _g:
        return _g["result"]
    if "output" in _g:
        return _g["output"]
    if callable(_g.get("handler")):
        return _g["handler"](input_data, _ctx)
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


_TS_BRIDGE_TEMPLATE = '''\
"""Cross-language bridge: call TypeScript functions from Python code-mode.

Uses httpx to call the function via the run server MCP endpoint.
Requires network access (Builder tier or above).
"""
import json
import os

_RUN_URL = "{run_url}"
_API_KEY = os.environ.get("__MCPWORKS_BRIDGE_KEY__", "")


def _call_ts_function(qualified_name: str, input_data: dict) -> object:
    """Call a TypeScript function via the run server."""
    if not _API_KEY:
        raise RuntimeError(
            f"Cannot call TypeScript function {{qualified_name}}: "
            "cross-language bridge key not configured. "
            "Use the execute_typescript tool directly instead."
        )
    import httpx

    response = httpx.post(
        _RUN_URL,
        headers={{
            "Authorization": f"Bearer {{_API_KEY}}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }},
        json={{
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {{
                "name": qualified_name,
                "arguments": input_data,
            }},
        }},
        timeout=60,
    )
    # Parse SSE response
    for line in response.text.split("\\n"):
        if line.startswith("data: "):
            data = json.loads(line[6:])
            result = data.get("result", {{}})
            content = result.get("content", [])
            is_error = result.get("isError", False)
            if content:
                text = content[0].get("text", "{{}}")
                parsed = json.loads(text)
                if is_error:
                    raise RuntimeError(
                        f"TypeScript function {{qualified_name}} failed: "
                        f"{{parsed.get('error', text)}}"
                    )
                return parsed
    raise RuntimeError(f"No response from TypeScript function {{qualified_name}}")
'''


_MCP_BRIDGE_TEMPLATE = '''\
"""MCP proxy bridge: call remote MCP server tools from sandbox code."""
import json
import os

_PROXY_URL = "{proxy_url}"
_BRIDGE_KEY = os.environ.get("__MCPWORKS_BRIDGE_KEY__", "")


def _call_mcp_tool(server: str, tool: str, arguments: dict) -> object:
    if not _BRIDGE_KEY:
        raise RuntimeError(
            f"Cannot call MCP tool {{server}}.{{tool}}: "
            "bridge key not configured."
        )
    import httpx

    response = httpx.post(
        _PROXY_URL,
        headers={{"Authorization": f"Bearer {{_BRIDGE_KEY}}"}},
        json={{"server": server, "tool": tool, "arguments": arguments}},
        timeout=60,
    )
    data = response.json()
    if "error" in data and data["error"]:
        raise RuntimeError(f"MCP tool {{server}}.{{tool}} failed: {{data['error']}}")
    return data.get("result")
'''


def _generate_mcp_wrapper(server_name: str, tool: dict[str, Any]) -> str:
    safe_server = _sanitize(server_name)
    safe_tool = _sanitize(tool["name"])
    qualified = f"mcp__{safe_server}__{safe_tool}"
    desc = tool.get("description", f"MCP tool: {server_name}.{tool['name']}")

    params = _params_from_schema(tool.get("input_schema"))
    if params:
        sig_parts = []
        for pname, default, _desc in params:
            if default is _NO_DEFAULT:
                sig_parts.append(pname)
            else:
                sig_parts.append(f"{pname}={default!r}")
        sig = ", ".join(sig_parts)
        dict_entries = ", ".join(f'"{p[0]}": {p[0]}' for p in params)
        input_line = f"    _args = {{{dict_entries}}}"
    else:
        sig = "**kwargs"
        input_line = "    _args = dict(kwargs)"

    return f'''def {qualified}({sig}):
    """{desc}"""
    from functions._registry import _track_call
    _track_call("mcp:{server_name}.{tool["name"]}")
{input_line}
    from functions._mcp_bridge import _call_mcp_tool
    return _call_mcp_tool("{server_name}", "{tool["name"]}", _args)
'''


def _generate_mcp_server_module(server_name: str, tools: list[dict[str, Any]]) -> str:
    lines = [f'"""Remote MCP tools from the {server_name} server."""\n']
    for tool in tools:
        lines.append(_generate_mcp_wrapper(server_name, tool))
    return "\n".join(lines)


def _generate_init_with_mcp(
    namespace: str,
    services: dict[str, list[tuple[Function, FunctionVersion]]],
    mcp_servers: list[dict[str, Any]] | None = None,
) -> str:
    doc_lines = [f"Available functions in the '{namespace}' namespace:", ""]
    imports: list[str] = []

    if services:
        doc_lines.append("  [Services]")
        for svc_name, funcs in sorted(services.items()):
            safe_svc = _sanitize(svc_name)
            doc_lines.append(f"    [{svc_name}]")
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
                doc_lines.append(f"      {safe_name}({sig}) — {desc}")
                imports.append(f"from functions.{safe_svc} import {safe_name}")
            doc_lines.append("")

    if mcp_servers:
        doc_lines.append("  [RemoteMCP]")
        for server in mcp_servers:
            safe_server = _sanitize(server["name"])
            doc_lines.append(f"    [{server['name']}]")
            for tool in server.get("tool_schemas", []):
                safe_tool = _sanitize(tool["name"])
                qualified = f"mcp__{safe_server}__{safe_tool}"
                params = _params_from_schema(tool.get("input_schema"))
                if params:
                    sig = ", ".join(
                        f"{p[0]}={p[1]!r}" if p[1] is not _NO_DEFAULT else p[0] for p in params
                    )
                else:
                    sig = "**kwargs"
                desc = tool.get("description", "")
                doc_lines.append(f"      {qualified}({sig}) — {desc}")
                imports.append(f"from functions._mcp.{safe_server} import {qualified}")
            doc_lines.append("")

    docstring = "\n".join(doc_lines)
    import_block = "\n".join(imports)
    return f'"""\n{docstring}\n"""\n\n{import_block}\n'


def generate_functions_package(
    functions: list[tuple[Function, FunctionVersion]],
    namespace: str,
    run_url: str | None = None,
    mcp_servers: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Generate a ``functions/`` Python package from database records.

    Args:
        functions: ``(Function, FunctionVersion)`` tuples from DB.
        namespace: Namespace name (for the docstring).
        run_url: MCP run server URL for cross-language bridge.
        mcp_servers: List of {"name": str, "tool_schemas": [...]} from namespace MCP servers.

    Returns:
        Mapping of relative file paths → file content strings.
        Write these into the sandbox ``exec_dir`` before running code.
    """
    files: dict[str, str] = {}

    services: dict[str, list[tuple[Function, FunctionVersion]]] = {}
    has_ts = False
    for func, version in functions:
        svc_name = func.service.name
        services.setdefault(svc_name, []).append((func, version))
        if getattr(version, "language", "python") == "typescript":
            has_ts = True

    files["functions/_registry.py"] = _REGISTRY_SOURCE

    if has_ts:
        bridge_url = run_url or url_builder.mcp_url(namespace, "run")
        files["functions/_ts_bridge.py"] = _TS_BRIDGE_TEMPLATE.format(run_url=bridge_url)

    for svc_name, funcs in services.items():
        safe_svc = _sanitize(svc_name)
        files[f"functions/{safe_svc}.py"] = _generate_service_module(svc_name, funcs)

        for func, version in funcs:
            if getattr(version, "language", "python") == "typescript":
                continue
            safe_name = _sanitize(func.name)
            code = version.code or ""
            files[f"functions/_code/{safe_svc}__{safe_name}.py"] = code

    if mcp_servers:
        from mcpworks_api.config import get_settings

        settings = get_settings()
        base = getattr(settings, "base_scheme", "https") + "://"
        base += "api." + getattr(settings, "base_domain", "localhost")
        proxy_url = f"{base}/v1/internal/mcp-proxy"
        files["functions/_mcp_bridge.py"] = _MCP_BRIDGE_TEMPLATE.format(proxy_url=proxy_url)
        files["functions/_mcp/__init__.py"] = ""
        for server in mcp_servers:
            safe_server = _sanitize(server["name"])
            files[f"functions/_mcp/{safe_server}.py"] = _generate_mcp_server_module(
                server["name"], server.get("tool_schemas", [])
            )

    files["functions/__init__.py"] = _generate_init_with_mcp(namespace, services, mcp_servers)

    return files

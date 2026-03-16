"""Run MCP Handler - Execution interface for namespace functions.

Generates dynamic tools from database and dispatches to backends.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.backends import get_backend
from mcpworks_api.backends.sandbox import TIER_CONFIG, resolve_execution_tier
from mcpworks_api.core.exceptions import NotFoundError
from mcpworks_api.mcp.env_passthrough import check_required_env, filter_env_for_function
from mcpworks_api.mcp.protocol import (
    JSONRPCRequest,
    JSONRPCResponse,
    MCPContent,
    MCPErrorCodes,
    MCPTool,
    MCPToolCallParams,
    MCPToolResult,
    MCPToolsListResult,
    make_error_response,
    make_success_response,
)
from mcpworks_api.models import Account, APIKey, Namespace
from mcpworks_api.services.function import FunctionService
from mcpworks_api.services.namespace import NamespaceServiceManager

logger = structlog.get_logger(__name__)


class RunMCPHandler:
    """Handler for *.run.mcpworks.io endpoints.

    Provides function execution by:
    1. Dynamically generating tools from database functions
    2. Dispatching execution to appropriate backend
    3. Recording execution metrics
    """

    TOOL_SCOPES: dict[str, str] = {
        "_env_status": "read",
    }

    def __init__(
        self,
        namespace: str,
        account: Account,
        db: AsyncSession,
        api_key: APIKey,
        mode: str = "code",
    ):
        self.namespace_name = namespace
        self.account = account
        self.db = db
        self.mode = mode
        self.api_key = api_key
        self.namespace_service = NamespaceServiceManager(db)
        self.function_service = FunctionService(db)
        self._namespace: Namespace | None = None

    def _get_tier_config(self) -> dict:
        """Get sandbox tier config for the current user's effective tier."""
        tier_str = self.account.user.effective_tier
        tier = resolve_execution_tier(tier_str)
        return TIER_CONFIG[tier]

    def _tier_notice(self) -> str:
        """Build a terse sandbox constraint notice for tool descriptions."""
        tier_str = self.account.user.effective_tier
        cfg = self._get_tier_config()
        parts = [
            f"\n\nSandbox limits ({tier_str} tier): timeout={cfg['timeout_sec']}s, memory={cfg['memory_mb']}MB."
        ]
        if not cfg["network"]:
            parts.append(
                "Network: BLOCKED. All outbound connections (requests, httpx, urllib, sockets) will fail. Upgrade to Builder tier for network access."
            )
        else:
            parts.append("Network: available.")
        return " ".join(parts)

    async def _get_namespace(self) -> Namespace:
        """Get and cache the current namespace (with execute share access)."""
        if self._namespace is None:
            self._namespace = await self.namespace_service.get_by_name(
                self.namespace_name,
                self.account.id,
                user_id=self.account.user_id,
                required_permission="execute",
            )
        return self._namespace

    async def _get_namespace_for_read(self) -> Namespace:
        """Get namespace with read share access (for tools/list)."""
        return await self.namespace_service.get_by_name(
            self.namespace_name,
            self.account.id,
            user_id=self.account.user_id,
            required_permission="read",
        )

    async def handle(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """Handle MCP request."""
        method = request.method
        params = request.params or {}

        if method == "initialize":
            return await self._handle_initialize(request.id)
        elif method == "tools/list":
            return await self._handle_tools_list(request.id)
        elif method == "tools/call":
            return await self._handle_tools_call(params, request.id)
        else:
            return make_error_response(
                MCPErrorCodes.METHOD_NOT_FOUND,
                f"Unknown method: {method}",
                request_id=request.id,
            )

    async def _handle_initialize(self, request_id) -> JSONRPCResponse:
        """Handle initialize method."""
        return make_success_response(
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": f"mcpworks-run-{self.namespace_name}",
                    "version": "1.0.0",
                },
            },
            request_id,
        )

    async def get_tools(self) -> list[MCPTool]:
        """Generate tools list from database functions."""
        if self.mode == "code":
            return self._get_code_mode_tools()

        tier_notice = self._tier_notice()
        namespace = await self._get_namespace_for_read()
        functions = await self.function_service.list_all_for_namespace(namespace_id=namespace.id)

        tools = []
        for func, version in functions:
            tool_name = f"{func.service.name}.{func.name}"
            desc = func.description or f"Execute {tool_name}"

            if version.required_env:
                desc += f"\n\nRequired env: {', '.join(version.required_env)}"
            if version.optional_env:
                desc += f"\nOptional env: {', '.join(version.optional_env)}"

            desc += tier_notice

            tools.append(
                MCPTool(
                    name=tool_name,
                    description=desc,
                    inputSchema=version.input_schema or {"type": "object", "properties": {}},
                )
            )

        tools.append(
            MCPTool(
                name="_env_status",
                description="Check which environment variables are configured and which are missing for this namespace's functions",
                inputSchema={"type": "object", "properties": {}},
            )
        )

        return tools

    def _get_code_mode_tools(self) -> list[MCPTool]:
        """Return execute tools for code-mode (Python + TypeScript)."""
        tier_notice = self._tier_notice()
        return [
            MCPTool(
                name="execute_python",
                description=(
                    "Execute Python code in a secure sandbox with access to all namespace functions.\n"
                    "\n"
                    "RETURNING DATA: Set `result = ...` to return data to the conversation. "
                    "Without this, the result will be null.\n"
                    "\n"
                    "CALLING FUNCTIONS: Import from the `functions` package:\n"
                    "  from functions import hello; result = hello(name='World')\n"
                    "\n"
                    "DISCOVERING FUNCTIONS: import functions; print(functions.__doc__)\n"
                    "\n"
                    "FUNCTION ARGUMENTS: Pass arguments as keyword args matching the function's input_schema. "
                    "Only parameters defined in the function's input_schema will be passed through.\n"
                    + tier_notice
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": (
                                "Python code to execute. "
                                "Set `result = ...` to return data. "
                                "Import functions via `from functions import func_name`. "
                                "Example: from functions import hello; result = hello(name='World')"
                            ),
                        }
                    },
                    "required": ["code"],
                },
            ),
            MCPTool(
                name="execute_typescript",
                description=(
                    "Execute TypeScript/JavaScript code in a secure Node.js sandbox with access to all namespace functions.\n"
                    "\n"
                    "RETURNING DATA: Set `module.exports.result = ...` or `export default ...` to return data.\n"
                    "\n"
                    "CALLING FUNCTIONS: Require from the `functions` package:\n"
                    '  const { hello } = require("./functions");\n'
                    "  module.exports.result = hello({ name: 'World' });\n"
                    "\n"
                    "ASYNC: Async functions are supported — return a Promise and it will be awaited.\n"
                    "\n"
                    "NOTE: Only TypeScript-language functions can be called from this tool. "
                    "Python functions will throw an error explaining they must be called from the Python execute tool.\n"
                    + tier_notice
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": (
                                "TypeScript or JavaScript code to execute in Node.js. "
                                "Set `module.exports.result = ...` to return data. "
                                'Require functions via `const { fn } = require("./functions")`. '
                                "Example: const { fibonacci } = require('./functions'); "
                                "module.exports.result = fibonacci({ n: 10 });"
                            ),
                        }
                    },
                    "required": ["code"],
                },
            ),
        ]

    def _check_scope(self, tool_name: str) -> None:
        """Check that the API key has the required scope for a tool.

        For run handler, dynamic tools (service.function and execute) require
        ``execute`` scope. Static tools use ``TOOL_SCOPES`` mapping.
        """
        required = self.TOOL_SCOPES.get(tool_name, "execute")
        if not self.api_key.has_scope(required):
            raise ValueError(f"API key missing required scope '{required}' for tool '{tool_name}'")

    async def dispatch_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        sandbox_env: dict[str, str] | None = None,
    ) -> MCPToolResult:
        """Execute a function via its backend without JSON-RPC wrapping.

        Args:
            name: Tool name — ``service.function`` for tools mode,
                or ``"execute"`` for code mode.
            arguments: Tool arguments dict.
            sandbox_env: User-provided env vars (already validated by transport layer).

        Returns:
            MCPToolResult with execution output.

        Raises:
            ValueError: If tool name format is invalid, backend unavailable, or scope missing.
            NotFoundError: If namespace/function not found.
        """
        self._check_scope(name)

        if name in ("execute_python", "execute") and self.mode == "code":
            return await self._execute_code_mode(arguments.get("code", ""), sandbox_env=sandbox_env)

        if name == "execute_typescript" and self.mode == "code":
            return await self._execute_code_mode_ts(
                arguments.get("code", ""), sandbox_env=sandbox_env
            )

        if name == "_env_status":
            return await self._handle_env_status(sandbox_env)

        if "." not in name:
            raise ValueError(f"Invalid tool name format. Expected service.function, got: {name}")

        service_name, function_name = name.split(".", 1)
        namespace = await self._get_namespace()

        function, version = await self.function_service.get_for_execution(
            namespace_id=namespace.id,
            service_name=service_name,
            function_name=function_name,
        )

        # Filter env vars to only those declared by this function
        filtered_env = (
            filter_env_for_function(
                sandbox_env or {},
                version.required_env,
                version.optional_env,
            )
            or None
        )

        # Check all required env vars are present
        missing = check_required_env(
            filtered_env or {},
            version.required_env,
        )
        if missing:
            return MCPToolResult(
                content=[
                    MCPContent(
                        text=json.dumps(
                            {
                                "error": "missing_env",
                                "missing": missing,
                                "message": f"Required environment variables not provided: {', '.join(missing)}",
                            }
                        )
                    )
                ],
                isError=True,
            )

        backend = get_backend(version.backend)
        if not backend:
            raise ValueError(f"Backend not available: {version.backend}")

        execution_id = str(uuid.uuid4())
        start_time = datetime.now(UTC)

        result = await backend.execute(
            code=version.code,
            config=version.config,
            input_data=arguments,
            account=self.account,
            execution_id=execution_id,
            sandbox_env=filtered_env,
            language=getattr(version, "language", "python"),
        )

        execution_time_ms = result.execution_time_ms or int(
            (datetime.now(UTC) - start_time).total_seconds() * 1000
        )

        logger.info(
            "function_executed",
            function=name,
            version=version.version,
            backend=version.backend,
            execution_time_ms=execution_time_ms,
            execution_id=execution_id,
            success=result.success,
        )

        if result.success:
            content_text = json.dumps(result.output)
        else:
            content_text = json.dumps(
                {
                    "error": result.error,
                    "error_type": result.error_type,
                    "stderr": result.stderr,
                }
            )

        return MCPToolResult(
            content=[MCPContent(text=content_text)],
            isError=not result.success,
            metadata={
                "function": name,
                "version": version.version,
                "backend": version.backend,
                "execution_time_ms": execution_time_ms,
                "executed_at": datetime.now(UTC).isoformat(),
                "execution_id": execution_id,
            },
        )

    async def _execute_code_mode(
        self,
        code: str,
        sandbox_env: dict[str, str] | None = None,
    ) -> MCPToolResult:
        """Execute agent-written code in a sandbox with function wrappers.

        Generates a ``functions/`` package from the namespace's DB functions,
        writes it into the sandbox directory, and runs the agent's code.
        The call log from ``functions._registry`` is captured so that
        service/function call_counts can be incremented by the transport layer.
        """
        from mcpworks_api.mcp.code_mode import generate_functions_package

        if not code:
            raise ValueError("No code provided")

        namespace = await self._get_namespace()
        functions = await self.function_service.list_all_for_namespace(namespace_id=namespace.id)

        run_url = f"https://{self.namespace_name}.run.mcpworks.io/mcp"
        extra_files = generate_functions_package(functions, self.namespace_name, run_url=run_url)

        # Inject API key for cross-language bridge (TS functions callable from Python)
        has_ts = any(getattr(v, "language", "python") == "typescript" for _, v in functions)
        if has_ts and self.api_key and self.api_key.key:
            if sandbox_env is None:
                sandbox_env = {}
            sandbox_env["__MCPWORKS_BRIDGE_KEY__"] = self.api_key.key

        backend = get_backend("code_sandbox")
        if not backend:
            raise ValueError("Code sandbox backend not available")

        # Append call-log capture (legacy stderr path, kept as fallback).
        # Primary path: execute.py reads /sandbox/.call_log directly (FINDING-04).
        augmented_code = code + _CALL_LOG_CAPTURE_SNIPPET

        execution_id = str(uuid.uuid4())
        start_time = datetime.now(UTC)

        result = await backend.execute(
            code=augmented_code,
            config=None,
            input_data={},
            account=self.account,
            execution_id=execution_id,
            extra_files=extra_files,
            sandbox_env=sandbox_env,
        )

        execution_time_ms = result.execution_time_ms or int(
            (datetime.now(UTC) - start_time).total_seconds() * 1000
        )

        # FINDING-04: Prefer call_log from output.json (read by trusted execute.py)
        # Fall back to stderr marker parsing for dev-mode / legacy compatibility
        called_functions = result.call_log or _parse_call_log(result.stderr)

        logger.info(
            "code_executed",
            execution_time_ms=execution_time_ms,
            execution_id=execution_id,
            success=result.success,
            called_functions=called_functions,
        )

        if result.success:
            content_text = json.dumps(result.output)
        else:
            content_text = json.dumps(
                {
                    "error": result.error,
                    "error_type": result.error_type,
                    "stderr": result.stderr,
                }
            )

        return MCPToolResult(
            content=[MCPContent(text=content_text)],
            isError=not result.success,
            metadata={
                "mode": "code",
                "execution_time_ms": execution_time_ms,
                "execution_id": execution_id,
                "called_functions": called_functions,
            },
        )

    async def _execute_code_mode_ts(
        self,
        code: str,
        sandbox_env: dict[str, str] | None = None,
    ) -> MCPToolResult:
        """Execute TypeScript code in a Node.js sandbox with function wrappers.

        Generates a ``functions/`` Node.js package from the namespace's DB functions,
        writes it into the sandbox directory, and runs the agent's TypeScript code.
        """
        from mcpworks_api.mcp.code_mode_ts import generate_ts_functions_package

        if not code:
            raise ValueError("No code provided")

        namespace = await self._get_namespace()
        functions = await self.function_service.list_all_for_namespace(namespace_id=namespace.id)

        run_url = f"https://{self.namespace_name}.run.mcpworks.io/mcp"
        extra_files = generate_ts_functions_package(functions, self.namespace_name, run_url=run_url)

        # Inject API key for cross-language bridge (Python functions callable from TS)
        has_py = any(getattr(v, "language", "python") == "python" for _, v in functions)
        if has_py and self.api_key and self.api_key.key:
            if sandbox_env is None:
                sandbox_env = {}
            sandbox_env["__MCPWORKS_BRIDGE_KEY__"] = self.api_key.key

        backend = get_backend("code_sandbox")
        if not backend:
            raise ValueError("Code sandbox backend not available")

        execution_id = str(uuid.uuid4())
        start_time = datetime.now(UTC)

        result = await backend.execute(
            code=code,
            config=None,
            input_data={},
            account=self.account,
            execution_id=execution_id,
            extra_files=extra_files,
            sandbox_env=sandbox_env,
            language="typescript",
        )

        execution_time_ms = result.execution_time_ms or int(
            (datetime.now(UTC) - start_time).total_seconds() * 1000
        )

        called_functions = result.call_log or []

        logger.info(
            "ts_code_executed",
            execution_time_ms=execution_time_ms,
            execution_id=execution_id,
            success=result.success,
            called_functions=called_functions,
        )

        if result.success:
            content_text = json.dumps(result.output)
        else:
            content_text = json.dumps(
                {
                    "error": result.error,
                    "error_type": result.error_type,
                    "stderr": result.stderr,
                }
            )

        return MCPToolResult(
            content=[MCPContent(text=content_text)],
            isError=not result.success,
            metadata={
                "mode": "code_typescript",
                "execution_time_ms": execution_time_ms,
                "execution_id": execution_id,
                "called_functions": called_functions,
            },
        )

    async def _handle_env_status(
        self,
        sandbox_env: dict[str, str] | None,
    ) -> MCPToolResult:
        """Return env var configuration status for all namespace functions."""
        namespace = await self._get_namespace()
        functions = await self.function_service.list_all_for_namespace(namespace_id=namespace.id)
        provided = set(sandbox_env or {})

        all_required: set[str] = set()
        all_optional: set[str] = set()
        per_function: dict[str, dict] = {}

        for func, version in functions:
            tool_name = f"{func.service.name}.{func.name}"
            req = version.required_env or []
            opt = version.optional_env or []
            all_required.update(req)
            all_optional.update(opt)

            fn_missing = [r for r in req if r not in provided]
            per_function[tool_name] = {
                "required": req,
                "optional": opt,
                "status": "missing_env" if fn_missing else "ready",
            }

        configured = sorted(provided & (all_required | all_optional))
        missing_required = sorted(all_required - provided)
        missing_optional = sorted(all_optional - provided)

        result: dict[str, Any] = {
            "configured": configured,
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "functions": per_function,
        }
        if missing_required:
            result["note"] = (
                "Functions with status 'missing_env' will fail. "
                "Add missing variables to your MCP server X-MCPWorks-Env header."
            )

        return MCPToolResult(
            content=[MCPContent(text=json.dumps(result))],
        )

    async def _handle_tools_list(self, request_id) -> JSONRPCResponse:
        """Generate tools list from database functions."""
        tools = await self.get_tools()
        result = MCPToolsListResult(tools=tools)
        return make_success_response(result.model_dump(), request_id)

    async def _handle_tools_call(
        self,
        params: dict[str, Any],
        request_id,
    ) -> JSONRPCResponse:
        """Execute a function via its backend."""
        try:
            call_params = MCPToolCallParams(**params)
        except Exception as e:
            return make_error_response(
                MCPErrorCodes.INVALID_PARAMS,
                f"Invalid tool call params: {e}",
                request_id=request_id,
            )

        try:
            result = await self.dispatch_tool(call_params.name, call_params.arguments)
            return make_success_response(result.model_dump(), request_id)
        except ValueError as e:
            return make_error_response(
                MCPErrorCodes.INVALID_PARAMS,
                str(e),
                request_id=request_id,
            )
        except NotFoundError as e:
            return make_error_response(
                MCPErrorCodes.NOT_FOUND,
                str(e),
                request_id=request_id,
            )
        except Exception as e:
            return make_error_response(
                MCPErrorCodes.EXECUTION_ERROR,
                str(e),
                request_id=request_id,
            )


# ---------------------------------------------------------------------------
# Code-mode call-log helpers
# ---------------------------------------------------------------------------

_CALL_LOG_MARKER = "__MCPWORKS_CALL_LOG__:"

_CALL_LOG_CAPTURE_SNIPPET = """

# --- MCPWorks: capture call log for billing ---
try:
    import sys as _sys, json as _json
    _log = []
    try:
        with open("/sandbox/.call_log") as _clf:
            _log = [_ln.strip() for _ln in _clf if _ln.strip()]
    except Exception:
        try:
            from functions._registry import _get_call_log as _gcl
            _log = _gcl()
        except Exception:
            pass
    if _log:
        _sys.stderr.write("\\n__MCPWORKS_CALL_LOG__:" + _json.dumps(_log) + "\\n")
except Exception:
    pass
"""


def _parse_call_log(stderr: str | None) -> list[str]:
    """Extract the list of called functions from sandbox stderr.

    The capture snippet writes a JSON-encoded list to stderr with a known
    marker prefix.  Returns an empty list if not found or unparseable.
    """
    if not stderr:
        return []
    for line in stderr.splitlines():
        line = line.strip()
        if line.startswith(_CALL_LOG_MARKER):
            try:
                return json.loads(line[len(_CALL_LOG_MARKER) :])
            except (json.JSONDecodeError, TypeError):
                pass
    return []

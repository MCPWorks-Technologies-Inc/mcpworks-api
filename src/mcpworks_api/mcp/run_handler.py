"""Run MCP Handler - Execution interface for namespace functions.

Generates dynamic tools from database and dispatches to backends.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.backends import get_backend
from mcpworks_api.core.exceptions import NotFoundError
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
from mcpworks_api.models import Account, Namespace
from mcpworks_api.services.function import FunctionService
from mcpworks_api.services.namespace import NamespaceServiceManager


class RunMCPHandler:
    """Handler for *.run.mcpworks.io endpoints.

    Provides function execution by:
    1. Dynamically generating tools from database functions
    2. Dispatching execution to appropriate backend
    3. Recording execution metrics
    """

    def __init__(
        self,
        namespace: str,
        account: Account,
        db: AsyncSession,
    ):
        """Initialize handler.

        Args:
            namespace: The namespace name from subdomain.
            account: The authenticated account.
            db: Database session.
        """
        self.namespace_name = namespace
        self.account = account
        self.db = db
        self.namespace_service = NamespaceServiceManager(db)
        self.function_service = FunctionService(db)
        self._namespace: Namespace | None = None

    async def _get_namespace(self) -> Namespace:
        """Get and cache the current namespace."""
        if self._namespace is None:
            self._namespace = await self.namespace_service.get_by_name(
                self.namespace_name,
                self.account.id,
            )
        return self._namespace

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
        namespace = await self._get_namespace()
        functions = await self.function_service.list_all_for_namespace(namespace_id=namespace.id)

        tools = []
        for func, version in functions:
            tool_name = f"{func.service.name}.{func.name}"
            tools.append(
                MCPTool(
                    name=tool_name,
                    description=func.description or f"Execute {tool_name}",
                    inputSchema=version.input_schema or {"type": "object", "properties": {}},
                )
            )
        return tools

    async def dispatch_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolResult:
        """Execute a function via its backend without JSON-RPC wrapping.

        Args:
            name: Tool name in service.function format.
            arguments: Tool arguments dict.

        Returns:
            MCPToolResult with execution output.

        Raises:
            ValueError: If tool name format is invalid or backend unavailable.
            NotFoundError: If namespace/function not found.
        """
        if "." not in name:
            raise ValueError(f"Invalid tool name format. Expected service.function, got: {name}")

        service_name, function_name = name.split(".", 1)
        namespace = await self._get_namespace()

        function, version = await self.function_service.get_for_execution(
            namespace_id=namespace.id,
            service_name=service_name,
            function_name=function_name,
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
        )

        execution_time_ms = result.execution_time_ms or int(
            (datetime.now(UTC) - start_time).total_seconds() * 1000
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

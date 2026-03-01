"""Create MCP Handler - Management interface for namespaces, services, functions.

Exposes 13 tools:
- make_namespace, list_namespaces
- make_service, list_services, delete_service
- make_function, update_function, delete_function, list_functions, describe_function
- list_packages
- list_templates, describe_template
"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.exceptions import ConflictError, ForbiddenError, NotFoundError
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
from mcpworks_api.services.namespace import (
    NamespaceServiceManager,
    NamespaceServiceService,
)

VALID_SCOPES = frozenset({"read", "write", "execute"})


class CreateMCPHandler:
    """Handler for *.create.mcpworks.io endpoints.

    Provides management operations for namespaces, services, and functions.
    """

    TOOL_SCOPES: dict[str, str] = {
        "list_namespaces": "read",
        "list_services": "read",
        "list_functions": "read",
        "describe_function": "read",
        "list_packages": "read",
        "list_templates": "read",
        "describe_template": "read",
        "make_namespace": "write",
        "make_service": "write",
        "delete_service": "write",
        "make_function": "write",
        "update_function": "write",
        "delete_function": "write",
    }

    def __init__(
        self,
        namespace: str,
        account: Account,
        db: AsyncSession,
        api_key: APIKey,
    ):
        self.namespace_name = namespace
        self.account = account
        self.db = db
        self.api_key = api_key
        self.namespace_service = NamespaceServiceManager(db)
        self.service_service = NamespaceServiceService(db)
        self.function_service = FunctionService(db)

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
                    "name": f"mcpworks-create-{self.namespace_name}",
                    "version": "1.0.0",
                },
            },
            request_id,
        )

    @classmethod
    def get_tools(cls) -> list[MCPTool]:
        """Return static list of management tools."""
        return [
            MCPTool(
                name="make_namespace",
                description="Create a new namespace for organizing services and functions",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Namespace name (lowercase, alphanumeric, hyphens, 1-63 chars)",
                            "pattern": "^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional description",
                        },
                    },
                    "required": ["name"],
                },
            ),
            MCPTool(
                name="list_namespaces",
                description="List all namespaces for the current account",
                inputSchema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="make_service",
                description="Create a new service within the current namespace",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Service name",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional description",
                        },
                    },
                    "required": ["name"],
                },
            ),
            MCPTool(
                name="list_services",
                description="List all services in the current namespace",
                inputSchema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="delete_service",
                description="Delete a service and all its functions",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Service name"},
                    },
                    "required": ["name"],
                },
            ),
            MCPTool(
                name="make_function",
                description="Create a new function in a service",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string", "description": "Service name"},
                        "name": {"type": "string", "description": "Function name"},
                        "backend": {
                            "type": "string",
                            "enum": ["code_sandbox", "activepieces", "nanobot", "github_repo"],
                            "description": "Execution backend",
                        },
                        "code": {
                            "type": "string",
                            "description": "Function code (for code_sandbox)",
                        },
                        "config": {
                            "type": "object",
                            "description": "Backend-specific configuration",
                        },
                        "input_schema": {
                            "type": "object",
                            "description": "JSON Schema for input",
                        },
                        "output_schema": {
                            "type": "object",
                            "description": "JSON Schema for output",
                        },
                        "description": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "requirements": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Python packages required (from allowed list). Use list_packages to see available.",
                        },
                        "required_env": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Environment variables required for execution (e.g. ['OPENAI_API_KEY']). Caller must provide these via X-MCPWorks-Env header.",
                        },
                        "optional_env": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional environment variables the function can use if provided.",
                        },
                        "created_by": {
                            "type": "string",
                            "description": "Who created this function (e.g. 'Claude Opus 4.6'). Optional attribution.",
                        },
                        "template": {
                            "type": "string",
                            "description": "Clone from a template (e.g. hello-world). Overrides code/schemas/requirements. Use list_templates to see available.",
                        },
                    },
                    "required": ["service", "name", "backend"],
                },
            ),
            MCPTool(
                name="update_function",
                description="Update a function (creates new version)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "name": {"type": "string"},
                        "backend": {"type": "string"},
                        "code": {"type": "string"},
                        "config": {"type": "object"},
                        "input_schema": {"type": "object"},
                        "output_schema": {"type": "object"},
                        "description": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "requirements": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Python packages required (from allowed list). Use list_packages to see available.",
                        },
                        "required_env": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Environment variables required for execution.",
                        },
                        "optional_env": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional environment variables.",
                        },
                        "created_by": {
                            "type": "string",
                            "description": "Who created this function (e.g. 'Claude Opus 4.6'). Optional attribution.",
                        },
                        "restore_version": {
                            "type": "integer",
                            "description": "Restore from a previous version number",
                        },
                    },
                    "required": ["service", "name"],
                },
            ),
            MCPTool(
                name="delete_function",
                description="Delete a function",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "name": {"type": "string"},
                    },
                    "required": ["service", "name"],
                },
            ),
            MCPTool(
                name="list_functions",
                description="List functions in a service",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "tag": {"type": "string", "description": "Filter by tag"},
                    },
                    "required": ["service"],
                },
            ),
            MCPTool(
                name="describe_function",
                description="Get detailed function info including version history",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "name": {"type": "string"},
                    },
                    "required": ["service", "name"],
                },
            ),
            MCPTool(
                name="list_packages",
                description="List available Python packages for sandbox functions, grouped by category",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            MCPTool(
                name="list_templates",
                description="List available function templates for quick-start",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            MCPTool(
                name="describe_template",
                description="Get full template details including code and schemas",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Template name (e.g. hello-world, csv-analyzer)",
                        },
                    },
                    "required": ["name"],
                },
            ),
        ]

    def _check_scope(self, tool_name: str) -> None:
        """Check that the API key has the required scope for a tool.

        Raises ValueError if scope is missing.
        """
        required = self.TOOL_SCOPES.get(tool_name)
        if required and not self.api_key.has_scope(required):
            raise ValueError(f"API key missing required scope '{required}' for tool '{tool_name}'")

    async def dispatch_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        sandbox_env: dict[str, str] | None = None,  # noqa: ARG002
    ) -> MCPToolResult:
        """Dispatch tool call directly without JSON-RPC wrapping.

        Args:
            name: Tool name.
            arguments: Tool arguments dict.
            sandbox_env: Ignored for create handler (env vars are run-only).

        Returns:
            MCPToolResult with tool output.

        Raises:
            ValueError: If tool name is unknown or scope missing.
            NotFoundError, ConflictError, ForbiddenError: From tool logic.
        """
        self._check_scope(name)

        handlers = {
            "make_namespace": self._make_namespace,
            "list_namespaces": self._list_namespaces,
            "make_service": self._make_service,
            "list_services": self._list_services,
            "delete_service": self._delete_service,
            "make_function": self._make_function,
            "update_function": self._update_function,
            "delete_function": self._delete_function,
            "list_functions": self._list_functions,
            "describe_function": self._describe_function,
            "list_packages": self._list_packages,
            "list_templates": self._list_templates,
            "describe_template": self._describe_template,
        }

        handler = handlers.get(name)
        if not handler:
            raise ValueError(f"Unknown tool: {name}")

        return await handler(**arguments)

    async def _handle_tools_list(self, request_id) -> JSONRPCResponse:
        """Return list of available management tools."""
        result = MCPToolsListResult(tools=self.get_tools())
        return make_success_response(result.model_dump(), request_id)

    async def _handle_tools_call(
        self,
        params: dict[str, Any],
        request_id,
    ) -> JSONRPCResponse:
        """Dispatch tool call to appropriate method."""
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
                MCPErrorCodes.METHOD_NOT_FOUND,
                str(e),
                request_id=request_id,
            )
        except NotFoundError as e:
            return make_error_response(
                MCPErrorCodes.NOT_FOUND,
                str(e),
                request_id=request_id,
            )
        except ConflictError as e:
            return make_error_response(
                MCPErrorCodes.INVALID_PARAMS,
                str(e),
                request_id=request_id,
            )
        except ForbiddenError as e:
            return make_error_response(
                MCPErrorCodes.FORBIDDEN,
                str(e),
                request_id=request_id,
            )
        except Exception as e:
            return make_error_response(
                MCPErrorCodes.EXECUTION_ERROR,
                str(e),
                request_id=request_id,
            )

    async def _get_current_namespace(self) -> Namespace:
        """Get the current namespace (owner-only, for write operations)."""
        return await self.namespace_service.get_by_name(
            self.namespace_name,
            self.account.id,
        )

    async def _get_current_namespace_read(self) -> Namespace:
        """Get the current namespace with share-based read access."""
        return await self.namespace_service.get_by_name(
            self.namespace_name,
            self.account.id,
            user_id=self.account.user_id,
            required_permission="read",
        )

    # Tool implementations
    async def _make_namespace(
        self,
        name: str,
        description: str | None = None,
    ) -> MCPToolResult:
        """Create a new namespace."""
        namespace = await self.namespace_service.create(
            account_id=self.account.id,
            name=name,
            description=description,
        )
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "id": str(namespace.id),
                            "name": namespace.name,
                            "create_endpoint": namespace.create_endpoint,
                            "run_endpoint": namespace.run_endpoint,
                            "created_at": namespace.created_at.isoformat(),
                        }
                    )
                )
            ]
        )

    async def _list_namespaces(self) -> MCPToolResult:
        """List all namespaces for account (including shared)."""
        namespaces, total = await self.namespace_service.list(
            self.account.id,
            user_id=self.account.user_id,
        )
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "namespaces": [
                                {
                                    "name": ns.name,
                                    "description": ns.description,
                                    "call_count": ns.call_count,
                                    "create_endpoint": ns.create_endpoint,
                                    "run_endpoint": ns.run_endpoint,
                                }
                                for ns in namespaces
                            ],
                            "total": total,
                        }
                    )
                )
            ]
        )

    async def _make_service(
        self,
        name: str,
        description: str | None = None,
    ) -> MCPToolResult:
        """Create a new service in current namespace."""
        namespace = await self._get_current_namespace()
        service = await self.service_service.create(
            namespace_id=namespace.id,
            name=name,
            description=description,
        )
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "name": service.name,
                            "namespace": self.namespace_name,
                            "created_at": service.created_at.isoformat(),
                        }
                    )
                )
            ]
        )

    async def _list_services(self) -> MCPToolResult:
        """List services in current namespace."""
        namespace = await self._get_current_namespace_read()
        services = await self.service_service.list(namespace.id)
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "services": [
                                {
                                    "name": s.name,
                                    "description": s.description,
                                    "function_count": s.function_count,
                                    "call_count": s.call_count,
                                }
                                for s in services
                            ],
                            "namespace": self.namespace_name,
                        }
                    )
                )
            ]
        )

    async def _delete_service(self, name: str) -> MCPToolResult:
        """Delete a service."""
        namespace = await self._get_current_namespace()
        service = await self.service_service.get_by_name(namespace.id, name)
        await self.service_service.delete(service.id)
        return MCPToolResult(content=[MCPContent(text=f"Deleted service: {name}")])

    async def _make_function(
        self,
        service: str,
        name: str,
        backend: str,
        code: str | None = None,
        config: dict[str, Any] | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        requirements: list[str] | None = None,
        required_env: list[str] | None = None,
        optional_env: list[str] | None = None,
        created_by: str | None = None,
        template: str | None = None,
    ) -> MCPToolResult:
        """Create a new function."""
        # ORDER-011: Apply template defaults if specified
        if template:
            from mcpworks_api.templates import get_template

            tmpl = get_template(template)
            if not tmpl:
                return MCPToolResult(
                    content=[
                        MCPContent(text=json.dumps({"error": f"Unknown template: {template}"}))
                    ],
                    isError=True,
                )
            # Template provides defaults; explicit args override
            if code is None:
                code = tmpl.code
            if input_schema is None:
                input_schema = tmpl.input_schema
            if output_schema is None:
                output_schema = tmpl.output_schema
            if description is None:
                description = tmpl.description
            if tags is None:
                tags = tmpl.tags
            if requirements is None and tmpl.requirements:
                requirements = tmpl.requirements

        # Validate requirements against allow-list
        validated_reqs = None
        if requirements:
            from mcpworks_api.sandbox.packages import validate_requirements

            validated_reqs, errors = validate_requirements(requirements)
            if errors:
                return MCPToolResult(
                    content=[MCPContent(text=json.dumps({"errors": errors}))],
                    isError=True,
                )

        # Validate env var names against blocklist
        validated_required_env = None
        validated_optional_env = None
        if required_env or optional_env:
            from mcpworks_api.mcp.env_passthrough import EnvPassthroughError, _validate_key

            all_env_names = (required_env or []) + (optional_env or [])
            for env_name in all_env_names:
                try:
                    _validate_key(env_name)
                except EnvPassthroughError as e:
                    return MCPToolResult(
                        content=[MCPContent(text=json.dumps({"error": str(e)}))],
                        isError=True,
                    )
            validated_required_env = required_env
            validated_optional_env = optional_env

        credential_warnings: list[str] = []
        if code:
            from mcpworks_api.sandbox.credential_scan import scan_code_for_credentials

            credential_warnings = scan_code_for_credentials(code)

        namespace = await self._get_current_namespace()
        svc = await self.service_service.get_by_name(namespace.id, service)

        function = await self.function_service.create(
            service_id=svc.id,
            name=name,
            backend=backend,
            code=code,
            config=config,
            input_schema=input_schema,
            output_schema=output_schema,
            description=description,
            tags=tags,
            requirements=validated_reqs,
            required_env=validated_required_env,
            optional_env=validated_optional_env,
            created_by=created_by,
        )
        result: dict[str, Any] = {
            "name": f"{service}.{name}",
            "version": 1,
            "backend": backend,
            "created_at": function.created_at.isoformat(),
        }
        if validated_reqs:
            result["requirements"] = validated_reqs
        if validated_required_env:
            result["required_env"] = validated_required_env
        if validated_optional_env:
            result["optional_env"] = validated_optional_env
        if created_by:
            result["created_by"] = created_by
        if credential_warnings:
            result["warnings"] = credential_warnings
        return MCPToolResult(content=[MCPContent(text=json.dumps(result))])

    async def _update_function(
        self,
        service: str,
        name: str,
        backend: str | None = None,
        code: str | None = None,
        config: dict[str, Any] | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        requirements: list[str] | None = None,
        required_env: list[str] | None = None,
        optional_env: list[str] | None = None,
        created_by: str | None = None,
        restore_version: int | None = None,
    ) -> MCPToolResult:
        """Update a function (creates new version)."""
        # Validate requirements against allow-list
        validated_reqs = None
        if requirements is not None:
            from mcpworks_api.sandbox.packages import validate_requirements

            validated_reqs, errors = validate_requirements(requirements)
            if errors:
                return MCPToolResult(
                    content=[MCPContent(text=json.dumps({"errors": errors}))],
                    isError=True,
                )

        # Validate env var names against blocklist
        validated_required_env = required_env
        validated_optional_env = optional_env
        if required_env is not None or optional_env is not None:
            from mcpworks_api.mcp.env_passthrough import EnvPassthroughError, _validate_key

            all_env_names = (required_env or []) + (optional_env or [])
            for env_name in all_env_names:
                try:
                    _validate_key(env_name)
                except EnvPassthroughError as e:
                    return MCPToolResult(
                        content=[MCPContent(text=json.dumps({"error": str(e)}))],
                        isError=True,
                    )

        credential_warnings: list[str] = []
        if code:
            from mcpworks_api.sandbox.credential_scan import scan_code_for_credentials

            credential_warnings = scan_code_for_credentials(code)

        namespace = await self._get_current_namespace()
        svc = await self.service_service.get_by_name(namespace.id, service)
        function = await self.function_service.get_by_name(svc.id, name)

        # Update metadata if provided
        if description is not None or tags is not None:
            await self.function_service.update(
                function_id=function.id,
                description=description,
                tags=tags,
            )

        # Create new version if code/config/requirements/env changes or restoring
        if restore_version:
            old_version = await self.function_service.get_version(function.id, restore_version)
            await self.function_service.create_version(
                function_id=function.id,
                backend=old_version.backend,
                code=old_version.code,
                config=old_version.config,
                input_schema=old_version.input_schema,
                output_schema=old_version.output_schema,
                requirements=old_version.requirements,
                required_env=old_version.required_env,
                optional_env=old_version.optional_env,
                created_by=created_by,
            )
            message = f"Restored from v{restore_version}"
        elif any(
            [
                backend,
                code,
                config,
                input_schema,
                output_schema,
                requirements is not None,
                required_env is not None,
                optional_env is not None,
            ]
        ):
            active = await self.function_service.get_active_version(function.id)
            await self.function_service.create_version(
                function_id=function.id,
                backend=backend or active.backend,
                code=code if code is not None else active.code,
                config=config if config is not None else active.config,
                input_schema=input_schema if input_schema is not None else active.input_schema,
                output_schema=output_schema if output_schema is not None else active.output_schema,
                requirements=validated_reqs if requirements is not None else active.requirements,
                required_env=validated_required_env
                if required_env is not None
                else active.required_env,
                optional_env=validated_optional_env
                if optional_env is not None
                else active.optional_env,
                created_by=created_by,
            )
            message = "Created new version"
        else:
            message = "Updated metadata only"

        # Refresh function to get updated active_version
        function = await self.function_service.get_by_id(function.id)

        result_data: dict[str, Any] = {
            "name": f"{service}.{name}",
            "version": function.active_version,
            "message": message,
        }
        if created_by:
            result_data["created_by"] = created_by
        if credential_warnings:
            result_data["warnings"] = credential_warnings
        return MCPToolResult(content=[MCPContent(text=json.dumps(result_data))])

    async def _delete_function(self, service: str, name: str) -> MCPToolResult:
        """Delete a function."""
        namespace = await self._get_current_namespace()
        svc = await self.service_service.get_by_name(namespace.id, service)
        function = await self.function_service.get_by_name(svc.id, name)
        await self.function_service.delete(function.id)
        return MCPToolResult(content=[MCPContent(text=f"Deleted function: {service}.{name}")])

    async def _list_functions(
        self,
        service: str,
        tag: str | None = None,
    ) -> MCPToolResult:
        """List functions in a service."""
        namespace = await self._get_current_namespace_read()
        svc = await self.service_service.get_by_name(namespace.id, service)

        tags = [tag] if tag else None
        functions, total = await self.function_service.list(svc.id, tags=tags)

        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "functions": [
                                {
                                    "name": f"{service}.{f.name}",
                                    "description": f.description,
                                    "version": f.active_version,
                                    "tags": f.tags or [],
                                    "call_count": f.call_count,
                                }
                                for f in functions
                            ],
                            "total": total,
                        }
                    )
                )
            ]
        )

    async def _describe_function(self, service: str, name: str) -> MCPToolResult:
        """Get detailed function info."""
        namespace = await self._get_current_namespace_read()
        svc = await self.service_service.get_by_name(namespace.id, service)
        function = await self.function_service.get_by_name(svc.id, name)
        details = await self.function_service.describe(function.id)
        return MCPToolResult(content=[MCPContent(text=json.dumps(details))])

    async def _list_packages(self) -> MCPToolResult:
        """List available Python packages for sandbox functions."""
        from mcpworks_api.sandbox.packages import (
            PACKAGE_REGISTRY,
            get_registry_by_category,
        )

        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "packages": get_registry_by_category(),
                            "total": len(PACKAGE_REGISTRY),
                        }
                    )
                )
            ]
        )

    async def _list_templates(self) -> MCPToolResult:
        """List available function templates."""
        from mcpworks_api.templates import list_templates

        return MCPToolResult(content=[MCPContent(text=json.dumps({"templates": list_templates()}))])

    async def _describe_template(self, name: str) -> MCPToolResult:
        """Get full template details including code and schemas."""
        from mcpworks_api.templates import get_template

        tmpl = get_template(name)
        if not tmpl:
            return MCPToolResult(
                content=[MCPContent(text=json.dumps({"error": f"Unknown template: {name}"}))],
                isError=True,
            )
        return MCPToolResult(content=[MCPContent(text=json.dumps(tmpl.to_full_dict()))])

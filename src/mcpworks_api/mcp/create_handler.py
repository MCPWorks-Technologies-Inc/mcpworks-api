"""Create MCP Handler - Management interface for namespaces, services, functions, agents.

Exposes 13 tools (all accounts):
- make_namespace, list_namespaces
- make_service, list_services, delete_service
- make_function, update_function, delete_function, list_functions, describe_function
- list_packages
- list_templates, describe_template

Exposes 6 additional tools (agent-enabled tiers only):
- make_agent, list_agents, describe_agent, start_agent, stop_agent, destroy_agent
"""

import contextlib
import json
import secrets
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api import url_builder
from mcpworks_api.backends.sandbox import TIER_CONFIG, resolve_execution_tier
from mcpworks_api.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from mcpworks_api.core.input_limits import InputTooLarge, validate_input_size
from mcpworks_api.core.tool_permissions import (
    MANAGEMENT_RATE_LIMITS,
    ToolTier,
    is_tool_allowed,
    requires_confirmation,
)
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
from mcpworks_api.services.agent_service import AgentService
from mcpworks_api.services.function import FunctionService
from mcpworks_api.services.namespace import (
    NamespaceServiceManager,
    NamespaceServiceService,
)

VALID_SCOPES = frozenset({"read", "write", "execute"})

JSON_ARGUMENT_KEYS = frozenset(
    {
        "input_schema",
        "output_schema",
        "config",
        "failure_policy",
        "servers",
        "requirements",
        "tags",
        "required_env",
        "optional_env",
    }
)


def _coerce_json_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Defensively parse arguments that should be dicts/lists but may arrive as JSON strings.

    Some MCP clients serialize nested objects and arrays as strings instead of
    native JSON. This silently parses them so handler methods always receive
    the correct types.
    """
    for key in JSON_ARGUMENT_KEYS:
        val = arguments.get(key)
        if isinstance(val, str):
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                arguments[key] = json.loads(val)
    return arguments


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
        "list_agents": "read",
        "describe_agent": "read",
        "make_agent": "write",
        "start_agent": "write",
        "stop_agent": "write",
        "destroy_agent": "write",
        "add_schedule": "write",
        "remove_schedule": "write",
        "list_schedules": "read",
        "add_webhook": "write",
        "remove_webhook": "write",
        "list_webhooks": "read",
        "set_agent_state": "write",
        "get_agent_state": "read",
        "delete_agent_state": "write",
        "list_agent_state_keys": "read",
        "configure_agent_ai": "write",
        "remove_agent_ai": "write",
        "configure_mcp_servers": "write",
        "configure_orchestration_limits": "write",
        "configure_heartbeat": "write",
        "chat_with_agent": "read",
        "add_channel": "write",
        "remove_channel": "write",
        "clone_agent": "write",
        "lock_function": "write",
        "unlock_function": "write",
        "publish_view": "write",
        "get_view_url": "read",
        "clear_view": "write",
        "configure_chat_token": "write",
    }

    _logger = structlog.get_logger(__name__)

    def __init__(
        self,
        namespace: str,
        account: Account,
        db: AsyncSession,
        api_key: APIKey,
        agent=None,
    ):
        self.namespace_name = namespace
        self.account = account
        self.db = db
        self.api_key = api_key
        self.agent = agent
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

    def _tier_notice(self) -> str:
        """Build a terse sandbox constraint notice for tool descriptions."""
        tier_str = self.account.user.effective_tier
        tier = resolve_execution_tier(tier_str)
        cfg = TIER_CONFIG[tier]
        parts = [
            f"Sandbox limits ({tier_str} tier): timeout={cfg['timeout_sec']}s, memory={cfg['memory_mb']}MB."
        ]
        if not cfg["network"]:
            parts.append(
                "Network: BLOCKED — code using requests/httpx/urllib/sockets will fail at runtime. Upgrade to Builder for network access."
            )
        else:
            parts.append("Network: available.")
        return " ".join(parts)

    def get_tools(self) -> list[MCPTool]:
        """Return management tools from centralized registry with tier-aware descriptions."""
        from mcpworks_api.mcp.tool_registry import AGENT_TOOLS, BASE_TOOLS

        tier_notice = self._tier_notice()
        format_kwargs = {"tier_notice": tier_notice}

        tools = [
            MCPTool(**tool_def.render(verbosity="standard", **format_kwargs))
            for tool_def in BASE_TOOLS.values()
        ]

        is_agent = self.account.user.effective_tier in (
            "pro-agent",
            "enterprise-agent",
            "dedicated-agent",
            "trial-agent",
        )
        if is_agent:
            tools.extend(
                MCPTool(**tool_def.render(verbosity="standard", **format_kwargs))
                for tool_def in AGENT_TOOLS.values()
            )

        return tools

    def _check_scope(self, tool_name: str) -> None:
        """Check that the API key has the required scope for a tool.

        Raises ValueError if scope is missing.
        """
        required = self.TOOL_SCOPES.get(tool_name)
        if required and not self.api_key.has_scope(required):
            raise ValueError(f"API key missing required scope '{required}' for tool '{tool_name}'")

    async def _authorize_agent_tool(self, tool_name: str) -> None:
        """Check if the calling agent is allowed to use this tool.

        Direct user calls (agent is None) bypass this check.
        """
        if self.agent is None:
            return

        tier = ToolTier(getattr(self.agent, "tool_tier", "standard"))
        if not is_tool_allowed(tier, tool_name):
            self._logger.warning(
                "tool_access_denied",
                tool=tool_name,
                agent=getattr(self.agent, "name", "?"),
                tier=tier.value,
            )
            raise ForbiddenError(
                f"Agent '{self.agent.name}' (tier: {tier.value}) "
                f"is not authorized to call '{tool_name}'"
            )

    async def _check_confirmation_token(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> MCPToolResult | None:
        """For destructive ops, require a confirmation token flow.

        Returns an MCPToolResult asking for confirmation if no token provided,
        or None if the token is valid and the call should proceed.
        """
        if not requires_confirmation(tool_name):
            return None

        token = arguments.pop("confirmation_token", None)
        if token is not None:
            from mcpworks_api.core.redis import get_redis_context

            target = arguments.get("name", arguments.get("agent_name", "unknown"))
            key = f"confirm:{self.account.id}:{tool_name}:{target}"
            async with get_redis_context() as redis:
                stored = await redis.get(key)
                if stored and stored.decode() == token:
                    await redis.delete(key)
                    return None
            raise ForbiddenError("Invalid or expired confirmation token")

        from mcpworks_api.core.redis import get_redis_context

        target = arguments.get("name", arguments.get("agent_name", "unknown"))
        new_token = secrets.token_urlsafe(32)
        key = f"confirm:{self.account.id}:{tool_name}:{target}"
        async with get_redis_context() as redis:
            await redis.setex(key, 60, new_token)

        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "status": "confirmation_required",
                            "confirmation_token": new_token,
                            "expires_in": 60,
                            "message": (
                                f"{tool_name}('{target}') is irreversible. "
                                f"Call again with confirmation_token to proceed."
                            ),
                        }
                    )
                )
            ]
        )

    async def _check_management_rate_limit(self, tool_name: str) -> None:
        """Enforce per-tool rate limits on management operations."""
        rate_config = MANAGEMENT_RATE_LIMITS.get(tool_name)
        if rate_config is None:
            return

        limit, window = rate_config
        from mcpworks_api.core.redis import RateLimiter, get_redis_context

        key = f"mgmt:{self.account.id}:{tool_name}"
        async with get_redis_context() as redis:
            limiter = RateLimiter(redis)
            is_limited, current = await limiter.is_rate_limited(key, limit, window)
            if is_limited:
                raise ForbiddenError(
                    f"Rate limit exceeded for {tool_name}: "
                    f"{limit} calls per {window}s (current: {current})"
                )

    def _validate_tool_inputs(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Validate input sizes for tool arguments."""
        if tool_name in ("make_function", "update_function"):
            validate_input_size("code", arguments.get("code"))
            validate_input_size("description", arguments.get("description"))
            validate_input_size(
                "input_schema",
                json.dumps(arguments["input_schema"])
                if "input_schema" in arguments and arguments["input_schema"] is not None
                else None,
            )
            validate_input_size(
                "output_schema",
                json.dumps(arguments["output_schema"])
                if "output_schema" in arguments and arguments["output_schema"] is not None
                else None,
            )
        elif tool_name == "set_agent_state":
            val = arguments.get("value")
            if val is not None:
                validate_input_size(
                    "agent_state_value",
                    json.dumps(val) if not isinstance(val, str | bytes) else val,
                )
        elif tool_name == "configure_agent_ai":
            validate_input_size("agent_ai_config", arguments.get("system_prompt"))

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
        await self._authorize_agent_tool(name)
        await self._check_management_rate_limit(name)

        try:
            self._validate_tool_inputs(name, arguments)
        except InputTooLarge as e:
            raise ForbiddenError(str(e)) from e

        confirmation = await self._check_confirmation_token(name, arguments)
        if confirmation is not None:
            return confirmation

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
            "make_agent": self._make_agent,
            "list_agents": self._list_agents,
            "describe_agent": self._describe_agent,
            "start_agent": self._start_agent,
            "stop_agent": self._stop_agent,
            "destroy_agent": self._destroy_agent,
            "add_schedule": self._add_schedule,
            "remove_schedule": self._remove_schedule,
            "list_schedules": self._list_schedules,
            "add_webhook": self._add_webhook,
            "remove_webhook": self._remove_webhook,
            "list_webhooks": self._list_webhooks,
            "set_agent_state": self._set_agent_state,
            "get_agent_state": self._get_agent_state,
            "delete_agent_state": self._delete_agent_state,
            "list_agent_state_keys": self._list_agent_state_keys,
            "configure_agent_ai": self._configure_agent_ai,
            "remove_agent_ai": self._remove_agent_ai,
            "configure_mcp_servers": self._configure_mcp_servers,
            "configure_orchestration_limits": self._configure_orchestration_limits,
            "configure_heartbeat": self._configure_heartbeat,
            "chat_with_agent": self._chat_with_agent,
            "add_channel": self._add_channel,
            "remove_channel": self._remove_channel,
            "clone_agent": self._clone_agent,
            "lock_function": self._lock_function,
            "unlock_function": self._unlock_function,
            "publish_view": self._publish_view,
            "get_view_url": self._get_view_url,
            "clear_view": self._clear_view,
            "configure_chat_token": self._configure_chat_token,
        }

        handler = handlers.get(name)
        if not handler:
            raise ValueError(f"Unknown tool: {name}")

        arguments = _coerce_json_arguments(arguments)
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
        except InputTooLarge as e:
            return make_error_response(
                MCPErrorCodes.INVALID_PARAMS,
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
        language: str = "python",
        public_safe: bool = False,
    ) -> MCPToolResult:
        """Create a new function."""
        if language not in ("python", "typescript"):
            return MCPToolResult(
                content=[
                    MCPContent(
                        text=json.dumps({"error": "language must be 'python' or 'typescript'"})
                    )
                ],
                isError=True,
            )

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
            # Inherit language from template if caller didn't specify
            if hasattr(tmpl, "language") and tmpl.language:
                language = tmpl.language

        # Validate requirements against language-specific allow-list
        validated_reqs = None
        if requirements:
            from mcpworks_api.sandbox.packages import validate_requirements_for_language

            validated_reqs, errors = validate_requirements_for_language(requirements, language)
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
            language=language,
            public_safe=public_safe,
        )
        result: dict[str, Any] = {
            "name": f"{service}.{name}",
            "version": 1,
            "backend": backend,
            "language": language,
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

        tier = resolve_execution_tier(self.account.user.effective_tier)
        cfg = TIER_CONFIG[tier]
        if not cfg["network"] and code:
            network_libs = {"httpx", "requests", "aiohttp", "urllib.request", "socket"}
            used = [lib for lib in network_libs if lib in code]
            if used:
                warnings = result.setdefault("warnings", [])
                warnings.append(
                    f"Your code imports network libraries ({', '.join(used)}) but your tier "
                    f"does not have network access. These will fail at runtime. "
                    f"Upgrade to Builder tier or above for network access."
                )

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
        public_safe: bool | None = None,
    ) -> MCPToolResult:
        """Update a function (creates new version)."""
        # Look up function to determine its language for requirements validation
        namespace = await self._get_current_namespace()
        svc = await self.service_service.get_by_name(namespace.id, service)
        function = await self.function_service.get_by_name(svc.id, name)
        active_ver = function.get_active_version_obj()
        fn_language = active_ver.language if active_ver else "python"

        # Validate requirements against language-specific allow-list
        validated_reqs = None
        if requirements is not None:
            from mcpworks_api.sandbox.packages import validate_requirements_for_language

            validated_reqs, errors = validate_requirements_for_language(requirements, fn_language)
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

        # Update metadata if provided
        if description is not None or tags is not None or public_safe is not None:
            await self.function_service.update(
                function_id=function.id,
                description=description,
                tags=tags,
                public_safe=public_safe,
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

    async def _list_packages(self, language: str = "python") -> MCPToolResult:
        """List available packages for sandbox functions."""
        if language == "typescript":
            from mcpworks_api.sandbox.packages_node import (
                NODE_PACKAGE_REGISTRY,
                get_node_registry_by_category,
            )

            return MCPToolResult(
                content=[
                    MCPContent(
                        text=json.dumps(
                            {
                                "language": "typescript",
                                "packages": get_node_registry_by_category(),
                                "total": len(NODE_PACKAGE_REGISTRY),
                                "note": "Node.js built-ins (crypto, url, path, buffer, util, fs, http) are always available without listing.",
                            }
                        )
                    )
                ]
            )

        from mcpworks_api.sandbox.packages import (
            PACKAGE_REGISTRY,
            get_registry_by_category,
        )

        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "language": "python",
                            "packages": get_registry_by_category(),
                            "total": len(PACKAGE_REGISTRY),
                        }
                    )
                )
            ]
        )

    async def _list_templates(self) -> MCPToolResult:
        """List available function templates, with network warnings for blocked tiers."""
        from mcpworks_api.templates import list_templates

        tier = resolve_execution_tier(self.account.user.effective_tier)
        cfg = TIER_CONFIG[tier]
        templates = list_templates()
        if not cfg["network"]:
            for t in templates:
                if t.get("requires_network"):
                    t["warning"] = (
                        "This template requires network access. Your tier does not have network access."
                    )
        return MCPToolResult(content=[MCPContent(text=json.dumps({"templates": templates}))])

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

    async def _make_agent(
        self,
        name: str,
        display_name: str | None = None,
    ) -> MCPToolResult:
        """Create a new agent."""
        service = AgentService(self.db)
        agent = await service.create_agent(
            account_id=self.account.id,
            user_id=self.account.user_id,
            tier=self.account.user.effective_tier,
            name=name,
            display_name=display_name,
        )
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "id": str(agent.id),
                            "name": agent.name,
                            "status": agent.status,
                        }
                    )
                )
            ]
        )

    async def _list_agents(self) -> MCPToolResult:
        """List all agents for the current account."""
        service = AgentService(self.db)
        agents = await service.list_agents(self.account.id)
        slots = await service.get_agent_slots(self.account.id, self.account.user.effective_tier)
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "agents": [
                                {
                                    "id": str(a.id),
                                    "name": a.name,
                                    "display_name": a.display_name,
                                    "status": a.status,
                                }
                                for a in agents
                            ],
                            "slots": slots,
                        }
                    )
                )
            ]
        )

    async def _describe_agent(self, name: str) -> MCPToolResult:
        """Get full details for an agent."""
        service = AgentService(self.db)
        agent = await service.get_agent(self.account.id, name)
        result = {
            "id": str(agent.id),
            "name": agent.name,
            "display_name": agent.display_name,
            "status": agent.status,
            "ai_engine": agent.ai_engine,
            "ai_model": agent.ai_model,
            "system_prompt": agent.system_prompt,
            "auto_channel": agent.auto_channel,
            "memory_limit_mb": agent.memory_limit_mb,
            "cpu_limit": agent.cpu_limit,
            "enabled": agent.enabled,
            "created_at": agent.created_at.isoformat(),
        }
        if agent.scratchpad_token and agent.scratchpad_size_bytes > 0:
            result["view_url"] = url_builder.view_url(agent.name, agent.scratchpad_token)
            result["scratchpad_size_bytes"] = agent.scratchpad_size_bytes
            if agent.scratchpad_expires_at:
                result["scratchpad_expires_at"] = agent.scratchpad_expires_at.isoformat()
        if agent.chat_token:
            result["chat_url"] = url_builder.chat_url(agent.name, agent.chat_token)
        return MCPToolResult(content=[MCPContent(text=json.dumps(result))])

    async def _start_agent(self, name: str) -> MCPToolResult:
        """Start a stopped agent."""
        service = AgentService(self.db)
        agent = await service.start_agent(self.account.id, name)
        return MCPToolResult(
            content=[MCPContent(text=json.dumps({"name": agent.name, "status": agent.status}))]
        )

    async def _stop_agent(self, name: str) -> MCPToolResult:
        """Stop a running agent."""
        service = AgentService(self.db)
        agent = await service.stop_agent(self.account.id, name)
        return MCPToolResult(
            content=[MCPContent(text=json.dumps({"name": agent.name, "status": agent.status}))]
        )

    async def _destroy_agent(self, name: str, confirm: bool = False) -> MCPToolResult:
        """Permanently destroy an agent."""
        if not confirm:
            raise ValueError("Must confirm=true to destroy agent")
        service = AgentService(self.db)
        agent = await service.destroy_agent(self.account.id, name)
        return MCPToolResult(
            content=[MCPContent(text=json.dumps({"name": agent.name, "destroyed": True}))]
        )

    async def _add_schedule(
        self,
        agent_name: str,
        function_name: str,
        cron_expression: str,
        failure_policy: dict,
        timezone: str = "UTC",
        orchestration_mode: str = "direct",
    ) -> MCPToolResult:
        """Add a cron schedule to an agent."""
        service = AgentService(self.db)
        schedule = await service.add_schedule(
            account_id=self.account.id,
            agent_name=agent_name,
            function_name=function_name,
            cron_expression=cron_expression,
            timezone=timezone,
            failure_policy=failure_policy,
            tier=self.account.user.effective_tier,
            orchestration_mode=orchestration_mode,
        )
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "schedule_id": str(schedule.id),
                            "agent_name": agent_name,
                            "function_name": function_name,
                            "cron_expression": cron_expression,
                            "timezone": timezone,
                            "orchestration_mode": schedule.orchestration_mode,
                            "enabled": schedule.enabled,
                        }
                    )
                )
            ]
        )

    async def _remove_schedule(
        self,
        agent_name: str,
        schedule_id: str,
    ) -> MCPToolResult:
        """Remove a schedule from an agent."""
        import uuid as uuid_module

        service = AgentService(self.db)
        await service.remove_schedule(self.account.id, agent_name, uuid_module.UUID(schedule_id))
        return MCPToolResult(
            content=[MCPContent(text=json.dumps({"schedule_id": schedule_id, "removed": True}))]
        )

    async def _list_schedules(self, agent_name: str) -> MCPToolResult:
        """List all schedules for an agent."""
        service = AgentService(self.db)
        schedules = await service.list_schedules(self.account.id, agent_name)
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "schedules": [
                                {
                                    "id": str(s.id),
                                    "function_name": s.function_name,
                                    "cron_expression": s.cron_expression,
                                    "timezone": s.timezone,
                                    "orchestration_mode": s.orchestration_mode,
                                    "enabled": s.enabled,
                                    "consecutive_failures": s.consecutive_failures,
                                }
                                for s in schedules
                            ],
                            "total": len(schedules),
                        }
                    )
                )
            ]
        )

    async def _add_webhook(
        self,
        agent_name: str,
        path: str,
        handler_function_name: str,
        secret: str | None = None,
        orchestration_mode: str = "direct",
    ) -> MCPToolResult:
        """Add a webhook to an agent."""
        service = AgentService(self.db)
        webhook = await service.add_webhook(
            account_id=self.account.id,
            agent_name=agent_name,
            path=path,
            handler_function_name=handler_function_name,
            secret=secret,
            orchestration_mode=orchestration_mode,
        )
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "webhook_id": str(webhook.id),
                            "agent_name": agent_name,
                            "path": path,
                            "handler_function_name": handler_function_name,
                            "orchestration_mode": webhook.orchestration_mode,
                            "enabled": webhook.enabled,
                        }
                    )
                )
            ]
        )

    async def _remove_webhook(
        self,
        agent_name: str,
        webhook_id: str,
    ) -> MCPToolResult:
        """Remove a webhook from an agent."""
        import uuid as uuid_module

        service = AgentService(self.db)
        await service.remove_webhook(self.account.id, agent_name, uuid_module.UUID(webhook_id))
        return MCPToolResult(
            content=[MCPContent(text=json.dumps({"webhook_id": webhook_id, "removed": True}))]
        )

    async def _list_webhooks(self, agent_name: str) -> MCPToolResult:
        """List all webhooks for an agent."""
        service = AgentService(self.db)
        webhooks = await service.list_webhooks(self.account.id, agent_name)
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "webhooks": [
                                {
                                    "id": str(w.id),
                                    "path": w.path,
                                    "handler_function_name": w.handler_function_name,
                                    "orchestration_mode": w.orchestration_mode,
                                    "enabled": w.enabled,
                                }
                                for w in webhooks
                            ],
                            "total": len(webhooks),
                        }
                    )
                )
            ]
        )

    async def _set_agent_state(
        self,
        agent_name: str,
        key: str,
        value: Any,
    ) -> MCPToolResult:
        """Set a persistent state key for an agent."""
        service = AgentService(self.db)
        state_entry = await service.set_state(
            account_id=self.account.id,
            agent_name=agent_name,
            key=key,
            value=value,
            tier=self.account.user.effective_tier,
        )
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {"key": key, "size_bytes": state_entry.size_bytes, "stored": True}
                    )
                )
            ]
        )

    async def _get_agent_state(self, agent_name: str, key: str) -> MCPToolResult:
        """Get a persistent state value for an agent."""
        service = AgentService(self.db)
        value, state_entry = await service.get_state(self.account.id, agent_name, key)
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {"key": key, "value": value, "size_bytes": state_entry.size_bytes}
                    )
                )
            ]
        )

    async def _delete_agent_state(self, agent_name: str, key: str) -> MCPToolResult:
        """Delete a persistent state key for an agent."""
        service = AgentService(self.db)
        await service.delete_state(self.account.id, agent_name, key)
        return MCPToolResult(content=[MCPContent(text=json.dumps({"key": key, "deleted": True}))])

    async def _list_agent_state_keys(self, agent_name: str) -> MCPToolResult:
        """List all state keys for an agent."""
        service = AgentService(self.db)
        result = await service.list_state_keys(
            self.account.id, agent_name, self.account.user.effective_tier
        )
        return MCPToolResult(content=[MCPContent(text=json.dumps(result))])

    async def _configure_agent_ai(
        self,
        agent_name: str,
        engine: str,
        model: str,
        api_key: str | None = None,
        system_prompt: str | None = None,
        auto_channel: str | None = None,
    ) -> MCPToolResult:
        """Configure an AI engine for an agent."""
        from mcpworks_api.services.agent_service import _UNSET

        if not api_key:
            svc = AgentService(self.db)
            agent_check = await svc.get_agent(self.account.id, agent_name)
            if not agent_check.ai_api_key_encrypted:
                return MCPToolResult(
                    content=[
                        MCPContent(
                            text=json.dumps(
                                {
                                    "error": "api_key is required when configuring AI for the first time (no existing key found)"
                                }
                            )
                        )
                    ],
                    isError=True,
                )

        service = AgentService(self.db)
        try:
            agent = await service.configure_ai(
                account_id=self.account.id,
                agent_name=agent_name,
                engine=engine,
                model=model,
                api_key=api_key,
                system_prompt=system_prompt if system_prompt is not None else _UNSET,
                auto_channel=auto_channel if auto_channel is not None else _UNSET,
            )
        except ValueError as e:
            return MCPToolResult(
                content=[MCPContent(text=json.dumps({"error": str(e)}))],
                isError=True,
            )
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "agent_name": agent_name,
                            "engine": agent.ai_engine,
                            "model": agent.ai_model,
                            "system_prompt": agent.system_prompt,
                            "auto_channel": agent.auto_channel,
                            "configured": True,
                        }
                    )
                )
            ]
        )

    async def _remove_agent_ai(self, agent_name: str) -> MCPToolResult:
        """Remove AI engine configuration from an agent."""
        service = AgentService(self.db)
        await service.remove_ai(self.account.id, agent_name)
        return MCPToolResult(
            content=[MCPContent(text=json.dumps({"agent_name": agent_name, "ai_removed": True}))]
        )

    async def _configure_mcp_servers(
        self,
        agent_name: str,
        servers: dict,
    ) -> MCPToolResult:
        """Configure external MCP servers for an agent."""
        service = AgentService(self.db)
        agent = await service.configure_mcp_servers(
            account_id=self.account.id,
            agent_name=agent_name,
            servers=servers,
        )
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "agent_name": agent_name,
                            "mcp_servers": agent.mcp_servers or {},
                            "count": len(agent.mcp_servers or {}),
                            "configured": True,
                        }
                    )
                )
            ]
        )

    async def _configure_orchestration_limits(
        self,
        agent_name: str,
        max_iterations: int | None = None,
        max_ai_tokens: int | None = None,
        max_execution_seconds: int | None = None,
        max_functions_called: int | None = None,
    ) -> MCPToolResult:
        """Set custom orchestration limits for an agent."""
        from mcpworks_api.tasks.orchestrator import resolve_orchestration_limits

        service = AgentService(self.db)
        agent = await service.get_agent(self.account.id, agent_name)

        overrides: dict[str, int] = {}
        if max_iterations is not None:
            overrides["max_iterations"] = max_iterations
        if max_ai_tokens is not None:
            overrides["max_ai_tokens"] = max_ai_tokens
        if max_execution_seconds is not None:
            overrides["max_execution_seconds"] = max_execution_seconds
        if max_functions_called is not None:
            overrides["max_functions_called"] = max_functions_called

        agent.orchestration_limits = overrides if overrides else None

        tier = self.account.user.effective_tier
        effective = resolve_orchestration_limits(tier, agent)

        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "agent_name": agent_name,
                            "overrides": overrides or None,
                            "effective_limits": effective,
                            "source": "custom" if overrides else "tier_default",
                        }
                    )
                )
            ]
        )

    async def _configure_heartbeat(
        self,
        agent_name: str,
        enabled: bool,
        interval_seconds: int | None = None,
    ) -> MCPToolResult:
        """Enable or disable heartbeat mode for an agent."""
        from mcpworks_api.models.subscription import AGENT_TIER_CONFIG

        service = AgentService(self.db)
        agent = await service.get_agent(self.account.id, agent_name)

        if enabled and not agent.ai_engine:
            raise ForbiddenError("Heartbeat requires an AI engine. Use configure_agent_ai first.")

        tier = self.account.user.effective_tier
        tier_config = AGENT_TIER_CONFIG.get(tier, {})
        min_interval = tier_config.get("min_schedule_seconds", 30)

        if enabled:
            interval = interval_seconds or 300
            if interval < min_interval:
                raise ForbiddenError(
                    f"Heartbeat interval {interval}s is below tier minimum ({min_interval}s)"
                )
            agent.heartbeat_enabled = True
            agent.heartbeat_interval = interval
            from datetime import UTC, datetime, timedelta

            agent.heartbeat_next_at = datetime.now(UTC) + timedelta(seconds=interval)
        else:
            agent.heartbeat_enabled = False
            agent.heartbeat_next_at = None

        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "agent_name": agent_name,
                            "heartbeat_enabled": agent.heartbeat_enabled,
                            "heartbeat_interval": agent.heartbeat_interval,
                            "heartbeat_next_at": agent.heartbeat_next_at.isoformat()
                            if agent.heartbeat_next_at
                            else None,
                        }
                    )
                )
            ]
        )

    async def _chat_with_agent(self, agent_name: str, message: str) -> MCPToolResult:
        """Send a message to an agent's AI and return its response."""
        from mcpworks_api.core.ai_client import AIClientError

        service = AgentService(self.db)
        try:
            response = await service.chat_with_agent(
                account_id=self.account.id,
                agent_name=agent_name,
                message=message,
                account=self.account,
            )
        except AIClientError as exc:
            return MCPToolResult(content=[MCPContent(text=json.dumps({"error": str(exc)}))])
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "agent_name": agent_name,
                            "response": response,
                        }
                    )
                )
            ]
        )

    async def _add_channel(
        self,
        agent_name: str,
        channel_type: str,
        config: dict,
    ) -> MCPToolResult:
        """Add a communication channel to an agent."""
        service = AgentService(self.db)
        channel = await service.add_channel(
            account_id=self.account.id,
            agent_name=agent_name,
            channel_type=channel_type,
            config=config,
        )
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "channel_id": str(channel.id),
                            "agent_name": agent_name,
                            "channel_type": channel_type,
                            "enabled": channel.enabled,
                        }
                    )
                )
            ]
        )

    async def _remove_channel(self, agent_name: str, channel_type: str) -> MCPToolResult:
        """Remove a communication channel from an agent."""
        service = AgentService(self.db)
        await service.remove_channel(self.account.id, agent_name, channel_type)
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {"agent_name": agent_name, "channel_type": channel_type, "removed": True}
                    )
                )
            ]
        )

    async def _clone_agent(self, agent_name: str, new_name: str) -> MCPToolResult:
        """Clone an agent."""
        service = AgentService(self.db)
        new_agent = await service.clone_agent(
            account_id=self.account.id,
            source_agent_name=agent_name,
            new_name=new_name,
            tier=self.account.user.effective_tier,
        )
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "id": str(new_agent.id),
                            "name": new_agent.name,
                            "status": new_agent.status,
                            "cloned_from": agent_name,
                        }
                    )
                )
            ]
        )

    async def _lock_function(self, namespace: str, service: str, function: str) -> MCPToolResult:
        """Lock a function (admin only)."""
        from mcpworks_api.services.namespace import NamespaceServiceManager, NamespaceServiceService

        ns_manager = NamespaceServiceManager(self.db)
        svc_service = NamespaceServiceService(self.db)

        ns = await ns_manager.get_by_name(namespace)
        svc = await svc_service.get_by_name(ns.id, service)
        fn = await self.function_service.get_by_name(svc.id, function)
        await self.function_service.lock_function(fn.id, self.account.user_id)
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "namespace": namespace,
                            "service": service,
                            "function": function,
                            "locked": True,
                        }
                    )
                )
            ]
        )

    async def _unlock_function(self, namespace: str, service: str, function: str) -> MCPToolResult:
        """Unlock a function (admin only)."""
        from mcpworks_api.services.namespace import NamespaceServiceManager, NamespaceServiceService

        ns_manager = NamespaceServiceManager(self.db)
        svc_service = NamespaceServiceService(self.db)

        ns = await ns_manager.get_by_name(namespace)
        svc = await svc_service.get_by_name(ns.id, service)
        fn = await self.function_service.get_by_name(svc.id, function)
        await self.function_service.unlock_function(fn.id)
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
                            "namespace": namespace,
                            "service": service,
                            "function": function,
                            "locked": False,
                        }
                    )
                )
            ]
        )

    async def _publish_view(
        self, agent_name: str, files: dict[str, str], mode: str = "replace"
    ) -> MCPToolResult:
        """Publish HTML/JS/CSS to agent's visual scratchpad."""
        from mcpworks_api.services.scratchpad import (
            ScratchpadNotAvailable,
            ScratchpadQuotaExceeded,
            ScratchpadService,
            ScratchpadValidationError,
        )

        service = AgentService(self.db)
        agent = await service.get_agent(self.account.id, agent_name)
        scratchpad = ScratchpadService(self.db)
        tier = self.account.user.effective_tier

        try:
            result = await scratchpad.publish(agent, files, mode, tier)
        except ScratchpadNotAvailable as e:
            return MCPToolResult(
                content=[
                    MCPContent(
                        text=json.dumps({"error": "SCRATCHPAD_NOT_AVAILABLE", "message": str(e)})
                    )
                ],
                isError=True,
            )
        except ScratchpadQuotaExceeded as e:
            return MCPToolResult(
                content=[
                    MCPContent(
                        text=json.dumps(
                            {
                                "error": "SCRATCHPAD_QUOTA_EXCEEDED",
                                "current_bytes": e.current_bytes,
                                "limit_bytes": e.limit_bytes,
                                "requested_bytes": e.requested_bytes,
                            }
                        )
                    )
                ],
                isError=True,
            )
        except ScratchpadValidationError as e:
            return MCPToolResult(
                content=[
                    MCPContent(text=json.dumps({"error": "VALIDATION_ERROR", "message": str(e)}))
                ],
                isError=True,
            )

        return MCPToolResult(content=[MCPContent(text=json.dumps(result))])

    async def _get_view_url(self, agent_name: str) -> MCPToolResult:
        """Get the agent's scratchpad view URL."""
        from mcpworks_api.services.scratchpad import ScratchpadService

        service = AgentService(self.db)
        agent = await service.get_agent(self.account.id, agent_name)
        scratchpad = ScratchpadService(self.db)
        result = await scratchpad.get_url(agent)
        return MCPToolResult(content=[MCPContent(text=json.dumps(result))])

    async def _clear_view(self, agent_name: str) -> MCPToolResult:
        """Clear all files from agent's scratchpad."""
        from mcpworks_api.services.scratchpad import ScratchpadService

        service = AgentService(self.db)
        agent = await service.get_agent(self.account.id, agent_name)
        scratchpad = ScratchpadService(self.db)
        await scratchpad.clear(agent)
        return MCPToolResult(content=[MCPContent(text=json.dumps({"status": "cleared"}))])

    async def _configure_chat_token(self, agent_name: str, action: str) -> MCPToolResult:
        """Generate or revoke a public chat token for an agent."""
        service = AgentService(self.db)
        if action == "generate":
            result = await service.generate_chat_token(self.account.id, agent_name)
            return MCPToolResult(content=[MCPContent(text=json.dumps(result))])
        elif action == "revoke":
            await service.revoke_chat_token(self.account.id, agent_name)
            return MCPToolResult(
                content=[MCPContent(text=json.dumps({"status": "revoked", "chat_url": None}))]
            )
        else:
            return MCPToolResult(
                content=[
                    MCPContent(text=json.dumps({"error": "action must be 'generate' or 'revoke'"}))
                ]
            )

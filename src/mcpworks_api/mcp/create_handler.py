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

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.backends.sandbox import TIER_CONFIG, resolve_execution_tier
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
from mcpworks_api.services.agent_service import AgentService
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
        "chat_with_agent": "read",
        "add_channel": "write",
        "remove_channel": "write",
        "clone_agent": "write",
        "lock_function": "write",
        "unlock_function": "write",
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
        """Return static list of management tools with tier-aware descriptions."""
        tier_notice = self._tier_notice()
        tools = [
            MCPTool(
                name="make_namespace",
                description=(
                    "Create a new namespace for organizing services and functions. "
                    "A namespace is the top-level container — you must have one before creating services or functions. "
                    "Your current namespace is already set by the MCP server connection URL."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Namespace name (lowercase, alphanumeric, hyphens, 1-63 chars). Example: 'my-project'",
                            "pattern": "^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional human-readable description of what this namespace is for",
                        },
                    },
                    "required": ["name"],
                },
            ),
            MCPTool(
                name="list_namespaces",
                description="List all namespaces owned by or shared with the current account. Returns namespace names and descriptions.",
                inputSchema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="make_service",
                description=(
                    "Create a new service within the current namespace. "
                    "A service is a group of related functions. You must create a service before creating functions. "
                    "The service is automatically created in the namespace this MCP server is connected to — do NOT pass a namespace parameter. "
                    "Example workflow: make_service(name='utils') → make_function(service='utils', name='hello', ...)"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Service name (lowercase, alphanumeric, hyphens). Example: 'utils', 'data-tools', 'api-helpers'",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional description of what this service does",
                        },
                    },
                    "required": ["name"],
                },
            ),
            MCPTool(
                name="list_services",
                description=(
                    "List all services in the current namespace. "
                    "Returns service names, descriptions, and function counts. "
                    "Use this to discover existing services before creating functions."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="delete_service",
                description="Permanently delete a service and ALL its functions. This cannot be undone.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Service name to delete (must exist in current namespace)",
                        },
                    },
                    "required": ["name"],
                },
            ),
            MCPTool(
                name="make_function",
                description=(
                    "Create a new function in an existing service. The service must already exist (use make_service first). "
                    + tier_notice
                    + "\n\nWorkflow: 1) make_service if needed → 2) make_function with service name → 3) execute via run server. "
                    "The 'service' parameter is just the service name (e.g. 'utils'), NOT a namespace or fully-qualified path."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Name of an existing service in the current namespace. Must be created first with make_service. Example: 'utils'",
                        },
                        "name": {
                            "type": "string",
                            "description": "Function name (lowercase, alphanumeric, hyphens). Example: 'hello', 'process-data'",
                        },
                        "backend": {
                            "type": "string",
                            "enum": ["code_sandbox", "activepieces", "nanobot", "github_repo"],
                            "description": "Execution backend. Use 'code_sandbox' for Python functions (most common).",
                        },
                        "code": {
                            "type": "string",
                            "description": (
                                "Python source code for code_sandbox backend. "
                                "Entry point patterns (in priority order): "
                                "1) 'result = ...' — assign to result variable. "
                                "2) 'output = ...' — alias for result. "
                                "3) 'def main(input):' — function receiving input dict, return value is the result. "
                                "4) 'def handler(input, context):' — function receiving input dict and context dict. "
                                "The input dict contains the caller's arguments. Example: "
                                "def main(input):\\n    name = input.get('name', 'World')\\n    return {'greeting': f'Hello, {name}!'}"
                            ),
                        },
                        "config": {
                            "type": "object",
                            "description": "Backend-specific configuration (not needed for code_sandbox)",
                        },
                        "input_schema": {
                            "type": "object",
                            "description": (
                                "JSON Schema defining the function's input parameters. "
                                "IMPORTANT: Only parameters defined here will be passed to the function when called. "
                                "If you add a new parameter to the code, you must also add it to input_schema. "
                                'Example: {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}'
                            ),
                        },
                        "output_schema": {
                            "type": "object",
                            "description": "JSON Schema defining the expected output format (optional, for documentation)",
                        },
                        "description": {
                            "type": "string",
                            "description": "Human-readable description of what this function does",
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "requirements": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Python packages needed (must be from the allowed list). Use list_packages to see what's available. Example: ['httpx', 'beautifulsoup4']",
                        },
                        "required_env": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Environment variables that MUST be provided for the function to run. The caller provides these via X-MCPWorks-Env header. Example: ['OPENAI_API_KEY']",
                        },
                        "optional_env": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Environment variables the function can optionally use if provided.",
                        },
                        "created_by": {
                            "type": "string",
                            "description": "Attribution for who created this function. Example: 'Claude Opus 4.6', 'GPT-4o'",
                        },
                        "template": {
                            "type": "string",
                            "description": "Start from a template instead of writing code. Overrides code/schemas/requirements. Use list_templates to see available templates.",
                        },
                    },
                    "required": ["service", "name", "backend"],
                },
            ),
            MCPTool(
                name="update_function",
                description=(
                    "Update an existing function, creating a new version. "
                    "Each update creates a new version — previous versions are preserved and can be restored. "
                    "Only provide the fields you want to change. "
                    "To restore a previous version, use restore_version with the version number."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name containing the function",
                        },
                        "name": {
                            "type": "string",
                            "description": "Function name to update",
                        },
                        "backend": {"type": "string"},
                        "code": {
                            "type": "string",
                            "description": "New Python code. Same entry point rules as make_function.",
                        },
                        "config": {"type": "object"},
                        "input_schema": {
                            "type": "object",
                            "description": "Updated input schema. Remember: only parameters defined here are passed to the function.",
                        },
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
                            "description": "Attribution for who made this update.",
                        },
                        "restore_version": {
                            "type": "integer",
                            "description": "Restore code and config from a previous version number. Use describe_function to see version history.",
                        },
                    },
                    "required": ["service", "name"],
                },
            ),
            MCPTool(
                name="delete_function",
                description="Permanently delete a function and all its versions. This cannot be undone.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name containing the function",
                        },
                        "name": {
                            "type": "string",
                            "description": "Function name to delete",
                        },
                    },
                    "required": ["service", "name"],
                },
            ),
            MCPTool(
                name="list_functions",
                description=(
                    "List all functions in a service. "
                    "Returns function names, descriptions, versions, tags, and call counts. "
                    "The 'service' parameter is just the service name — use list_services first to see available services."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name to list functions from. Use list_services to see available services.",
                        },
                        "tag": {
                            "type": "string",
                            "description": "Optional: filter functions by tag",
                        },
                    },
                    "required": ["service"],
                },
            ),
            MCPTool(
                name="describe_function",
                description=(
                    "Get detailed information about a function including its current code, "
                    "input/output schemas, requirements, environment variables, and full version history."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name containing the function",
                        },
                        "name": {
                            "type": "string",
                            "description": "Function name to describe",
                        },
                    },
                    "required": ["service", "name"],
                },
            ),
            MCPTool(
                name="list_packages",
                description=(
                    "List all Python packages available for use in sandbox functions, grouped by category. "
                    "Only packages from this list can be used in the 'requirements' field of make_function/update_function."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            MCPTool(
                name="list_templates",
                description="List available function templates for quick-start. Templates provide pre-built code, schemas, and requirements.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            MCPTool(
                name="describe_template",
                description="Get full template details including source code, input/output schemas, and required packages. Use this before cloning a template with make_function.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Template name (e.g. 'hello-world', 'csv-analyzer'). Use list_templates to see available templates.",
                        },
                    },
                    "required": ["name"],
                },
            ),
        ]

        agent_tiers = ("builder-agent", "pro-agent", "enterprise-agent")
        if self.account.user.effective_tier in agent_tiers:
            tools += [
                MCPTool(
                    name="make_agent",
                    description=(
                        "Create a new autonomous agent. "
                        "An agent is a container that groups functions, schedules, webhooks, channels, and AI config together. "
                        "After creating an agent, use make_service and make_function to add capabilities, "
                        "then configure_agent_ai to give it an AI brain, add_schedule for cron jobs, "
                        "add_webhook for HTTP triggers, and add_channel for messaging integrations."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Agent name (lowercase, alphanumeric, hyphens). This becomes the agent's namespace.",
                            },
                            "display_name": {
                                "type": "string",
                                "description": "Human-readable display name. Example: 'Social Media Bot'",
                            },
                        },
                        "required": ["name"],
                    },
                ),
                MCPTool(
                    name="list_agents",
                    description="List all agents for the current account. Returns agent names, display names, status (running/stopped), and slot usage.",
                    inputSchema={"type": "object", "properties": {}},
                ),
                MCPTool(
                    name="describe_agent",
                    description="Get full details for an agent including status, AI engine config, resource limits, and creation date.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Agent name",
                            },
                        },
                        "required": ["name"],
                    },
                ),
                MCPTool(
                    name="start_agent",
                    description="Start a stopped agent. The agent must exist and be in 'stopped' status.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Agent name to start",
                            },
                        },
                        "required": ["name"],
                    },
                ),
                MCPTool(
                    name="stop_agent",
                    description="Stop a running agent. Pauses scheduled tasks and webhook processing. The agent can be restarted with start_agent.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Agent name to stop",
                            },
                        },
                        "required": ["name"],
                    },
                ),
                MCPTool(
                    name="destroy_agent",
                    description="Permanently destroy an agent and ALL its data (state, schedules, webhooks, channels). This cannot be undone.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Agent name to destroy",
                            },
                            "confirm": {
                                "type": "boolean",
                                "description": "Must be true to confirm destruction. Safety check to prevent accidental deletion.",
                            },
                        },
                        "required": ["name", "confirm"],
                    },
                ),
                MCPTool(
                    name="add_schedule",
                    description=(
                        "Add a cron schedule to an agent. The schedule will periodically execute the specified function. "
                        "The function must exist in the agent's namespace (format: 'service.function'). "
                        "Use orchestration_mode to control AI involvement: 'direct' (default) runs the function, "
                        "'reason_first' sends the trigger to the AI and lets it decide what to do, "
                        "'run_then_reason' runs the function first then passes output to the AI for analysis."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                            "function_name": {
                                "type": "string",
                                "description": "Function to call, in 'service.function' format. Example: 'utils.check-status'. The function must already exist.",
                            },
                            "cron_expression": {
                                "type": "string",
                                "description": "Standard cron expression. Examples: '0 * * * *' (hourly), '*/5 * * * *' (every 5 min), '0 9 * * 1-5' (weekdays at 9am)",
                            },
                            "timezone": {
                                "type": "string",
                                "description": "IANA timezone for schedule. Default: UTC. Example: 'America/New_York'",
                                "default": "UTC",
                            },
                            "failure_policy": {
                                "type": "object",
                                "description": 'What to do when the function fails. Required. Options: {"strategy": "continue"} (keep running), {"strategy": "auto_disable", "max_failures": 5} (disable after N failures), {"strategy": "backoff", "backoff_factor": 2.0} (exponential backoff)',
                            },
                            "orchestration_mode": {
                                "type": "string",
                                "enum": ["direct", "reason_first", "run_then_reason"],
                                "description": (
                                    "How the schedule interacts with the agent's AI engine. "
                                    "'direct' (default): execute function without AI. "
                                    "'reason_first': send trigger to AI, let it decide which functions to call. "
                                    "'run_then_reason': execute function first, pass output to AI for analysis."
                                ),
                                "default": "direct",
                            },
                        },
                        "required": [
                            "agent_name",
                            "function_name",
                            "cron_expression",
                            "failure_policy",
                        ],
                    },
                ),
                MCPTool(
                    name="remove_schedule",
                    description="Remove a cron schedule from an agent. Use list_schedules to find the schedule_id.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                            "schedule_id": {
                                "type": "string",
                                "description": "Schedule UUID (from list_schedules or add_schedule response)",
                            },
                        },
                        "required": ["agent_name", "schedule_id"],
                    },
                ),
                MCPTool(
                    name="list_schedules",
                    description="List all cron schedules for an agent. Returns schedule IDs, function names, cron expressions, and failure counts.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                        },
                        "required": ["agent_name"],
                    },
                ),
                MCPTool(
                    name="add_webhook",
                    description=(
                        "Add a webhook endpoint to an agent. "
                        "When the webhook URL receives an HTTP POST, it triggers the specified handler function. "
                        "The webhook URL will be: https://{agent_name}.agent.mcpworks.io/webhook/{path}"
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                            "path": {
                                "type": "string",
                                "description": "Webhook path segment. Example: 'github/push' creates URL https://{agent}.agent.mcpworks.io/webhook/github/push",
                            },
                            "handler_function_name": {
                                "type": "string",
                                "description": "Function to call when webhook fires, in 'service.function' format. Example: 'hooks.handle-push'",
                            },
                            "secret": {
                                "type": "string",
                                "description": "Optional HMAC secret for webhook signature verification",
                            },
                            "orchestration_mode": {
                                "type": "string",
                                "enum": ["direct", "reason_first", "run_then_reason"],
                                "description": (
                                    "How the webhook interacts with the agent's AI engine. "
                                    "'direct' (default): execute handler function without AI. "
                                    "'reason_first': send webhook payload to AI, let it decide which functions to call. "
                                    "'run_then_reason': execute handler first, pass output to AI for analysis."
                                ),
                                "default": "direct",
                            },
                        },
                        "required": ["agent_name", "path", "handler_function_name"],
                    },
                ),
                MCPTool(
                    name="remove_webhook",
                    description="Remove a webhook from an agent. Use list_webhooks to find the webhook_id.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                            "webhook_id": {
                                "type": "string",
                                "description": "Webhook UUID (from list_webhooks or add_webhook response)",
                            },
                        },
                        "required": ["agent_name", "webhook_id"],
                    },
                ),
                MCPTool(
                    name="list_webhooks",
                    description="List all webhooks for an agent. Returns webhook IDs, paths, handler functions, and enabled status.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                        },
                        "required": ["agent_name"],
                    },
                ),
                MCPTool(
                    name="set_agent_state",
                    description=(
                        "Store a persistent key-value pair for an agent. "
                        "State survives agent restarts and can be read by the agent's functions. "
                        "Values can be any JSON type (string, number, boolean, object, array)."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                            "key": {
                                "type": "string",
                                "description": "State key. Example: 'last_run', 'config', 'user_prefs'",
                            },
                            "value": {
                                "description": "Value to store. Any JSON type: string, number, boolean, object, or array."
                            },
                        },
                        "required": ["agent_name", "key", "value"],
                    },
                ),
                MCPTool(
                    name="get_agent_state",
                    description="Retrieve a stored state value for an agent by key.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                            "key": {"type": "string", "description": "State key to retrieve"},
                        },
                        "required": ["agent_name", "key"],
                    },
                ),
                MCPTool(
                    name="delete_agent_state",
                    description="Delete a stored state key for an agent. The key and its value are permanently removed.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                            "key": {"type": "string", "description": "State key to delete"},
                        },
                        "required": ["agent_name", "key"],
                    },
                ),
                MCPTool(
                    name="list_agent_state_keys",
                    description="List all stored state keys for an agent. Returns key names and total storage used.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                        },
                        "required": ["agent_name"],
                    },
                ),
                MCPTool(
                    name="configure_agent_ai",
                    description=(
                        "Configure an AI engine (LLM) for an agent. "
                        "This sets up the agent's 'brain' — the AI model it uses for orchestration (schedule/webhook with AI modes) and chat_with_agent. "
                        "When a schedule or webhook has orchestration_mode='reason_first' or 'run_then_reason', the AI can call namespace functions as tools. "
                        "NOTE: The AI API key is stored securely but is NOT passed to sandbox functions as an environment variable."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                            "engine": {
                                "type": "string",
                                "enum": ["anthropic", "openai", "google", "openrouter"],
                                "description": "AI provider. Use 'openrouter' for access to many models.",
                            },
                            "model": {
                                "type": "string",
                                "description": "Model identifier. Examples: 'claude-sonnet-4-20250514' (anthropic), 'gpt-4o' (openai), 'google/gemini-2.0-flash-exp:free' (openrouter)",
                            },
                            "api_key": {
                                "type": "string",
                                "description": "API key for the chosen engine. Stored encrypted, never exposed to sandbox functions.",
                            },
                            "system_prompt": {
                                "type": "string",
                                "description": "System prompt that defines the agent's personality and behavior for AI orchestration and chat_with_agent conversations.",
                            },
                            "auto_channel": {
                                "type": "string",
                                "enum": ["discord", "slack", "email"],
                                "description": "Automatically post the AI's final response to this channel type after orchestration runs. The channel must be configured via add_channel.",
                            },
                        },
                        "required": ["agent_name", "engine", "model", "api_key"],
                    },
                ),
                MCPTool(
                    name="remove_agent_ai",
                    description="Remove the AI engine configuration from an agent. The agent will no longer be able to respond to chat_with_agent messages.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                        },
                        "required": ["agent_name"],
                    },
                ),
                MCPTool(
                    name="configure_mcp_servers",
                    description=(
                        "Configure external MCP servers that an agent can connect to as a client. "
                        "When AI orchestration runs, the agent will connect to these servers and make their tools available alongside namespace functions. "
                        "Supports SSE, streamable_http, and stdio transports. Pass an empty servers dict to clear all."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                            "servers": {
                                "type": "object",
                                "description": "Map of server_name -> config. Each config has 'type' (sse/streamable_http/stdio), 'url' (for sse/streamable_http), 'command'+'args' (for stdio), optional 'headers'.",
                                "additionalProperties": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": ["sse", "streamable_http", "stdio"],
                                        },
                                        "url": {"type": "string"},
                                        "command": {"type": "string"},
                                        "args": {"type": "array", "items": {"type": "string"}},
                                        "headers": {
                                            "type": "object",
                                            "additionalProperties": {"type": "string"},
                                        },
                                    },
                                    "required": ["type"],
                                },
                            },
                        },
                        "required": ["agent_name", "servers"],
                    },
                ),
                MCPTool(
                    name="chat_with_agent",
                    description=(
                        "Send a message to an agent's AI engine and get its response. "
                        "The agent must have an AI engine configured (use configure_agent_ai first). "
                        "Use this to talk to the agent, test its behavior, or ask it to suggest changes to its own configuration."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {
                                "type": "string",
                                "description": "Agent name (must have AI engine configured)",
                            },
                            "message": {
                                "type": "string",
                                "description": "Message to send to the agent's AI engine",
                            },
                        },
                        "required": ["agent_name", "message"],
                    },
                ),
                MCPTool(
                    name="add_channel",
                    description=(
                        "Add a communication channel to an agent. "
                        "Channels allow the agent to send and receive messages on external platforms. "
                        "Each channel type requires specific config keys (e.g., discord needs bot_token and guild_id)."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                            "channel_type": {
                                "type": "string",
                                "enum": ["discord", "slack", "whatsapp", "email"],
                                "description": "Platform type",
                            },
                            "config": {
                                "type": "object",
                                "description": 'Channel-specific config. Discord: {"bot_token": "...", "guild_id": "..."}. Slack: {"bot_token": "...", "channel_id": "..."}. Email: {"smtp_host": "...", "from": "..."}.',
                            },
                        },
                        "required": ["agent_name", "channel_type", "config"],
                    },
                ),
                MCPTool(
                    name="remove_channel",
                    description="Remove a communication channel from an agent by its type (discord, slack, etc.).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Agent name"},
                            "channel_type": {
                                "type": "string",
                                "description": "Channel type to remove: 'discord', 'slack', 'whatsapp', or 'email'",
                            },
                        },
                        "required": ["agent_name", "channel_type"],
                    },
                ),
                MCPTool(
                    name="clone_agent",
                    description="Clone an agent with state, schedules, and channels",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Source agent name"},
                            "new_name": {"type": "string", "description": "New agent name"},
                        },
                        "required": ["agent_name", "new_name"],
                    },
                ),
                MCPTool(
                    name="lock_function",
                    description="Lock a function to prevent modification (admin only)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "namespace": {"type": "string"},
                            "service": {"type": "string"},
                            "function": {"type": "string"},
                        },
                        "required": ["namespace", "service", "function"],
                    },
                ),
                MCPTool(
                    name="unlock_function",
                    description="Unlock a function to allow modification (admin only)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "namespace": {"type": "string"},
                            "service": {"type": "string"},
                            "function": {"type": "string"},
                        },
                        "required": ["namespace", "service", "function"],
                    },
                ),
            ]

        return tools

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
            "chat_with_agent": self._chat_with_agent,
            "add_channel": self._add_channel,
            "remove_channel": self._remove_channel,
            "clone_agent": self._clone_agent,
            "lock_function": self._lock_function,
            "unlock_function": self._unlock_function,
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
        return MCPToolResult(
            content=[
                MCPContent(
                    text=json.dumps(
                        {
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
                    )
                )
            ]
        )

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
        api_key: str,
        system_prompt: str | None = None,
        auto_channel: str | None = None,
    ) -> MCPToolResult:
        """Configure an AI engine for an agent."""
        service = AgentService(self.db)
        agent = await service.configure_ai(
            account_id=self.account.id,
            agent_name=agent_name,
            engine=engine,
            model=model,
            api_key=api_key,
            system_prompt=system_prompt,
            auto_channel=auto_channel,
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

    async def _chat_with_agent(self, agent_name: str, message: str) -> MCPToolResult:
        """Send a message to an agent's AI and return its response."""
        from mcpworks_api.core.ai_client import AIClientError

        service = AgentService(self.db)
        try:
            response = await service.chat_with_agent(
                account_id=self.account.id,
                agent_name=agent_name,
                message=message,
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

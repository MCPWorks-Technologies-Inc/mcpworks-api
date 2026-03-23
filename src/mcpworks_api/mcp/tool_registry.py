"""Centralized MCP tool definitions registry.

All tool names, descriptions, and schemas live here — not inline in handlers.
This enables:
- Consistent auditing of tool clarity
- Verbosity control (brief vs standard vs detailed descriptions)
- Single source of truth for tool documentation
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDef:
    """A tool definition that can be rendered at different verbosity levels."""

    name: str
    brief: str
    description: str
    detailed: str = ""
    input_schema: dict = field(default_factory=dict)

    def render(self, verbosity: str = "standard", **format_kwargs: str) -> dict:
        """Render as MCPTool-compatible dict.

        Args:
            verbosity: "brief", "standard", or "detailed"
            **format_kwargs: String substitutions for placeholders like {tier_notice}
        """
        if verbosity == "brief":
            desc = self.brief
        elif verbosity == "detailed":
            desc = self.description + ("\n\n" + self.detailed if self.detailed else "")
        else:
            desc = self.description
        if format_kwargs:
            for key, val in format_kwargs.items():
                desc = desc.replace("{" + key + "}", str(val))
        return {
            "name": self.name,
            "description": desc,
            "inputSchema": self.input_schema,
        }


BASE_TOOLS: dict[str, ToolDef] = {
    "make_namespace": ToolDef(
        name="make_namespace",
        brief="Create a new namespace (top-level container for services and functions).",
        description=(
            "Create a new namespace for organizing services and functions. "
            "A namespace is the top-level container — you must have one before creating services or functions. "
            "Your current namespace is already set by the MCP server connection URL."
        ),
        input_schema={
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
    "list_namespaces": ToolDef(
        name="list_namespaces",
        brief="List all namespaces owned by or shared with the current account.",
        description="List all namespaces owned by or shared with the current account. Returns namespace names and descriptions.",
        input_schema={"type": "object", "properties": {}},
    ),
    "make_service": ToolDef(
        name="make_service",
        brief="Create a new service (group of related functions) within the current namespace.",
        description=(
            "Create a new service within the current namespace. "
            "A service is a group of related functions. You must create a service before creating functions. "
            "The service is automatically created in the namespace this MCP server is connected to — do NOT pass a namespace parameter. "
            "Example: make_service(name='utils') → make_function(service='utils', name='hello', ...)"
        ),
        input_schema={
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
    "list_services": ToolDef(
        name="list_services",
        brief="List all services in the current namespace.",
        description=(
            "List all services in the current namespace. "
            "Returns service names, descriptions, and function counts. "
            "Use this to discover existing services before creating functions."
        ),
        input_schema={"type": "object", "properties": {}},
    ),
    "delete_service": ToolDef(
        name="delete_service",
        brief="Permanently delete a service and ALL its functions.",
        description="Permanently delete a service and ALL its functions. This cannot be undone.",
        input_schema={
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
    "make_function": ToolDef(
        name="make_function",
        brief="Create a new function in an existing service.",
        description=(
            "Create a new function in an existing service. The service must already exist (use make_service first). "
            "Workflow: 1) make_service if needed → 2) make_function with service name → 3) execute via run server. "
            "The 'service' parameter is just the service name (e.g. 'utils'), NOT a namespace or fully-qualified path. "
            "{tier_notice}"
        ),
        detailed=(
            "Python entry points (in priority order): "
            "1) 'result = ...' — assign to result variable. "
            "2) 'output = ...' — alias for result. "
            "3) 'def main(input):' — function receiving input dict, return value is the result. "
            "4) 'def handler(input, context):' — function receiving input dict and context dict. "
            "\n\nTypeScript entry points: "
            "1) 'export default function main(input) { ... }' — default export (preferred). "
            "2) 'export default function handler(input, context) { ... }' — with context. "
            "3) 'module.exports.main = function(input) { ... }' — CommonJS. "
            "4) 'const result = ...' — simple assignment."
            "\n\nNEVER hardcode API keys, tokens, secrets, or credentials in code — "
            "use required_env for caller-provided secrets or agent state (via context['state']) for stored secrets."
        ),
        input_schema={
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
                    "description": "Execution backend. Use 'code_sandbox' for Python and TypeScript functions.",
                },
                "language": {
                    "type": "string",
                    "enum": ["python", "typescript"],
                    "description": (
                        "Programming language for the function. Default: 'python'. "
                        "Use 'typescript' for TypeScript/JavaScript functions. "
                        "Language cannot be changed after creation."
                    ),
                },
                "code": {
                    "type": "string",
                    "description": (
                        "Source code for code_sandbox backend. "
                        "Required when backend is 'code_sandbox' (unless using template). "
                        "NEVER hardcode API keys, tokens, secrets, or credentials in code — "
                        "use required_env for caller-provided secrets or agent state (via context['state']) for stored secrets. "
                        "\n\nPython entry points (in priority order): "
                        "1) 'result = ...' — assign to result variable. "
                        "2) 'output = ...' — alias for result. "
                        "3) 'def main(input):' — function receiving input dict, return value is the result. "
                        "4) 'def handler(input, context):' — function receiving input dict and context dict. "
                        "\n\nTypeScript entry points: "
                        "1) 'export default function main(input) { ... }' — default export (preferred). "
                        "2) 'export default function handler(input, context) { ... }' — with context. "
                        "3) 'module.exports.main = function(input) { ... }' — CommonJS. "
                        "4) 'const result = ...' — simple assignment."
                    ),
                },
                "config": {
                    "type": "object",
                    "description": "Backend-specific configuration. Required for 'activepieces' backend. Not needed for 'code_sandbox'.",
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
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for categorizing the function. Example: ['data', 'utility']",
                },
                "requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Packages needed (must be from the allowed list). Use list_packages to see what's available. Python: ['httpx', 'pandas'] | TypeScript: ['axios', 'zod']",
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
                "public_safe": {
                    "type": "boolean",
                    "description": "If true, this function can be called from public chat endpoints (scratchpad chat). Default: false — functions are internal-only unless explicitly marked safe.",
                },
            },
            "required": ["service", "name", "backend"],
        },
    ),
    "update_function": ToolDef(
        name="update_function",
        brief="Update an existing function, creating a new version.",
        description=(
            "Update an existing function, creating a new version. "
            "Each update creates a new version — previous versions are preserved and can be restored. "
            "Only provide the fields you want to change. "
            "To restore a previous version, use restore_version with the version number."
        ),
        input_schema={
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
                "backend": {
                    "type": "string",
                    "enum": ["code_sandbox", "activepieces", "nanobot", "github_repo"],
                    "description": "Execution backend. Use 'code_sandbox' for Python and TypeScript functions.",
                },
                "code": {
                    "type": "string",
                    "description": "New Python code. Same entry point rules as make_function. NEVER hardcode API keys, tokens, or secrets — use required_env or agent state (context['state']) instead.",
                },
                "config": {
                    "type": "object",
                    "description": "Backend-specific configuration. Required for 'activepieces' backend. Not needed for 'code_sandbox'.",
                },
                "input_schema": {
                    "type": "object",
                    "description": "Updated input schema. Remember: only parameters defined here are passed to the function.",
                },
                "output_schema": {
                    "type": "object",
                    "description": "JSON Schema defining the expected output format (optional, for documentation)",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of what this function does",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for categorizing the function. Example: ['data', 'utility']",
                },
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
                "public_safe": {
                    "type": "boolean",
                    "description": "If true, this function can be called from public chat endpoints (scratchpad chat). Default: false.",
                },
            },
            "required": ["service", "name"],
        },
    ),
    "delete_function": ToolDef(
        name="delete_function",
        brief="Permanently delete a function and all its versions.",
        description="Permanently delete a function and all its versions. This cannot be undone.",
        input_schema={
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
    "list_functions": ToolDef(
        name="list_functions",
        brief="List all functions in a service.",
        description=(
            "List all functions in a service. "
            "Returns function names, descriptions, versions, tags, and call counts. "
            "The 'service' parameter is just the service name — use list_services first to see available services."
        ),
        input_schema={
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
    "describe_function": ToolDef(
        name="describe_function",
        brief="Get detailed information about a function including code, schemas, and version history.",
        description=(
            "Get detailed information about a function including its current code, "
            "input/output schemas, requirements, environment variables, and full version history."
        ),
        input_schema={
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
    "list_packages": ToolDef(
        name="list_packages",
        brief="List packages available for use in sandbox functions, grouped by category.",
        description=(
            "List packages available for use in sandbox functions, grouped by category. "
            "Only packages from this list can be used in the 'requirements' field of make_function/update_function. "
            "Use the 'language' parameter to filter by Python or TypeScript."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["python", "typescript"],
                    "description": "Filter packages by language. Default: python.",
                },
            },
        },
    ),
    "list_templates": ToolDef(
        name="list_templates",
        brief="List available function templates for quick-start.",
        description="List available function templates for quick-start. Templates provide pre-built code, schemas, and requirements.",
        input_schema={
            "type": "object",
            "properties": {},
        },
    ),
    "describe_template": ToolDef(
        name="describe_template",
        brief="Get full template details including source code, schemas, and required packages.",
        description="Get full template details including source code, input/output schemas, and required packages. Use this before cloning a template with make_function.",
        input_schema={
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
}


AGENT_TOOLS: dict[str, ToolDef] = {
    "make_agent": ToolDef(
        name="make_agent",
        brief="Create a new autonomous agent.",
        description=(
            "Create a new autonomous agent. "
            "An agent is a container that groups functions, schedules, webhooks, channels, and AI config together. "
            "After creating an agent, use make_service and make_function to add capabilities, "
            "then configure_agent_ai to give it an AI brain, add_schedule for cron jobs, "
            "add_webhook for HTTP triggers, and add_channel for messaging integrations."
        ),
        input_schema={
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
    "list_agents": ToolDef(
        name="list_agents",
        brief="List all agents for the current account.",
        description="List all agents for the current account. Returns agent names, display names, status (running/stopped), and slot usage.",
        input_schema={"type": "object", "properties": {}},
    ),
    "describe_agent": ToolDef(
        name="describe_agent",
        brief="Get full details for an agent including status, AI config, and resource limits.",
        description="Get full details for an agent including status, AI engine config, resource limits, and creation date.",
        input_schema={
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
    "start_agent": ToolDef(
        name="start_agent",
        brief="Start a stopped agent.",
        description="Start a stopped agent. The agent must exist and be in 'stopped' status.",
        input_schema={
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
    "stop_agent": ToolDef(
        name="stop_agent",
        brief="Stop a running agent, pausing schedules and webhook processing.",
        description="Stop a running agent. Pauses scheduled tasks and webhook processing. The agent can be restarted with start_agent.",
        input_schema={
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
    "destroy_agent": ToolDef(
        name="destroy_agent",
        brief="Permanently destroy an agent and ALL its data.",
        description="Permanently destroy an agent and ALL its data (state, schedules, webhooks, channels). This cannot be undone.",
        input_schema={
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
    "add_schedule": ToolDef(
        name="add_schedule",
        brief="Add a cron schedule to an agent that periodically executes a function.",
        description=(
            "Add a cron schedule to an agent. The schedule will periodically execute the specified function. "
            "The function must exist in the agent's namespace (format: 'service.function'). "
            "Use orchestration_mode to control AI involvement: 'direct' (default) runs the function, "
            "'reason_first' sends the trigger to the AI and lets it decide what to do, "
            "'run_then_reason' runs the function first then passes output to the AI for analysis."
        ),
        detailed=(
            "failure_policy options:\n"
            '1. Keep running despite failures: {"strategy": "continue"}\n'
            '2. Auto-disable after N failures: {"strategy": "auto_disable", "max_failures": 5}\n'
            '3. Exponential backoff on failure: {"strategy": "backoff", "backoff_factor": 2.0}\n'
            'Most common choice: {"strategy": "continue"}'
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
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
                    "description": (
                        "What to do when the scheduled function fails. "
                        "Must include a 'strategy' field. Three options:\n"
                        '1. Keep running despite failures: {"strategy": "continue"}\n'
                        '2. Auto-disable after N failures: {"strategy": "auto_disable", "max_failures": 5}\n'
                        '3. Exponential backoff on failure: {"strategy": "backoff", "backoff_factor": 2.0}\n'
                        'Most common choice: {"strategy": "continue"}'
                    ),
                    "properties": {
                        "strategy": {
                            "type": "string",
                            "enum": ["continue", "auto_disable", "backoff"],
                            "description": "Failure handling strategy",
                        },
                        "max_failures": {
                            "type": "integer",
                            "description": "Only for auto_disable: disable schedule after this many consecutive failures. Default: 5",
                        },
                        "backoff_factor": {
                            "type": "number",
                            "description": "Only for backoff: multiply delay by this factor on each failure. Default: 2.0",
                        },
                    },
                    "required": ["strategy"],
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
    "remove_schedule": ToolDef(
        name="remove_schedule",
        brief="Remove a cron schedule from an agent.",
        description="Remove a cron schedule from an agent. Use list_schedules to find the schedule_id.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
                "schedule_id": {
                    "type": "string",
                    "description": "Schedule UUID (from list_schedules or add_schedule response)",
                },
            },
            "required": ["agent_name", "schedule_id"],
        },
    ),
    "list_schedules": ToolDef(
        name="list_schedules",
        brief="List all cron schedules for an agent.",
        description="List all cron schedules for an agent. Returns schedule IDs, function names, cron expressions, and failure counts.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
            },
            "required": ["agent_name"],
        },
    ),
    "add_webhook": ToolDef(
        name="add_webhook",
        brief="Add a webhook endpoint to an agent that triggers a handler function on HTTP POST.",
        description=(
            "Add a webhook endpoint to an agent. "
            "When the webhook URL receives an HTTP POST, it triggers the specified handler function. "
            "The webhook URL will be: https://{agent_name}.agent.mcpworks.io/webhook/{path}"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
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
    "remove_webhook": ToolDef(
        name="remove_webhook",
        brief="Remove a webhook from an agent.",
        description="Remove a webhook from an agent. Use list_webhooks to find the webhook_id.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
                "webhook_id": {
                    "type": "string",
                    "description": "Webhook UUID (from list_webhooks or add_webhook response)",
                },
            },
            "required": ["agent_name", "webhook_id"],
        },
    ),
    "list_webhooks": ToolDef(
        name="list_webhooks",
        brief="List all webhooks for an agent.",
        description="List all webhooks for an agent. Returns webhook IDs, paths, handler functions, and enabled status.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
            },
            "required": ["agent_name"],
        },
    ),
    "set_agent_state": ToolDef(
        name="set_agent_state",
        brief="Store a persistent key-value pair for an agent.",
        description=(
            "Store a persistent key-value pair for an agent. "
            "State survives agent restarts and can be read by the agent's functions. "
            "Values can be any JSON type (string, number, boolean, object, array)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
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
    "get_agent_state": ToolDef(
        name="get_agent_state",
        brief="Retrieve a stored state value for an agent by key.",
        description="Retrieve a stored state value for an agent by key.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
                "key": {
                    "type": "string",
                    "description": "State key to retrieve",
                },
            },
            "required": ["agent_name", "key"],
        },
    ),
    "delete_agent_state": ToolDef(
        name="delete_agent_state",
        brief="Delete a stored state key for an agent.",
        description="Delete a stored state key for an agent. The key and its value are permanently removed.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
                "key": {
                    "type": "string",
                    "description": "State key to delete",
                },
            },
            "required": ["agent_name", "key"],
        },
    ),
    "list_agent_state_keys": ToolDef(
        name="list_agent_state_keys",
        brief="List all stored state keys for an agent.",
        description="List all stored state keys for an agent. Returns key names and total storage used.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
            },
            "required": ["agent_name"],
        },
    ),
    "configure_agent_ai": ToolDef(
        name="configure_agent_ai",
        brief="Configure an AI engine (LLM) for an agent's orchestration and chat.",
        description=(
            "Configure an AI engine (LLM) for an agent. "
            "This sets up the agent's 'brain' — the AI model it uses for orchestration (schedule/webhook with AI modes) and chat_with_agent. "
            "When a schedule or webhook has orchestration_mode='reason_first' or 'run_then_reason', the AI can call namespace functions as tools. "
            "NOTE: The AI API key is stored securely but is NOT passed to sandbox functions as an environment variable."
        ),
        detailed=(
            "Supported engines and example models:\n"
            "- anthropic: 'claude-sonnet-4-20250514', 'claude-haiku-3-5-20241022'\n"
            "- openai: 'gpt-4o', 'gpt-4o-mini'\n"
            "- google: 'gemini-2.0-flash-exp'\n"
            "- openrouter: 'google/gemini-2.0-flash-exp:free', 'meta-llama/llama-3.1-70b-instruct'\n\n"
            "Use openrouter for access to many models with a single API key."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
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
                    "description": "API key for the chosen engine. Optional if the agent already has a key configured — omit to keep the existing key. Only provide when setting up AI for the first time or rotating the key.",
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
            "required": ["agent_name", "engine", "model"],
        },
    ),
    "remove_agent_ai": ToolDef(
        name="remove_agent_ai",
        brief="Remove the AI engine configuration from an agent.",
        description="Remove the AI engine configuration from an agent. The agent will no longer be able to respond to chat_with_agent messages.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
            },
            "required": ["agent_name"],
        },
    ),
    "configure_mcp_servers": ToolDef(
        name="configure_mcp_servers",
        brief="Configure external MCP servers that an agent connects to as a client during AI orchestration.",
        description=(
            "Configure external MCP servers that an agent can connect to as a client. "
            "When AI orchestration runs, the agent will connect to these servers and make their tools available alongside namespace functions. "
            "Supports SSE, streamable_http, and stdio transports. Pass an empty servers dict to clear all.\n\n"
            'Example servers object: {"my-tool": {"type": "sse", "url": "https://example.com/mcp", "headers": {"Authorization": "Bearer token"}}}'
        ),
        detailed=(
            "Transport types:\n"
            "- sse: Server-Sent Events. Requires 'url'. Optional 'headers' dict.\n"
            "- streamable_http: HTTP streaming. Requires 'url'. Optional 'headers' dict.\n"
            "- stdio: Local process. Requires 'command' and 'args' list.\n\n"
            "Examples:\n"
            '  SSE:  {"type": "sse", "url": "https://example.com/mcp"}\n'
            '  HTTP: {"type": "streamable_http", "url": "https://example.com/mcp", "headers": {"Authorization": "Bearer sk-..."}}\n'
            '  stdio: {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]}'
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
                "servers": {
                    "type": "object",
                    "description": (
                        "Map of server_name -> config. Each config has 'type' (sse/streamable_http/stdio), "
                        "'url' (for sse/streamable_http), 'command'+'args' (for stdio), optional 'headers'. "
                        'Example: {"my-tool": {"type": "sse", "url": "https://example.com/mcp", "headers": {"Authorization": "Bearer token"}}}'
                    ),
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["sse", "streamable_http", "stdio"],
                                "description": "Transport type: 'sse' or 'streamable_http' for URL-based servers, 'stdio' for local process",
                            },
                            "url": {
                                "type": "string",
                                "description": "Server URL (required for sse and streamable_http transports)",
                            },
                            "command": {
                                "type": "string",
                                "description": "Process command (required for stdio transport). Example: 'npx'",
                            },
                            "args": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Process arguments (for stdio transport). Example: ['-y', '@modelcontextprotocol/server-filesystem', '/tmp']",
                            },
                            "headers": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                                "description": "Optional HTTP headers (for sse/streamable_http). Example: {'Authorization': 'Bearer sk-...'}",
                            },
                        },
                        "required": ["type"],
                    },
                },
            },
            "required": ["agent_name", "servers"],
        },
    ),
    "configure_orchestration_limits": ToolDef(
        name="configure_orchestration_limits",
        brief="Set custom orchestration limits for an agent, overriding tier defaults.",
        description=(
            "Set custom orchestration limits for an agent, overriding tier defaults. "
            "Useful for agents that need more AI reasoning power (higher iterations/tokens) or tighter constraints. "
            "Omit any field to keep the tier default for that limit. "
            "Call with no optional fields to reset all limits to tier defaults."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Max AI reasoning loops per orchestration run (1-200). Tier default varies by plan.",
                    "minimum": 1,
                    "maximum": 200,
                },
                "max_ai_tokens": {
                    "type": "integer",
                    "description": "Max LLM tokens consumed per orchestration run (1000-10000000). Controls BYOAI cost.",
                    "minimum": 1000,
                    "maximum": 10000000,
                },
                "max_execution_seconds": {
                    "type": "integer",
                    "description": "Max wall-clock time for orchestration run (10-3600).",
                    "minimum": 10,
                    "maximum": 3600,
                },
                "max_functions_called": {
                    "type": "integer",
                    "description": "Max function calls per orchestration run (1-500).",
                    "minimum": 1,
                    "maximum": 500,
                },
            },
            "required": ["agent_name"],
        },
    ),
    "configure_heartbeat": ToolDef(
        name="configure_heartbeat",
        brief="Enable or disable heartbeat mode — a periodic AI autonomy loop for an agent.",
        description=(
            "Enable or disable heartbeat mode for an agent. "
            "Heartbeat is a proactive autonomy loop — the agent wakes on a configurable interval, "
            "loads its soul and goals from state, and its AI decides whether to act. "
            "Unlike cron schedules (which run specific functions), heartbeat runs the AI reasoning loop itself. "
            "Requires an AI engine to be configured. Ticks count as executions. "
            "Set the agent's soul via set_agent_state with key '__soul__' and goals via '__goals__'."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "Enable (true) or disable (false) heartbeat mode",
                },
                "interval_seconds": {
                    "type": "integer",
                    "description": "Seconds between heartbeat ticks. Must respect tier minimums (Pro: 30s, Enterprise: 15s).",
                    "minimum": 15,
                    "maximum": 86400,
                },
            },
            "required": ["agent_name", "enabled"],
        },
    ),
    "chat_with_agent": ToolDef(
        name="chat_with_agent",
        brief="Send a message to an agent's AI engine and get its response.",
        description=(
            "Send a message to an agent's AI engine and get its response. "
            "The agent can call namespace functions, platform tools (get_state, set_state, send_to_channel), and MCP tools during the conversation. "
            "The agent must have an AI engine configured (use configure_agent_ai first). "
            "Use this to talk to the agent, test its orchestration behavior, or ask it to run its pipeline."
        ),
        input_schema={
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
    "add_channel": ToolDef(
        name="add_channel",
        brief="Add a communication channel (Discord, Slack, WhatsApp, email) to an agent.",
        description=(
            "Add a communication channel to an agent. "
            "Channels allow the agent to send and receive messages on external platforms. "
            "Each channel type requires specific config keys."
        ),
        detailed=(
            "Config keys by channel type:\n"
            '- discord: {"bot_token": "Bot TOKEN", "guild_id": "123456", "channel_id": "789012"}\n'
            '- slack: {"bot_token": "xoxb-...", "channel_id": "C01234567"}\n'
            '- whatsapp: {"phone_number_id": "...", "access_token": "..."}\n'
            '- email: {"smtp_host": "smtp.example.com", "smtp_port": 587, "username": "...", "password": "...", "from": "bot@example.com"}'
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
                "channel_type": {
                    "type": "string",
                    "enum": ["discord", "slack", "whatsapp", "email"],
                    "description": "Platform type",
                },
                "config": {
                    "type": "object",
                    "description": (
                        "Channel-specific configuration. Required keys by type:\n"
                        '- discord: {"bot_token": "Bot TOKEN", "guild_id": "123456", "channel_id": "789012"}\n'
                        '- slack: {"bot_token": "xoxb-...", "channel_id": "C01234567"}\n'
                        '- whatsapp: {"phone_number_id": "...", "access_token": "..."}\n'
                        '- email: {"smtp_host": "smtp.example.com", "smtp_port": 587, "username": "...", "password": "...", "from": "bot@example.com"}'
                    ),
                },
            },
            "required": ["agent_name", "channel_type", "config"],
        },
    ),
    "remove_channel": ToolDef(
        name="remove_channel",
        brief="Remove a communication channel from an agent.",
        description="Remove a communication channel from an agent by its type.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
                "channel_type": {
                    "type": "string",
                    "enum": ["discord", "slack", "whatsapp", "email"],
                    "description": "Channel type to remove",
                },
            },
            "required": ["agent_name", "channel_type"],
        },
    ),
    "clone_agent": ToolDef(
        name="clone_agent",
        brief="Clone an agent, copying its state, schedules, channels, and AI config.",
        description=(
            "Clone an agent into a new agent with a different name. "
            "The clone copies: persistent state (key-value store), cron schedules, channels (Discord/Slack/etc), AI engine configuration, and orchestration limits. "
            "Functions live in services (which belong to the namespace), so they are NOT copied — the clone starts with no functions. "
            "The cloned agent starts in 'stopped' status regardless of the source agent's status."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Source agent name to clone from",
                },
                "new_name": {
                    "type": "string",
                    "description": "New agent name for the clone (lowercase, alphanumeric, hyphens)",
                },
            },
            "required": ["agent_name", "new_name"],
        },
    ),
    "lock_function": ToolDef(
        name="lock_function",
        brief="Lock a function to prevent modification (admin only).",
        description=(
            "Lock a function to prevent any further modification. "
            "Locked functions cannot be updated or deleted until unlocked. "
            "Admin-only operation."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name containing the function",
                },
                "name": {
                    "type": "string",
                    "description": "Function name to lock",
                },
            },
            "required": ["service", "name"],
        },
    ),
    "unlock_function": ToolDef(
        name="unlock_function",
        brief="Unlock a function to allow modification (admin only).",
        description=(
            "Unlock a previously locked function, allowing it to be updated or deleted again. "
            "Admin-only operation."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name containing the function",
                },
                "name": {
                    "type": "string",
                    "description": "Function name to unlock",
                },
            },
            "required": ["service", "name"],
        },
    ),
    "publish_view": ToolDef(
        name="publish_view",
        brief="Publish HTML/JS/CSS files to the agent's visual scratchpad.",
        description=(
            "Publish HTML/JS/CSS to the agent's visual scratchpad. "
            "Creates a web-accessible page at a secret URL. "
            "Use replace mode for full rewrites, append to add files incrementally. "
            "Binary files use 'base64:...' prefix."
        ),
        detailed=(
            "The scratchpad URL is stable and shareable. Retrieve it with get_view_url. "
            "Replace mode clears all existing files before writing. "
            "Append mode adds or overwrites only the specified files, leaving others intact. "
            "Example: publish_view(agent_name='mybot', files={'index.html': '<html>...</html>', 'app.js': 'console.log(\"hello\")'}, mode='replace')"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
                "files": {
                    "type": "object",
                    "description": "Map of filename to content. Example: {'index.html': '<html>...', 'app.js': '...'}. Use 'base64:...' prefix for binary files.",
                    "additionalProperties": {"type": "string"},
                },
                "mode": {
                    "type": "string",
                    "enum": ["replace", "append"],
                    "default": "replace",
                    "description": "replace: clear existing files first. append: add/overwrite specified files only.",
                },
            },
            "required": ["agent_name", "files"],
        },
    ),
    "get_view_url": ToolDef(
        name="get_view_url",
        brief="Get the agent's scratchpad view URL and file listing.",
        description="Get the agent's scratchpad view URL and file listing.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
            },
            "required": ["agent_name"],
        },
    ),
    "clear_view": ToolDef(
        name="clear_view",
        brief="Delete all files from the agent's visual scratchpad.",
        description="Delete all files from the agent's visual scratchpad.",
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
            },
            "required": ["agent_name"],
        },
    ),
    "configure_chat_token": ToolDef(
        name="configure_chat_token",
        brief="Generate or revoke a public chat URL for an agent.",
        description=(
            "Generate or revoke a public chat URL for an agent. "
            "The URL allows web frontends to POST messages to the agent's AI "
            "without API key authentication — the token in the URL IS the auth. "
            "Pattern: POST https://{agent}.agent.mcpworks.io/chat/{token}"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name",
                },
                "action": {
                    "type": "string",
                    "enum": ["generate", "revoke"],
                    "description": "generate: create/rotate token. revoke: disable public chat.",
                },
            },
            "required": ["agent_name", "action"],
        },
    ),
}


RUN_TOOLS: dict[str, ToolDef] = {
    "execute_python": ToolDef(
        name="execute_python",
        brief="Execute Python code in a secure sandbox with access to all namespace functions.",
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
            "Only parameters defined in the function's input_schema will be passed through."
        ),
        detailed=(
            "The sandbox has access to all functions in the current namespace. "
            "Standard library and approved packages are available. "
            "Network access depends on your tier."
        ),
        input_schema={
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
    "execute_typescript": ToolDef(
        name="execute_typescript",
        brief="Execute TypeScript/JavaScript code in a secure Node.js sandbox with access to all namespace functions.",
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
            "Python functions will throw an error explaining they must be called from the Python execute tool."
        ),
        input_schema={
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
    "_env_status": ToolDef(
        name="_env_status",
        brief="Check which environment variables are configured and which are missing.",
        description="Check which environment variables are configured and which are missing for this namespace's functions.",
        input_schema={"type": "object", "properties": {}},
    ),
}


def get_tools(group: str, verbosity: str = "standard") -> list[dict]:
    """Get tool definitions for a group at specified verbosity.

    Args:
        group: One of 'base', 'agent', or 'run'.
        verbosity: One of 'brief', 'standard', or 'detailed'.

    Returns:
        List of MCPTool-compatible dicts.
    """
    groups: dict[str, dict[str, ToolDef]] = {
        "base": BASE_TOOLS,
        "agent": AGENT_TOOLS,
        "run": RUN_TOOLS,
    }
    registry = groups.get(group, {})
    return [tool_def.render(verbosity) for tool_def in registry.values()]


def get_tool(name: str, verbosity: str = "standard") -> dict[str, Any] | None:
    """Get a single tool definition by name.

    Searches all groups. Returns None if not found.
    """
    for registry in (BASE_TOOLS, AGENT_TOOLS, RUN_TOOLS):
        if name in registry:
            return registry[name].render(verbosity)
    return None

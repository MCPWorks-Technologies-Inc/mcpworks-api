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
                    "enum": ["code_sandbox", "nanobot", "github_repo"],
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
                    "description": "Backend-specific configuration. Not needed for 'code_sandbox'.",
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
                "output_trust": {
                    "type": "string",
                    "enum": ["prompt", "data"],
                    "description": "Trust level for function output. 'prompt' = trusted output (computed results, summaries). 'data' = untrusted external content (emails, API responses, web scrapes) — will be wrapped with trust boundary markers. Required.",
                },
            },
            "required": ["service", "name", "backend", "output_trust"],
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
                    "enum": ["code_sandbox", "nanobot", "github_repo"],
                    "description": "Execution backend. Use 'code_sandbox' for Python and TypeScript functions.",
                },
                "code": {
                    "type": "string",
                    "description": "New Python code. Same entry point rules as make_function. NEVER hardcode API keys, tokens, or secrets — use required_env or agent state (context['state']) instead.",
                },
                "config": {
                    "type": "object",
                    "description": "Backend-specific configuration. Not needed for 'code_sandbox'.",
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
                "output_trust": {
                    "type": "string",
                    "enum": ["prompt", "data"],
                    "description": "Change the trust level. 'prompt' = trusted, 'data' = untrusted (wrapped with markers).",
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
        brief="Get full details for an agent including status, AI config, replicas, and resource limits.",
        description="Get full details for an agent including status, AI engine config, resource limits, replica list with names/status/heartbeat, and creation date.",
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
    "scale_agent": ToolDef(
        name="scale_agent",
        brief="Scale an agent to a target number of replicas.",
        description=(
            "Scale an agent to a target number of replicas. Each replica runs the same configuration "
            "(functions, AI engine, schedules, webhooks). Each replica counts as one agent slot toward "
            "your tier limit. Replicas get auto-generated verb-animal names (e.g., daring-duck). "
            "Set replicas=0 to stop all replicas without destroying the agent."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Agent name",
                },
                "replicas": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Target replica count",
                },
            },
            "required": ["name", "replicas"],
        },
    ),
    "start_agent": ToolDef(
        name="start_agent",
        brief="Start a stopped agent or specific replica.",
        description="Start a stopped agent. Starts all replicas, or a specific one if replica is specified.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Agent name to start",
                },
                "replica": {
                    "type": "string",
                    "description": "Target a specific replica by verb-animal name. Omit to start all stopped replicas.",
                },
            },
            "required": ["name"],
        },
    ),
    "stop_agent": ToolDef(
        name="stop_agent",
        brief="Stop a running agent or specific replica.",
        description="Stop a running agent. Pauses scheduled tasks and webhook processing. Stops all replicas, or a specific one if replica is specified. The agent can be restarted with start_agent.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Agent name to stop",
                },
                "replica": {
                    "type": "string",
                    "description": "Target a specific replica by verb-animal name. Omit to stop all running replicas.",
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
                "mode": {
                    "type": "string",
                    "enum": ["single", "cluster"],
                    "description": (
                        "Execution mode for clustered agents. "
                        "'single' (default): exactly one replica executes the schedule. "
                        "'cluster': all replicas execute the schedule independently."
                    ),
                    "default": "single",
                },
                "orchestration_mode": {
                    "type": "string",
                    "enum": ["direct", "reason_first", "run_then_reason", "procedure"],
                    "description": (
                        "How the schedule interacts with the agent's AI engine. "
                        "'direct' (default): execute function without AI. "
                        "'reason_first': send trigger to AI, let it decide which functions to call. "
                        "'run_then_reason': execute function first, pass output to AI for analysis. "
                        "'procedure': execute a named procedure step-by-step."
                    ),
                    "default": "direct",
                },
                "procedure_name": {
                    "type": "string",
                    "description": "Required when orchestration_mode is 'procedure'. Name of the procedure to execute.",
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
            "The webhook URL will be: /mcp/agent/{agent_name}/webhook/{path}"
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
                    "description": "Webhook path segment. Example: 'github/push' creates URL /mcp/agent/{agent}/webhook/github/push",
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
                    "enum": ["direct", "reason_first", "run_then_reason", "procedure"],
                    "description": (
                        "How the webhook interacts with the agent's AI engine. "
                        "'direct' (default): execute handler function without AI. "
                        "'reason_first': send webhook payload to AI, let it decide which functions to call. "
                        "'run_then_reason': execute handler first, pass output to AI for analysis. "
                        "'procedure': execute a named procedure step-by-step."
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
            "For clustered agents, specify a replica name for session continuity. "
            "If omitted, the message is routed to any available replica and the response includes which replica handled it."
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
                "replica": {
                    "type": "string",
                    "description": "Target a specific replica for session continuity. Omit for any available replica.",
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
    "make_procedure": ToolDef(
        name="make_procedure",
        brief="Create a procedure — an ordered sequence of steps that each call a specific function.",
        description=(
            "Create a procedure with ordered steps. Each step references a function that the AI must call. "
            "The orchestrator enforces step-by-step execution and captures actual function results as proof. "
            "This eliminates LLM hallucination of function calls."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name"},
                "name": {"type": "string", "description": "Procedure name"},
                "description": {"type": "string", "description": "What this procedure does"},
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "description": "Ordered list of steps",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Step name"},
                            "function_ref": {
                                "type": "string",
                                "description": "Function to call (service.function format)",
                            },
                            "instructions": {
                                "type": "string",
                                "description": "Instructions for the AI at this step",
                            },
                            "failure_policy": {
                                "type": "string",
                                "enum": ["required", "allowed", "skip"],
                                "default": "required",
                            },
                            "max_retries": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 5,
                                "default": 1,
                            },
                            "validation": {
                                "type": "object",
                                "description": "Optional: {required_fields: ['field1']}",
                            },
                        },
                        "required": ["name", "function_ref", "instructions"],
                    },
                },
            },
            "required": ["service", "name", "steps"],
        },
    ),
    "update_procedure": ToolDef(
        name="update_procedure",
        brief="Update a procedure's steps (creates a new immutable version).",
        description="Update a procedure. If steps are provided, a new version is created. Old versions remain for audit.",
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name"},
                "name": {"type": "string", "description": "Procedure name"},
                "description": {"type": "string"},
                "steps": {
                    "type": "array",
                    "description": "New step definitions (creates new version)",
                },
            },
            "required": ["service", "name"],
        },
    ),
    "delete_procedure": ToolDef(
        name="delete_procedure",
        brief="Soft-delete a procedure. Execution records are preserved.",
        description="Soft-delete a procedure. It will no longer appear in listings. Historical execution records remain intact for audit.",
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name"},
                "name": {"type": "string", "description": "Procedure name"},
            },
            "required": ["service", "name"],
        },
    ),
    "list_procedures": ToolDef(
        name="list_procedures",
        brief="List all procedures in a service.",
        description="List all procedures in a service with their names, step counts, and versions.",
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name"},
            },
            "required": ["service"],
        },
    ),
    "describe_procedure": ToolDef(
        name="describe_procedure",
        brief="Get full details of a procedure including step definitions and version history.",
        description="Get full details of a procedure: steps, failure policies, validation rules, version history.",
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name"},
                "name": {"type": "string", "description": "Procedure name"},
            },
            "required": ["service", "name"],
        },
    ),
    "run_procedure": ToolDef(
        name="run_procedure",
        brief="Execute a procedure step-by-step with enforced function calls.",
        description=(
            "Execute a procedure. The orchestrator steps through each defined step, calling the required function "
            "and capturing its result before advancing. Each step produces verifiable proof of execution."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name"},
                "name": {"type": "string", "description": "Procedure name"},
                "input_context": {
                    "type": "object",
                    "description": "Optional initial context available to step 1",
                },
            },
            "required": ["service", "name"],
        },
    ),
    "list_procedure_executions": ToolDef(
        name="list_procedure_executions",
        brief="List execution records for a procedure.",
        description="List execution records with status, timestamps, and step counts. Filter by status.",
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name"},
                "name": {"type": "string", "description": "Procedure name"},
                "status": {"type": "string", "enum": ["running", "completed", "failed"]},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["service", "name"],
        },
    ),
    "describe_procedure_execution": ToolDef(
        name="describe_procedure_execution",
        brief="Get the full audit trail for a procedure execution.",
        description="Get step-by-step details: function called, result data, retry attempts, timestamps, and status for each step.",
        input_schema={
            "type": "object",
            "properties": {
                "execution_id": {"type": "string", "description": "Execution UUID"},
            },
            "required": ["execution_id"],
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
            "Pattern: POST /mcp/agent/{agent}/chat/{token}"
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
    "configure_agent_access": ToolDef(
        name="configure_agent_access",
        brief="Add access rules or set trust score for an agent.",
        description=(
            "Add a per-agent access rule or set the agent's trust score. "
            "Provide 'rule' to add access rules, or 'trust_score' to set the score directly. "
            "Rule types: "
            "'allow_services', 'deny_services', 'allow_functions', 'deny_functions', "
            "'allow_keys', 'deny_keys'. "
            "Function rules support optional 'min_trust_score' (0-1000) to gate access "
            "based on the agent's behavioral trust score. "
            "Trust scores degrade automatically on security events and recover slowly "
            "on successful executions. Default score is 500. "
            "Example rule: configure_agent_access(agent_name='bot', "
            "rule={'type': 'allow_functions', 'patterns': ['svc.*'], 'min_trust_score': 400}). "
            "Example trust: configure_agent_access(agent_name='bot', trust_score=500)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name of the agent to configure.",
                },
                "rule": {
                    "type": "object",
                    "description": (
                        "Access rule definition. Must include 'type' and 'patterns'. "
                        "Optional 'min_trust_score' for trust-gated access."
                    ),
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "allow_services",
                                "deny_services",
                                "allow_functions",
                                "deny_functions",
                                "allow_keys",
                                "deny_keys",
                            ],
                        },
                        "patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "min_trust_score": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 1000,
                            "description": "Minimum trust score required to use matched functions.",
                        },
                    },
                    "required": ["type", "patterns"],
                },
                "trust_score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 1000,
                    "description": "Set the agent's trust score directly (admin override).",
                },
            },
            "required": ["agent_name"],
        },
    ),
    "list_agent_access_rules": ToolDef(
        name="list_agent_access_rules",
        brief="List all access rules configured for an agent.",
        description=(
            "List all function and state access rules configured for an agent. "
            "Returns function_rules and state_rules with their IDs, types, and patterns. "
            "Rule IDs can be used with remove_agent_access_rule to remove specific rules. "
            "Example: list_agent_access_rules(agent_name='social-bot')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name of the agent to list access rules for.",
                },
            },
            "required": ["agent_name"],
        },
    ),
    "remove_agent_access_rule": ToolDef(
        name="remove_agent_access_rule",
        brief="Remove an access rule from an agent by ID.",
        description=(
            "Remove a specific function or state access rule from an agent by its rule ID. "
            "Rule IDs are returned when rules are added via configure_agent_access "
            "and visible in list_agent_access_rules. "
            "Example: remove_agent_access_rule(agent_name='social-bot', rule_id='r-a1b2c3d4')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name of the agent to remove a rule from.",
                },
                "rule_id": {
                    "type": "string",
                    "description": "ID of the rule to remove (e.g., 'r-a1b2c3d4').",
                },
            },
            "required": ["agent_name", "rule_id"],
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
        "git": GIT_TOOLS,
        "analytics": ANALYTICS_TOOLS,
    }
    registry = groups.get(group, {})
    return [tool_def.render(verbosity) for tool_def in registry.values()]


GIT_TOOLS: dict[str, ToolDef] = {
    "configure_git_remote": ToolDef(
        name="configure_git_remote",
        brief="Configure a Git remote for exporting this namespace.",
        description=(
            "Configure a Git remote for this namespace. "
            "You MUST call this before using export_namespace or export_service. "
            "The namespace will push exports to this repository. "
            "One remote per namespace; calling again overwrites the previous configuration. "
            "Works with any Git host that supports HTTPS: GitHub, GitLab, Gitea, Bitbucket, or self-hosted. "
            "The token is verified against the remote before saving. "
            "Example: configure_git_remote(git_url='https://github.com/user/my-functions.git', git_token='ghp_abc123...')"
        ),
        detailed=(
            "The personal access token (PAT) is encrypted at rest using AES-256-GCM envelope encryption. "
            "The URL must be an HTTPS Git URL ending in .git. SSH URLs are not supported. "
            "To get a PAT: GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → "
            "create with 'Contents: Read and write' permission on the target repo. "
            "GitLab → Preferences → Access Tokens → create with 'write_repository' scope. "
            "The token only needs push access to the single repository you configure."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "git_url": {
                    "type": "string",
                    "description": "HTTPS Git URL. Must end with .git. Example: 'https://github.com/user/my-functions.git'",
                },
                "git_token": {
                    "type": "string",
                    "description": "Personal access token (PAT) with push access to the repository. Example: 'ghp_xxxxxxxxxxxx' (GitHub) or 'glpat-xxxxxxxxxxxx' (GitLab)",
                },
                "git_branch": {
                    "type": "string",
                    "description": "Target branch name. Default: 'main'. Use 'main' unless the repo uses a different default branch.",
                    "default": "main",
                },
            },
            "required": ["git_url", "git_token"],
        },
    ),
    "remove_git_remote": ToolDef(
        name="remove_git_remote",
        brief="Remove the Git remote configuration for this namespace.",
        description=(
            "Remove the Git remote configuration for this namespace. "
            "After removal, export_namespace and export_service will fail until a new remote is configured. "
            "This does NOT delete the remote repository or its contents — only the stored configuration."
        ),
        input_schema={"type": "object", "properties": {}},
    ),
    "export_namespace": ToolDef(
        name="export_namespace",
        brief="Export this namespace to its configured Git remote.",
        description=(
            "Export the entire namespace to its configured Git remote. "
            "PREREQUISITE: You must call configure_git_remote first. "
            "Serializes all services, functions (active version code), and agent definitions "
            "into YAML manifest files + handler.py/handler.ts code files, then commits and pushes to the remote. "
            "Each export is a full replacement — the repo always reflects the exact current namespace state. "
            "Git handles diffing between exports, so you get meaningful commit history. "
            "Secrets (env var values, API keys, channel tokens) are NEVER exported."
        ),
        detailed=(
            "The export creates this structure in the Git repo:\n"
            "  {namespace}/namespace.yaml\n"
            "  {namespace}/services/{service}/service.yaml\n"
            "  {namespace}/services/{service}/functions/{function}/function.yaml\n"
            "  {namespace}/services/{service}/functions/{function}/handler.py\n"
            "  {namespace}/agents/{agent}/agent.yaml\n\n"
            "function.yaml contains input/output schemas, requirements, tags, and env var declarations (names only). "
            "handler.py contains the active version's source code. "
            "agent.yaml contains AI engine/model, system prompt, schedules, and webhooks (no API keys or channel credentials)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Git commit message. If omitted, defaults to 'MCPWorks export: {namespace}'",
                },
            },
        },
    ),
    "export_service": ToolDef(
        name="export_service",
        brief="Export a single service to the namespace's Git remote.",
        description=(
            "Export a single service to the namespace's configured Git remote. "
            "PREREQUISITE: You must call configure_git_remote first. "
            "Only the specified service and its functions are included in the commit. "
            "Use this when you want to share or back up a specific service rather than the entire namespace."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Name of the service to export. Must be an existing service in this namespace. Example: 'utils'",
                },
                "message": {
                    "type": "string",
                    "description": "Git commit message. If omitted, defaults to 'MCPWorks export: {namespace}/{service}'",
                },
            },
            "required": ["service"],
        },
    ),
    "import_namespace": ToolDef(
        name="import_namespace",
        brief="Import a namespace from a Git repository.",
        description=(
            "Clone a Git repository and create a namespace from a MCPWorks export directory. "
            "Creates the namespace, all services, functions (with code), and agent definitions in one operation. "
            "The repo must contain a valid MCPWorks export (namespace.yaml at root or in a subdirectory). "
            "Secrets are NOT imported — after import, you must separately configure: "
            "(1) AI API keys for agents via configure_agent_ai, "
            "(2) channel credentials via add_channel, "
            "(3) environment variable values for functions that declare required_env. "
            "For public repos, git_token is not needed. For private repos, provide a PAT with read access."
        ),
        detailed=(
            "Conflict handling:\n"
            "- 'fail' (default): Abort the entire import if ANY entity (namespace, service, or function) already exists. Safest option.\n"
            "- 'skip': Import only entities that don't already exist. Existing entities are left untouched. Good for partial imports.\n"
            "- 'overwrite': Update existing entities with the imported data. For functions, this creates a new version. Use when restoring from backup."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "git_url": {
                    "type": "string",
                    "description": "HTTPS Git URL to clone. Example: 'https://github.com/user/my-functions.git'",
                },
                "git_token": {
                    "type": "string",
                    "description": "Personal access token for private repos. Omit for public repos. Example: 'ghp_xxxxxxxxxxxx'",
                },
                "git_branch": {
                    "type": "string",
                    "description": "Branch to clone. Default: 'main'",
                    "default": "main",
                },
                "name": {
                    "type": "string",
                    "description": "Override the namespace name from the export. If omitted, uses the name from namespace.yaml. Example: 'my-imported-ns'",
                },
                "conflict": {
                    "type": "string",
                    "enum": ["fail", "skip", "overwrite"],
                    "description": "How to handle existing entities. 'fail' = abort if anything exists (default, safest). 'skip' = import only new entities. 'overwrite' = update existing entities (creates new function versions).",
                    "default": "fail",
                },
            },
            "required": ["git_url"],
        },
    ),
    "import_service": ToolDef(
        name="import_service",
        brief="Import a single service from a Git repository into this namespace.",
        description=(
            "Clone a Git repository and import a single service into the current namespace. "
            "Only the specified service's functions are created. The service must exist in the repo's export structure. "
            "Use this to pull in a shared utility service from another namespace's export. "
            "For public repos, git_token is not needed. For private repos, provide a PAT with read access."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "git_url": {
                    "type": "string",
                    "description": "HTTPS Git URL to clone. Example: 'https://github.com/user/my-functions.git'",
                },
                "git_token": {
                    "type": "string",
                    "description": "Personal access token for private repos. Omit for public repos.",
                },
                "service": {
                    "type": "string",
                    "description": "Name of the service to import from the repo. Must match a service directory in the export. Example: 'utils'",
                },
                "conflict": {
                    "type": "string",
                    "enum": ["fail", "skip", "overwrite"],
                    "description": "How to handle existing entities. 'fail' = abort if anything exists (default). 'skip' = import only new functions. 'overwrite' = update existing functions with new versions.",
                    "default": "fail",
                },
            },
            "required": ["git_url", "service"],
        },
    ),
}

MCP_SERVER_TOOLS: dict[str, ToolDef] = {
    "add_mcp_server": ToolDef(
        name="add_mcp_server",
        brief="Register a third-party MCP server on this namespace.",
        description=(
            "Register a third-party MCP server so its tools are available for agents in this namespace. "
            "MCPWorks connects to the server immediately to discover its tools and caches the schemas. "
            "PREREQUISITE: provide either url (for sse or streamable_http transport) or command (for stdio transport). "
            "For HTTP transports, auth_token is sent as a Bearer token in the Authorization header. "
            "Example (HTTP): add_mcp_server(name='github', url='https://api.github.com/mcp', auth_token='ghp_xxx'). "
            "Example (stdio): add_mcp_server(name='local-fs', transport='stdio', command='npx', args=['-y', '@modelcontextprotocol/server-filesystem', '/tmp'])."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for this MCP server within the namespace. Lowercase, alphanumeric, hyphens. Example: 'github'",
                },
                "url": {
                    "type": "string",
                    "description": "URL of the MCP server endpoint. Required for sse and streamable_http transports. Example: 'https://api.github.com/mcp'",
                },
                "transport": {
                    "type": "string",
                    "enum": ["streamable_http", "sse", "stdio"],
                    "description": "Transport protocol. Default: 'streamable_http'. Use 'sse' for older MCP servers, 'stdio' for local process-based servers.",
                    "default": "streamable_http",
                },
                "auth_token": {
                    "type": "string",
                    "description": "Bearer token for authentication. Stored encrypted. Sent as 'Authorization: Bearer <token>'. Example: 'ghp_xxxxxxxxxxxxx'",
                },
                "headers": {
                    "type": "object",
                    "description": 'Additional HTTP headers as key-value pairs. Stored encrypted. Example: {"X-Api-Key": "abc123"}',
                },
                "command": {
                    "type": "string",
                    "description": "Executable to run for stdio transport. Example: 'npx' or 'python'",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Arguments for the stdio command. Example: ['-y', '@modelcontextprotocol/server-filesystem', '/data']",
                },
            },
            "required": ["name"],
        },
    ),
    "remove_mcp_server": ToolDef(
        name="remove_mcp_server",
        brief="Remove a registered MCP server from this namespace.",
        description=(
            "Permanently remove a registered MCP server from this namespace. "
            "The server's tool schemas, settings, and encrypted credentials are deleted. "
            "Any agents configured to use this server will lose access to its tools. "
            "Example: remove_mcp_server(name='github')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server to remove. Example: 'github'",
                },
            },
            "required": ["name"],
        },
    ),
    "list_mcp_servers": ToolDef(
        name="list_mcp_servers",
        brief="List all MCP servers registered on this namespace.",
        description=(
            "List all third-party MCP servers registered on this namespace. "
            "Returns a summary of each server including its name, URL, transport, tool count, enabled status, "
            "and when it last successfully connected. "
            "Use describe_mcp_server to get full details including individual tool schemas."
        ),
        input_schema={"type": "object", "properties": {}},
    ),
    "describe_mcp_server": ToolDef(
        name="describe_mcp_server",
        brief="Get full details of a registered MCP server including its tools.",
        description=(
            "Get full details for a registered MCP server: connection settings, current tunable settings, "
            "env var names (not values), and the cached tool schemas (name and description of each tool). "
            "Use this to inspect what tools an MCP server exposes before configuring an agent to use it. "
            "Example: describe_mcp_server(name='github')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server to describe. Example: 'github'",
                },
            },
            "required": ["name"],
        },
    ),
    "refresh_mcp_server": ToolDef(
        name="refresh_mcp_server",
        brief="Reconnect to an MCP server and update its cached tool schemas.",
        description=(
            "Reconnect to a registered MCP server and refresh its cached tool list. "
            "Use this after the upstream server adds or removes tools. "
            "Returns the updated tool count and lists which tools were added or removed. "
            "Example: refresh_mcp_server(name='github')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server to refresh. Example: 'github'",
                },
            },
            "required": ["name"],
        },
    ),
    "update_mcp_server": ToolDef(
        name="update_mcp_server",
        brief="Update credentials or URL for a registered MCP server.",
        description=(
            "Update the connection credentials or URL for an existing MCP server registration. "
            "Provide only the fields you want to change; omitted fields are left unchanged. "
            "Use this to rotate API keys or point the server at a new endpoint URL. "
            "Example (rotate token): update_mcp_server(name='github', auth_token='ghp_newtoken'). "
            "Example (change URL): update_mcp_server(name='github', url='https://new-endpoint.example.com/mcp')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server to update. Example: 'github'",
                },
                "auth_token": {
                    "type": "string",
                    "description": "New Bearer token for authentication. Replaces the existing token.",
                },
                "headers": {
                    "type": "object",
                    "description": 'Replacement HTTP headers. Replaces all existing custom headers. Example: {"X-Api-Key": "newkey"}',
                },
                "url": {
                    "type": "string",
                    "description": "New URL for the MCP server endpoint. Example: 'https://new-endpoint.example.com/mcp'",
                },
            },
            "required": ["name"],
        },
    ),
    "set_mcp_server_setting": ToolDef(
        name="set_mcp_server_setting",
        brief="Update a tunable setting on a registered MCP server.",
        description=(
            "Update a tunable operational setting for a registered MCP server. "
            "Valid keys: response_limit_bytes (int, max bytes in a tool response), "
            "timeout_seconds (int, connection and response timeout), "
            "max_calls_per_execution (int, max tool calls per agent execution), "
            "retry_on_failure (bool, auto-retry on transient errors), "
            "retry_count (int, number of retries), "
            "enabled (bool, whether the server is active). "
            "Example: set_mcp_server_setting(name='github', key='timeout_seconds', value=60). "
            "Example: set_mcp_server_setting(name='github', key='enabled', value=False)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server. Example: 'github'",
                },
                "key": {
                    "type": "string",
                    "description": "Setting key to update. One of: response_limit_bytes, timeout_seconds, max_calls_per_execution, retry_on_failure, retry_count, enabled.",
                },
                "value": {
                    "description": "New value for the setting. Must match the expected type for the key (int, bool, etc.).",
                },
            },
            "required": ["name", "key", "value"],
        },
    ),
    "set_mcp_server_env": ToolDef(
        name="set_mcp_server_env",
        brief="Set an environment variable on a registered MCP server.",
        description=(
            "Set an environment variable that will be injected when connecting to this MCP server. "
            "Useful for stdio-transport servers that read configuration from environment variables. "
            "The value is stored in plaintext in the server record. "
            "Example: set_mcp_server_env(name='local-fs', key='FS_ROOT', value='/data/workspace')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server. Example: 'local-fs'",
                },
                "key": {
                    "type": "string",
                    "description": "Environment variable name. Example: 'FS_ROOT'",
                },
                "value": {
                    "type": "string",
                    "description": "Environment variable value. Example: '/data/workspace'",
                },
            },
            "required": ["name", "key", "value"],
        },
    ),
    "remove_mcp_server_env": ToolDef(
        name="remove_mcp_server_env",
        brief="Remove an environment variable from a registered MCP server.",
        description=(
            "Remove an environment variable from a registered MCP server's configuration. "
            "If the key does not exist, the operation succeeds silently. "
            "Example: remove_mcp_server_env(name='local-fs', key='FS_ROOT')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server. Example: 'local-fs'",
                },
                "key": {
                    "type": "string",
                    "description": "Environment variable name to remove. Example: 'FS_ROOT'",
                },
            },
            "required": ["name", "key"],
        },
    ),
    "configure_agent_mcp": ToolDef(
        name="configure_agent_mcp",
        brief="Set which MCP servers an agent can access during execution.",
        description=(
            "Configure the list of MCP servers an agent is allowed to call during execution. "
            "The servers must already be registered on this namespace via add_mcp_server. "
            "Replaces any previously configured MCP server list for the agent. "
            "Pass an empty array to remove all MCP server access from the agent. "
            "Example: configure_agent_mcp(agent_name='my-agent', servers=['github', 'slack']). "
            "Example (remove all): configure_agent_mcp(agent_name='my-agent', servers=[])."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name of the agent to configure. Example: 'my-agent'",
                },
                "servers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of MCP server names the agent may access. Each must be registered on this namespace. Example: ['github', 'slack']",
                },
            },
            "required": ["agent_name", "servers"],
        },
    ),
    "add_mcp_server_rule": ToolDef(
        name="add_mcp_server_rule",
        brief="Add a request or response rule to a registered MCP server.",
        description=(
            "Add a rule that is applied to tool calls made to or from a registered MCP server. "
            "direction must be 'request' (applied before the tool call is sent) or 'response' (applied to the tool result). "
            "Available rule types: 'redact' (remove fields matching a path or pattern), "
            "'truncate' (limit response length), "
            "'allow_tools' (whitelist specific tools by name), "
            "'deny_tools' (block specific tools by name), "
            "'inject_header' (add a header to outgoing requests). "
            "Each rule must include a 'type' field and type-specific parameters. "
            "Example: add_mcp_server_rule(name='github', direction='response', rule={'type': 'truncate', 'max_bytes': 4096}). "
            "Example: add_mcp_server_rule(name='github', direction='request', rule={'type': 'allow_tools', 'tools': ['get_issue', 'list_repos']})."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server to add the rule to. Example: 'github'",
                },
                "direction": {
                    "type": "string",
                    "enum": ["request", "response"],
                    "description": "When the rule is applied: 'request' (before the tool call) or 'response' (after the tool result is received).",
                },
                "rule": {
                    "type": "object",
                    "description": "Rule definition. Must include 'type' (one of: redact, truncate, allow_tools, deny_tools, inject_header) plus type-specific fields.",
                },
            },
            "required": ["name", "direction", "rule"],
        },
    ),
    "remove_mcp_server_rule": ToolDef(
        name="remove_mcp_server_rule",
        brief="Remove a rule from a registered MCP server by ID.",
        description=(
            "Remove a request or response rule from a registered MCP server by its rule ID. "
            "Rule IDs are returned when the rule is added via add_mcp_server_rule and visible in list_mcp_server_rules. "
            "Example: remove_mcp_server_rule(name='github', rule_id='r-a1b2c3d4')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server. Example: 'github'",
                },
                "rule_id": {
                    "type": "string",
                    "description": "ID of the rule to remove. Example: 'r-a1b2c3d4'",
                },
            },
            "required": ["name", "rule_id"],
        },
    ),
    "list_mcp_server_rules": ToolDef(
        name="list_mcp_server_rules",
        brief="List all rules configured on a registered MCP server.",
        description=(
            "List all request and response rules configured on a registered MCP server. "
            "Returns two lists: request_rules (applied before tool calls) and response_rules (applied to tool results). "
            "Each rule includes its ID, type, and type-specific parameters. "
            "Example: list_mcp_server_rules(name='github')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server. Example: 'github'",
                },
            },
            "required": ["name"],
        },
    ),
    "set_mcp_server_tool_trust": ToolDef(
        name="set_mcp_server_tool_trust",
        brief="Set the output trust level for a specific tool on a registered MCP server.",
        description=(
            "Override the output trust level for a specific tool exposed by a registered MCP server. "
            "output_trust controls how tool results are handled by agents: "
            "'prompt' means the result is included in the agent's prompt context (standard), "
            "'data' means the result is treated as structured data and not injected into the prompt (token-efficient). "
            "Example: set_mcp_server_tool_trust(name='github', tool='get_issue', output_trust='data')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server. Example: 'github'",
                },
                "tool": {
                    "type": "string",
                    "description": "Name of the tool to configure. Must be a tool exposed by this MCP server. Example: 'get_issue'",
                },
                "output_trust": {
                    "type": "string",
                    "enum": ["prompt", "data"],
                    "description": "'prompt' includes tool output in the agent's prompt context. 'data' treats it as structured data (token-efficient).",
                },
            },
            "required": ["name", "tool", "output_trust"],
        },
    ),
}


ANALYTICS_TOOLS: dict[str, ToolDef] = {
    "get_mcp_server_stats": ToolDef(
        name="get_mcp_server_stats",
        brief="Get per-tool performance stats for an MCP server.",
        description="Get per-tool performance stats for a registered MCP server in this namespace.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "MCP server name",
                },
                "period": {
                    "type": "string",
                    "description": "Time period for stats",
                    "enum": ["1h", "24h", "7d", "30d"],
                    "default": "24h",
                },
            },
            "required": ["name"],
        },
    ),
    "get_token_savings_report": ToolDef(
        name="get_token_savings_report",
        brief="Get namespace-wide token savings report.",
        description="Get a token savings report for this namespace across all MCP proxy calls.",
        input_schema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Time period for the report",
                    "enum": ["1h", "24h", "7d", "30d"],
                    "default": "24h",
                },
            },
        },
    ),
    "suggest_optimizations": ToolDef(
        name="suggest_optimizations",
        brief="Get actionable optimization suggestions for MCP server usage.",
        description="Get actionable optimization suggestions for MCP server usage in this namespace.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "MCP server name to analyze (omit for all servers)",
                },
                "probe": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tool names to live-probe for response size analysis",
                },
            },
        },
    ),
    "get_function_mcp_stats": ToolDef(
        name="get_function_mcp_stats",
        brief="Get per-function MCP proxy usage stats.",
        description="Get per-function MCP proxy usage statistics for this namespace.",
        input_schema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Time period for stats",
                    "enum": ["1h", "24h", "7d", "30d"],
                    "default": "24h",
                },
            },
        },
    ),
    "list_executions": ToolDef(
        name="list_executions",
        brief="List recent function execution history with optional filters.",
        description=(
            "List recent function executions for this namespace. "
            "Filter by service name, function name, or status (completed, failed, timed_out). "
            "Returns execution summaries with status, timing, and error messages. "
            "Example: list_executions(service='social', function='post-to-bluesky', status='failed')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Filter by service name.",
                },
                "function": {
                    "type": "string",
                    "description": "Filter by function name.",
                },
                "status": {
                    "type": "string",
                    "enum": ["completed", "failed", "timed_out"],
                    "description": "Filter by execution status.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20, max 100).",
                    "default": 20,
                },
            },
        },
    ),
    "describe_execution": ToolDef(
        name="describe_execution",
        brief="Get full detail for a specific execution including input, output, and errors.",
        description=(
            "Get complete execution detail by ID. Returns input data, output/error, "
            "stdout/stderr, function version, timing, and backend metadata. "
            "Use list_executions to find execution IDs. "
            "Example: describe_execution(execution_id='abc-123-def')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "execution_id": {
                    "type": "string",
                    "description": "Execution UUID.",
                },
            },
            "required": ["execution_id"],
        },
    ),
    "add_security_scanner": ToolDef(
        name="add_security_scanner",
        brief="Add a security scanner to the namespace's scanner pipeline.",
        description=(
            "Add a scanner to the namespace's security pipeline. Scanners evaluate function "
            "inputs/outputs for prompt injection, secrets, and other threats. "
            "Three types: 'builtin' (pattern_scanner, secret_scanner, trust_boundary), "
            "'webhook' (POST to external URL), 'python' (importable Python callable). "
            "Example: add_security_scanner(type='webhook', name='my-guard', direction='output', "
            "config={'url': 'https://guard.internal/scan', 'timeout_ms': 2000})."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["builtin", "webhook", "python"]},
                "name": {"type": "string", "description": "Human-readable scanner name."},
                "direction": {"type": "string", "enum": ["input", "output", "both"]},
                "config": {"type": "object", "description": "Type-specific config."},
            },
            "required": ["type", "name", "direction", "config"],
        },
    ),
    "list_security_scanners": ToolDef(
        name="list_security_scanners",
        brief="List all scanners in the namespace's security pipeline.",
        description="List all configured security scanners for this namespace, including their type, direction, order, and enabled status.",
        input_schema={"type": "object", "properties": {}},
    ),
    "update_security_scanner": ToolDef(
        name="update_security_scanner",
        brief="Update a security scanner's config, enabled status, or execution order.",
        description="Update an existing scanner in the pipeline. Use to enable/disable scanners, change their config, or reorder them. Lower order numbers run first.",
        input_schema={
            "type": "object",
            "properties": {
                "scanner_id": {"type": "string", "description": "Scanner ID (e.g., 's-a1b2c3d4')."},
                "enabled": {"type": "boolean", "description": "Enable or disable the scanner."},
                "config": {"type": "object", "description": "Updated config (merged)."},
                "order": {"type": "integer", "description": "Execution order (lower runs first)."},
            },
            "required": ["scanner_id"],
        },
    ),
    "remove_security_scanner": ToolDef(
        name="remove_security_scanner",
        brief="Remove a scanner from the namespace's security pipeline.",
        description="Remove a scanner by ID. Use list_security_scanners to find scanner IDs.",
        input_schema={
            "type": "object",
            "properties": {
                "scanner_id": {"type": "string", "description": "Scanner ID to remove."},
            },
            "required": ["scanner_id"],
        },
    ),
    "configure_telemetry_webhook": ToolDef(
        name="configure_telemetry_webhook",
        brief="Set, update, or remove a telemetry webhook for this namespace.",
        description=(
            "Configure a webhook URL that receives execution metadata on every tool call. "
            "Supports HMAC-SHA256 signing and optional event batching. "
            "Set remove=true to disable the webhook."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "HTTPS webhook URL (HTTP allowed for localhost only).",
                },
                "secret": {
                    "type": "string",
                    "description": "HMAC-SHA256 signing secret (optional, encrypted at rest).",
                },
                "batch_enabled": {
                    "type": "boolean",
                    "description": "Enable event batching (default: false).",
                },
                "batch_interval_seconds": {
                    "type": "integer",
                    "description": "Flush interval for batching in seconds (1-60, default: 10).",
                },
                "remove": {
                    "type": "boolean",
                    "description": "Set true to remove the webhook entirely.",
                },
            },
        },
    ),
}


def get_tool(name: str, verbosity: str = "standard") -> dict[str, Any] | None:
    """Get a single tool definition by name.

    Searches all groups. Returns None if not found.
    """
    for registry in (
        BASE_TOOLS,
        AGENT_TOOLS,
        RUN_TOOLS,
        GIT_TOOLS,
        MCP_SERVER_TOOLS,
        ANALYTICS_TOOLS,
    ):
        if name in registry:
            return registry[name].render(verbosity)
    return None

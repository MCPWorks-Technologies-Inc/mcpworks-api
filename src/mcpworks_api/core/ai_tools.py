"""Build tool definitions for AI orchestration from namespace functions."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.services.function import FunctionService

PLATFORM_TOOLS: list[dict] = [
    {
        "name": "send_to_channel",
        "description": "Send a message to a configured communication channel (discord, slack, email)",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel_type": {
                    "type": "string",
                    "enum": ["discord", "slack", "email"],
                },
                "message": {"type": "string"},
            },
            "required": ["channel_type", "message"],
        },
    },
    {
        "name": "get_state",
        "description": "Read a value from persistent agent state by key",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    },
    {
        "name": "set_state",
        "description": "Write a value to persistent agent state",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {},
            },
            "required": ["key", "value"],
        },
    },
]

PLATFORM_TOOL_NAMES = frozenset(t["name"] for t in PLATFORM_TOOLS)


async def build_tool_definitions(
    namespace_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """Build tool definitions from all functions in a namespace + platform tools.

    Tool name format: "{service_name}__{function_name}" (double underscore).
    """
    function_service = FunctionService(db)
    pairs = await function_service.list_all_for_namespace(namespace_id)

    tools: list[dict] = []
    for fn, version in pairs:
        service_name = fn.service.name if fn.service else "unknown"
        tool_name = f"{service_name}__{fn.name}"
        tools.append(
            {
                "name": tool_name,
                "description": fn.description or f"Execute {service_name}.{fn.name}",
                "input_schema": version.input_schema or {"type": "object", "properties": {}},
            }
        )

    tools.extend(PLATFORM_TOOLS)
    return tools


def parse_tool_name(tool_name: str) -> tuple[str, str] | None:
    """Parse a namespace function tool name into (service_name, function_name).

    Accepts both canonical format (service__function) and dot notation
    (service.function) which AI models may use from system prompt references.

    Returns None if the tool_name is a platform tool, MCP tool, or unrecognized.
    """
    if tool_name in PLATFORM_TOOL_NAMES:
        return None
    from mcpworks_api.core.mcp_client import is_mcp_tool

    if is_mcp_tool(tool_name):
        return None
    if "__" in tool_name:
        service_name, function_name = tool_name.split("__", 1)
        return service_name, function_name
    if "." in tool_name:
        service_name, function_name = tool_name.split(".", 1)
        return service_name, function_name
    return None


def format_available_tools(tools: list[dict]) -> str:
    """Format available tool names for error messages to help the AI self-correct."""
    names = [t["name"] for t in tools]
    if len(names) <= 15:
        return ", ".join(names)
    return ", ".join(names[:15]) + f" (and {len(names) - 15} more)"


def augment_system_prompt(system_prompt: str | None, tools: list[dict]) -> str:
    """Append available tool names to the system prompt.

    AI models may not connect natural function references in the system prompt
    (e.g. 'leads.harvest-leads') to the actual tool names in the tool
    definitions (e.g. 'leads__harvest-leads'). This bridges the gap by
    listing exact callable tool names at the end of the system prompt.
    """
    ns_tools = [t for t in tools if t["name"] not in PLATFORM_TOOL_NAMES]
    platform = [t for t in tools if t["name"] in PLATFORM_TOOL_NAMES]

    lines = []
    if ns_tools:
        lines.append("## Your callable tools")
        lines.append("Use these EXACT names when making tool calls:")
        for t in ns_tools:
            desc = t.get("description", "")
            lines.append(f"- `{t['name']}` — {desc}")
    if platform:
        lines.append("")
        lines.append("## Platform tools")
        for t in platform:
            lines.append(f"- `{t['name']}` — {t.get('description', '')}")

    suffix = "\n".join(lines)
    base = system_prompt or ""
    if base:
        return f"{base}\n\n{suffix}"
    return suffix

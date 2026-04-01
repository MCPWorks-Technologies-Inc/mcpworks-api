"""Build tool definitions for AI orchestration from namespace functions."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.services.function import FunctionService

PLATFORM_TOOLS: list[dict] = [
    {
        "name": "send_to_channel",
        "description": (
            "Send a message to a configured communication channel. "
            "Use this to notify users or post updates. "
            "Example: send_to_channel(channel_type='discord', message='Deploy complete!') "
            'Returns {"sent": true, "channel": "discord"} on success.'
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "channel_type": {
                    "type": "string",
                    "enum": ["discord", "slack", "email"],
                    "description": "Which channel to send to: 'discord', 'slack', or 'email'",
                },
                "message": {
                    "type": "string",
                    "description": "The message text to send",
                },
            },
            "required": ["channel_type", "message"],
        },
    },
    {
        "name": "get_state",
        "description": (
            "Read a single value from your persistent memory by exact key name. "
            "Use this when you know the exact key. If you don't know the key name, "
            "use list_state_keys or search_state first. "
            "Example: get_state(key='user_prefs') "
            'Returns {"key": "user_prefs", "value": ...} or an error if key not found.'
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Exact key name to retrieve (e.g. '__goals__', 'config', 'last_run')",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "set_state",
        "description": (
            "Save a value to your persistent memory. Values survive restarts and "
            "are available in future conversations. The value can be any JSON type: "
            "string, number, boolean, object, or array. "
            "Example: set_state(key='last_run', value='2026-03-20T10:00:00Z') "
            'Returns {"key": "last_run", "stored": true} on success. '
            "Special keys: '__soul__' (your identity), '__goals__' (your objectives), "
            "'__heartbeat_instructions__' (what to do on next heartbeat wake)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key name to store under (e.g. 'config', 'last_run', '__goals__')",
                },
                "value": {
                    "description": (
                        "Value to store. Any JSON type: string, number, boolean, "
                        "object {}, or array []"
                    ),
                },
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "list_state_keys",
        "description": (
            "List all keys stored in your persistent memory. Use this to discover "
            "what you have saved. Takes no arguments. "
            'Returns {"keys": ["key1", "key2", ...], "count": 5, '
            '"total_size_bytes": 2048}.'
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "search_state",
        "description": (
            "Search your persistent memory by keyword. Finds keys and values "
            "containing the search term (case-insensitive). Use this when you need "
            "to find something but don't remember the exact key name. "
            "Example: search_state(query='project') "
            'Returns {"matches": [{"key": "my_project", "preview": "...first 100 chars..."}], '
            '"query": "project", "total_searched": 10}.'
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search keyword — matches against key names and values "
                        "(case-insensitive substring match)"
                    ),
                },
            },
            "required": ["query"],
        },
    },
]

PLATFORM_TOOL_NAMES = frozenset(t["name"] for t in PLATFORM_TOOLS)

PUBLIC_SAFE_PLATFORM_TOOLS = frozenset(
    ["get_state", "send_to_channel", "list_state_keys", "search_state"]
)

RESTRICTED_AGENT_TOOLS = frozenset(
    [
        "make_function",
        "update_function",
        "delete_function",
        "make_service",
        "delete_service",
        "lock_function",
        "unlock_function",
        "make_procedure",
        "update_procedure",
        "delete_procedure",
    ]
)


async def build_tool_definitions(
    namespace_id: uuid.UUID,
    db: AsyncSession,
    *,
    public_only: bool = False,
    agent_mode: bool = False,
) -> list[dict]:
    """Build tool definitions from all functions in a namespace + platform tools.

    Tool name format: "{service_name}__{function_name}" (double underscore).

    If public_only=True, only include functions marked public_safe=True
    and a restricted set of platform tools (no set_state).

    If agent_mode=True, exclude function management tools (make_function,
    update_function, etc.) from the tool set. This prevents agent AIs from
    authoring or modifying functions during orchestration.
    """
    function_service = FunctionService(db)
    pairs = await function_service.list_all_for_namespace(namespace_id)

    tools: list[dict] = []
    for fn, version in pairs:
        if public_only and not fn.public_safe:
            continue
        service_name = fn.service.name if fn.service else "unknown"
        tool_name = f"{service_name}__{fn.name}"
        if agent_mode and tool_name in RESTRICTED_AGENT_TOOLS:
            continue
        tools.append(
            {
                "name": tool_name,
                "description": fn.description or f"Execute {service_name}.{fn.name}",
                "input_schema": version.input_schema or {"type": "object", "properties": {}},
            }
        )

    if public_only:
        tools.extend(t for t in PLATFORM_TOOLS if t["name"] in PUBLIC_SAFE_PLATFORM_TOOLS)
    else:
        tools.extend(
            t for t in PLATFORM_TOOLS if not (agent_mode and t["name"] in RESTRICTED_AGENT_TOOLS)
        )
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


async def get_procedure_summaries(
    namespace_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """Return procedure summaries for a namespace with covered function refs.

    Each summary: {service, name, description, step_count, covered_functions}
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from mcpworks_api.models.namespace_service import NamespaceService
    from mcpworks_api.models.procedure import Procedure

    result = await db.execute(
        select(Procedure)
        .join(NamespaceService, Procedure.service_id == NamespaceService.id)
        .where(
            Procedure.namespace_id == namespace_id,
            Procedure.is_deleted.is_(False),
        )
        .options(
            selectinload(Procedure.versions),
            selectinload(Procedure.service),
        )
    )
    procedures = result.scalars().all()

    summaries = []
    for proc in procedures:
        version = proc.get_active_version_obj()
        if not version:
            continue
        service_name = proc.service.name if proc.service else "unknown"
        covered = []
        for step in version.steps or []:
            ref = step.get("function_ref", "")
            if ref:
                covered.append(ref)
        summaries.append(
            {
                "service": service_name,
                "name": proc.name,
                "description": proc.description or "",
                "step_count": len(version.steps or []),
                "covered_functions": covered,
            }
        )
    return summaries


def _build_covered_function_set(
    procedure_summaries: list[dict],
) -> dict[str, str]:
    """Map tool names covered by procedures to their procedure name.

    Returns {tool_name: "service / procedure_name"} for annotation.
    """
    covered: dict[str, str] = {}
    for ps in procedure_summaries:
        proc_label = f"{ps['service']} / {ps['name']}"
        for ref in ps.get("covered_functions", []):
            tool_name = ref.replace(".", "__")
            covered[tool_name] = proc_label
    return covered


def augment_system_prompt(
    system_prompt: str | None,
    tools: list[dict],
    procedure_summaries: list[dict] | None = None,
) -> str:
    """Append available tool names to the system prompt.

    AI models may not connect natural function references in the system prompt
    (e.g. 'leads.harvest-leads') to the actual tool names in the tool
    definitions (e.g. 'leads__harvest-leads'). This bridges the gap by
    listing exact callable tool names at the end of the system prompt.

    If procedure_summaries are provided, procedures are listed prominently
    BEFORE tools with a MUST-USE directive.
    """
    procedure_summaries = procedure_summaries or []
    covered = _build_covered_function_set(procedure_summaries)

    ns_tools = [t for t in tools if t["name"] not in PLATFORM_TOOL_NAMES]
    platform = [t for t in tools if t["name"] in PLATFORM_TOOL_NAMES]

    lines = []

    if procedure_summaries:
        lines.append("## Procedures (USE THESE FIRST)")
        lines.append(
            "IMPORTANT: When a procedure exists for the task you are about to do, "
            "you MUST use `run_procedure` instead of calling the underlying functions "
            "directly. Procedures enforce verified step-by-step execution. Calling "
            "raw functions that a procedure covers is a violation — the results "
            "cannot be trusted without procedure enforcement."
        )
        lines.append("")
        for ps in procedure_summaries:
            desc = ps.get("description", "")
            steps = ps.get("step_count", 0)
            lines.append(
                f"- `run_procedure(service='{ps['service']}', "
                f"name='{ps['name']}')` — {desc} ({steps} steps)"
            )
        lines.append("")

    if ns_tools:
        lines.append("## Your callable tools")
        lines.append("Use these EXACT names when making tool calls:")
        for t in ns_tools:
            desc = t.get("description", "")
            hint = ""
            if t["name"] in covered:
                hint = f" ⚠️ USE PROCEDURE: {covered[t['name']]}"
            lines.append(f"- `{t['name']}` — {desc}{hint}")
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

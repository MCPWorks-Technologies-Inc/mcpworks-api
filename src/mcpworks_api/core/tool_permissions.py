"""Per-agent tool scoping — OWASP LLM06 Excessive Agency defense.

Agents are assigned a tool_tier that restricts which MCP tools they can call.
Direct user calls (not via agent) bypass this check — they use account-level
permissions (API key scopes) instead.
"""

from enum import Enum


class ToolTier(str, Enum):
    EXECUTE_ONLY = "execute_only"
    STANDARD = "standard"
    BUILDER = "builder"
    ADMIN = "admin"


_EXECUTE_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "execute",
    }
)

_STANDARD_TOOLS: frozenset[str] = _EXECUTE_ONLY_TOOLS | frozenset(
    {
        "get_agent_state",
        "set_agent_state",
        "delete_agent_state",
        "list_agent_state_keys",
        "list_functions",
        "describe_function",
        "list_services",
        "list_namespaces",
        "list_agents",
        "describe_agent",
        "list_schedules",
        "list_webhooks",
        "list_packages",
        "list_templates",
        "describe_template",
        "chat_with_agent",
        "get_view_url",
    }
)

_BUILDER_TOOLS: frozenset[str] = _STANDARD_TOOLS | frozenset(
    {
        "make_function",
        "update_function",
        "make_service",
        "make_namespace",
        "make_agent",
        "add_schedule",
        "add_webhook",
        "add_channel",
        "configure_agent_ai",
        "configure_mcp_servers",
        "configure_orchestration_limits",
        "configure_heartbeat",
        "lock_function",
        "unlock_function",
        "clone_agent",
        "publish_view",
        "clear_view",
    }
)

_ADMIN_TOOLS: frozenset[str] = _BUILDER_TOOLS | frozenset(
    {
        "delete_function",
        "delete_service",
        "destroy_agent",
        "remove_agent_ai",
        "remove_schedule",
        "remove_webhook",
        "remove_channel",
        "start_agent",
        "stop_agent",
    }
)

TIER_TOOLS: dict[ToolTier, frozenset[str]] = {
    ToolTier.EXECUTE_ONLY: _EXECUTE_ONLY_TOOLS,
    ToolTier.STANDARD: _STANDARD_TOOLS,
    ToolTier.BUILDER: _BUILDER_TOOLS,
    ToolTier.ADMIN: _ADMIN_TOOLS,
}

CONFIRMATION_REQUIRED: frozenset[str] = frozenset(
    {
        "destroy_agent",
        "delete_service",
    }
)

MANAGEMENT_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "make_function": (10, 60),
    "update_function": (20, 60),
    "delete_function": (5, 60),
    "destroy_agent": (2, 3600),
    "delete_service": (2, 3600),
    "configure_agent_ai": (5, 3600),
}


def is_tool_allowed(tool_tier: ToolTier, tool_name: str) -> bool:
    return tool_name in TIER_TOOLS.get(tool_tier, frozenset())


def requires_confirmation(tool_name: str) -> bool:
    return tool_name in CONFIRMATION_REQUIRED

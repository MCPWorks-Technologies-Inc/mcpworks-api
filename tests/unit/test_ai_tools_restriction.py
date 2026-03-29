"""Tests for agent AI tool restrictions — function management tools blocked."""

from mcpworks_api.core.ai_tools import (
    PLATFORM_TOOLS,
    RESTRICTED_AGENT_TOOLS,
)


class TestRestrictedAgentTools:
    def test_restricted_set_contains_expected_tools(self):
        expected = {
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
        }
        assert expected == RESTRICTED_AGENT_TOOLS

    def test_platform_tools_do_not_contain_restricted(self):
        platform_names = {t["name"] for t in PLATFORM_TOOLS}
        overlap = platform_names & RESTRICTED_AGENT_TOOLS
        assert not overlap, f"Platform tools should not contain restricted tools: {overlap}"

    def test_restricted_tools_are_frozen(self):
        assert isinstance(RESTRICTED_AGENT_TOOLS, frozenset)

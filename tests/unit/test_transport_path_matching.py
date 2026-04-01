"""Unit tests for MCPTransportMiddleware path matching logic.

Tests the _is_mcp_protocol_path function directly. Uses importlib.reload
to re-import transport with mocked MCP SDK dependencies, avoiding
Prometheus duplicate registration issues.
"""

import importlib
import sys
from unittest.mock import MagicMock

_MOCK_MODULES = [
    "mcp",
    "mcp.server",
    "mcp.server.streamable_http_manager",
    "mcp.types",
]
_saved = {}
for mod_name in _MOCK_MODULES:
    _saved[mod_name] = sys.modules.get(mod_name)
    sys.modules[mod_name] = MagicMock()

try:
    import mcpworks_api.mcp.transport as _transport_mod

    _transport_mod = importlib.reload(_transport_mod)
    _is_mcp_protocol_path = _transport_mod._is_mcp_protocol_path
finally:
    for mod_name in _MOCK_MODULES:
        if _saved[mod_name] is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = _saved[mod_name]


class TestIsMcpProtocolPath:
    """Tests for _is_mcp_protocol_path helper."""

    def test_legacy_mcp_post(self):
        assert _is_mcp_protocol_path("/mcp", "POST") is True

    def test_legacy_mcp_slash_post(self):
        assert _is_mcp_protocol_path("/mcp/", "POST") is True

    def test_legacy_mcp_delete(self):
        assert _is_mcp_protocol_path("/mcp", "DELETE") is True

    def test_legacy_mcp_get_is_discovery(self):
        """GET /mcp should NOT be intercepted — it's the discovery endpoint."""
        assert _is_mcp_protocol_path("/mcp", "GET") is False

    def test_legacy_mcp_slash_get_is_discovery(self):
        assert _is_mcp_protocol_path("/mcp/", "GET") is False

    def test_path_create_post(self):
        assert _is_mcp_protocol_path("/mcp/create/acme", "POST") is True

    def test_path_run_post(self):
        assert _is_mcp_protocol_path("/mcp/run/myns", "POST") is True

    def test_path_agent_post(self):
        assert _is_mcp_protocol_path("/mcp/agent/mybot", "POST") is True

    def test_path_create_get_sse(self):
        """GET on path-based MCP endpoint = SSE reconnection."""
        assert _is_mcp_protocol_path("/mcp/create/acme", "GET") is True

    def test_path_run_delete(self):
        assert _is_mcp_protocol_path("/mcp/run/acme", "DELETE") is True

    def test_path_trailing_slash(self):
        assert _is_mcp_protocol_path("/mcp/create/acme/", "POST") is True

    def test_agent_webhook_not_intercepted(self):
        assert _is_mcp_protocol_path("/mcp/agent/mybot/webhook/github", "POST") is False

    def test_agent_webhook_deep_path_not_intercepted(self):
        assert _is_mcp_protocol_path("/mcp/agent/mybot/webhook/github/push", "POST") is False

    def test_agent_chat_not_intercepted(self):
        assert _is_mcp_protocol_path("/mcp/agent/mybot/chat/tok123", "POST") is False

    def test_agent_view_not_intercepted(self):
        assert _is_mcp_protocol_path("/mcp/agent/mybot/view/tok123/", "GET") is False

    def test_agent_view_subpath_not_intercepted(self):
        assert _is_mcp_protocol_path("/mcp/agent/mybot/view/tok123/style.css", "GET") is False

    def test_non_mcp_path(self):
        assert _is_mcp_protocol_path("/v1/health", "GET") is False

    def test_root_path(self):
        assert _is_mcp_protocol_path("/", "GET") is False

    def test_invalid_endpoint_not_intercepted(self):
        assert _is_mcp_protocol_path("/mcp/invalid/ns", "POST") is False

    def test_empty_method(self):
        """Method defaults to empty string — should still work for path-based."""
        assert _is_mcp_protocol_path("/mcp/create/acme", "") is True
        assert _is_mcp_protocol_path("/mcp", "") is True

    def test_only_endpoint_no_namespace(self):
        """/mcp/create has only 3 segments — not a valid MCP protocol path."""
        assert _is_mcp_protocol_path("/mcp/create", "POST") is False

    def test_too_many_segments_non_agent(self):
        """/mcp/create/ns/extra should not match (4+ segments for non-agent)."""
        assert _is_mcp_protocol_path("/mcp/create/ns/extra", "POST") is False

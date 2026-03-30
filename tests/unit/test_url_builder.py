"""Unit tests for url_builder module."""

from unittest.mock import MagicMock, patch


def _mock_settings(base_domain="mcpworks.io", base_scheme="https", routing_mode="path"):
    s = MagicMock()
    s.base_domain = base_domain
    s.base_scheme = base_scheme
    s.routing_mode = routing_mode
    return s


class TestUrlBuilderPathMode:
    """Tests for url_builder in path-based routing mode (default)."""

    def test_create_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import create_url

            assert create_url("demo") == "https://api.mcpworks.io/mcp/create/demo"

    def test_run_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import run_url

            assert run_url("demo") == "https://api.mcpworks.io/mcp/run/demo"

    def test_agent_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import agent_url

            assert agent_url("bot") == "https://api.mcpworks.io/mcp/agent/bot"

    def test_mcp_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import mcp_url

            assert mcp_url("demo", "run") == "https://api.mcpworks.io/mcp/run/demo"
            assert mcp_url("demo", "create") == "https://api.mcpworks.io/mcp/create/demo"

    def test_api_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import api_url

            assert api_url() == "https://api.mcpworks.io"
            assert api_url("/v1/health") == "https://api.mcpworks.io/v1/health"

    def test_view_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import view_url

            assert view_url("bot", "tok123") == "https://api.mcpworks.io/mcp/agent/bot/view/tok123/"

    def test_chat_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import chat_url

            assert chat_url("bot", "tok123") == "https://api.mcpworks.io/mcp/agent/bot/chat/tok123"

    def test_webhook_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import webhook_url

            assert (
                webhook_url("bot", "github/push")
                == "https://api.mcpworks.io/mcp/agent/bot/webhook/github/push"
            )

    def test_valid_suffixes_path_mode(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import valid_suffixes

            valid_suffixes.cache_clear()
            result = valid_suffixes()
            assert "/mcp/create/" in result
            assert "/mcp/run/" in result
            assert "/mcp/agent/" in result


class TestUrlBuilderSubdomainMode:
    """Tests for url_builder in subdomain routing mode (legacy)."""

    def test_create_url(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings(routing_mode="subdomain"),
        ):
            from mcpworks_api.url_builder import create_url

            assert create_url("demo") == "https://demo.create.mcpworks.io"

    def test_run_url(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings(routing_mode="subdomain"),
        ):
            from mcpworks_api.url_builder import run_url

            assert run_url("demo") == "https://demo.run.mcpworks.io"

    def test_agent_url(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings(routing_mode="subdomain"),
        ):
            from mcpworks_api.url_builder import agent_url

            assert agent_url("bot") == "https://bot.agent.mcpworks.io"

    def test_mcp_url(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings(routing_mode="subdomain"),
        ):
            from mcpworks_api.url_builder import mcp_url

            assert mcp_url("demo", "run") == "https://demo.run.mcpworks.io/mcp"
            assert mcp_url("demo", "create") == "https://demo.create.mcpworks.io/mcp"

    def test_view_url(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings(routing_mode="subdomain"),
        ):
            from mcpworks_api.url_builder import view_url

            assert view_url("bot", "tok123") == "https://bot.agent.mcpworks.io/view/tok123/"

    def test_chat_url(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings(routing_mode="subdomain"),
        ):
            from mcpworks_api.url_builder import chat_url

            assert chat_url("bot", "tok123") == "https://bot.agent.mcpworks.io/chat/tok123"

    def test_webhook_url(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings(routing_mode="subdomain"),
        ):
            from mcpworks_api.url_builder import webhook_url

            assert (
                webhook_url("bot", "github/push")
                == "https://bot.agent.mcpworks.io/webhook/github/push"
            )

    def test_valid_suffixes_subdomain_mode(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings(routing_mode="subdomain"),
        ):
            from mcpworks_api.url_builder import valid_suffixes

            valid_suffixes.cache_clear()
            result = valid_suffixes()
            assert ".create.mcpworks.io" in result
            assert ".run.mcpworks.io" in result
            assert ".agent.mcpworks.io" in result


class TestUrlBuilderBothMode:
    """Tests for url_builder in 'both' routing mode — path takes precedence."""

    def test_create_url_uses_path(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings(routing_mode="both"),
        ):
            from mcpworks_api.url_builder import create_url

            assert create_url("demo") == "https://api.mcpworks.io/mcp/create/demo"


class TestUrlBuilderCustomDomain:
    def test_create_url_custom(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings("selfhost.dev", routing_mode="path"),
        ):
            from mcpworks_api.url_builder import create_url

            assert create_url("demo") == "https://api.selfhost.dev/mcp/create/demo"

    def test_create_url_custom_subdomain(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings("selfhost.dev", routing_mode="subdomain"),
        ):
            from mcpworks_api.url_builder import create_url

            assert create_url("demo") == "https://demo.create.selfhost.dev"


class TestUrlBuilderHttpScheme:
    def test_urls_use_http_path_mode(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings("localhost", "http", routing_mode="path"),
        ):
            from mcpworks_api.url_builder import api_url, create_url

            assert create_url("demo") == "http://api.localhost/mcp/create/demo"
            assert api_url() == "http://api.localhost"

    def test_urls_use_http_subdomain_mode(self):
        with patch(
            "mcpworks_api.url_builder._settings",
            return_value=_mock_settings("localhost", "http", routing_mode="subdomain"),
        ):
            from mcpworks_api.url_builder import api_url, create_url

            assert create_url("demo") == "http://demo.create.localhost"
            assert api_url() == "http://api.localhost"

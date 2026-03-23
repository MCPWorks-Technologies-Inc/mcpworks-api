"""Unit tests for url_builder module."""

from unittest.mock import MagicMock, patch


def _mock_settings(base_domain="mcpworks.io", base_scheme="https"):
    s = MagicMock()
    s.base_domain = base_domain
    s.base_scheme = base_scheme
    return s


class TestUrlBuilderDefault:
    def test_create_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import create_url

            assert create_url("demo") == "https://demo.create.mcpworks.io"

    def test_run_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import run_url

            assert run_url("demo") == "https://demo.run.mcpworks.io"

    def test_agent_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import agent_url

            assert agent_url("bot") == "https://bot.agent.mcpworks.io"

    def test_mcp_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import mcp_url

            assert mcp_url("demo", "run") == "https://demo.run.mcpworks.io/mcp"
            assert mcp_url("demo", "create") == "https://demo.create.mcpworks.io/mcp"

    def test_api_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import api_url

            assert api_url() == "https://api.mcpworks.io"
            assert api_url("/v1/health") == "https://api.mcpworks.io/v1/health"

    def test_view_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import view_url

            assert view_url("bot", "tok123") == "https://bot.agent.mcpworks.io/view/tok123/"

    def test_chat_url(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import chat_url

            assert chat_url("bot", "tok123") == "https://bot.agent.mcpworks.io/chat/tok123"

    def test_valid_suffixes(self):
        with patch("mcpworks_api.url_builder._settings", return_value=_mock_settings()):
            from mcpworks_api.url_builder import valid_suffixes

            valid_suffixes.cache_clear()
            result = valid_suffixes()
            assert ".create.mcpworks.io" in result
            assert ".run.mcpworks.io" in result
            assert ".agent.mcpworks.io" in result


class TestUrlBuilderCustomDomain:
    def test_create_url_custom(self):
        with patch(
            "mcpworks_api.url_builder._settings", return_value=_mock_settings("selfhost.dev")
        ):
            from mcpworks_api.url_builder import create_url

            assert create_url("demo") == "https://demo.create.selfhost.dev"

    def test_run_url_custom(self):
        with patch(
            "mcpworks_api.url_builder._settings", return_value=_mock_settings("selfhost.dev")
        ):
            from mcpworks_api.url_builder import run_url

            assert run_url("demo") == "https://demo.run.selfhost.dev"

    def test_agent_url_custom(self):
        with patch(
            "mcpworks_api.url_builder._settings", return_value=_mock_settings("selfhost.dev")
        ):
            from mcpworks_api.url_builder import agent_url

            assert agent_url("bot") == "https://bot.agent.selfhost.dev"

    def test_valid_suffixes_custom(self):
        with patch(
            "mcpworks_api.url_builder._settings", return_value=_mock_settings("selfhost.dev")
        ):
            from mcpworks_api.url_builder import valid_suffixes

            valid_suffixes.cache_clear()
            result = valid_suffixes()
            assert ".create.selfhost.dev" in result
            assert ".run.selfhost.dev" in result
            assert ".agent.selfhost.dev" in result


class TestUrlBuilderHttpScheme:
    def test_urls_use_http(self):
        with patch(
            "mcpworks_api.url_builder._settings", return_value=_mock_settings("localhost", "http")
        ):
            from mcpworks_api.url_builder import api_url, create_url

            assert create_url("demo") == "http://demo.create.localhost"
            assert api_url() == "http://api.localhost"

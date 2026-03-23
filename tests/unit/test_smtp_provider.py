"""Tests for SMTP email provider and provider selection logic."""

from unittest.mock import AsyncMock, patch

import pytest

from mcpworks_api.services.smtp_provider import SmtpProvider


@pytest.fixture
def smtp_provider():
    return SmtpProvider(
        host="smtp.example.com",
        port=587,
        username="user@example.com",
        password="secret",  # pragma: allowlist secret
        from_email="noreply@example.com",
        use_tls=True,
    )


class TestSmtpProvider:
    async def test_send_success(self, smtp_provider):
        with patch(
            "mcpworks_api.services.smtp_provider.aiosmtplib.send", new_callable=AsyncMock
        ) as mock_send:
            result = await smtp_provider.send("dest@example.com", "Test Subject", "<h1>Hello</h1>")

            assert result == "smtp-dest@example.com"
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args
            assert call_kwargs.kwargs["hostname"] == "smtp.example.com"
            assert call_kwargs.kwargs["port"] == 587
            assert call_kwargs.kwargs["username"] == "user@example.com"
            assert call_kwargs.kwargs["password"] == "secret"
            assert call_kwargs.kwargs["start_tls"] is True

    async def test_send_failure_returns_none(self, smtp_provider):
        with patch(
            "mcpworks_api.services.smtp_provider.aiosmtplib.send",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            result = await smtp_provider.send("dest@example.com", "Test Subject", "<h1>Hello</h1>")
            assert result is None

    async def test_send_no_tls(self):
        provider = SmtpProvider(
            host="localhost",
            port=25,
            username="",
            password="",
            from_email="noreply@local.dev",
            use_tls=False,
        )
        with patch("mcpworks_api.services.smtp_provider.aiosmtplib.send", new_callable=AsyncMock):
            result = await provider.send("dest@example.com", "Test", "<p>Hi</p>")
            assert result == "smtp-dest@example.com"


class TestProviderSelection:
    def test_resend_key_selects_resend(self):
        with patch("mcpworks_api.services.email.get_settings") as mock_settings:
            mock_settings.return_value.resend_api_key = "re_test_key"
            mock_settings.return_value.resend_from_email = "noreply@example.com"
            mock_settings.return_value.smtp_host = ""

            from mcpworks_api.services.email import ResendProvider, _get_provider

            provider = _get_provider()
            assert isinstance(provider, ResendProvider)

    def test_smtp_host_selects_smtp(self):
        with patch("mcpworks_api.services.email.get_settings") as mock_settings:
            mock_settings.return_value.resend_api_key = ""
            mock_settings.return_value.smtp_host = "smtp.example.com"
            mock_settings.return_value.smtp_port = 587
            mock_settings.return_value.smtp_username = "user"
            mock_settings.return_value.smtp_password = "pass"
            mock_settings.return_value.smtp_from_email = "noreply@example.com"
            mock_settings.return_value.resend_from_email = "fallback@example.com"
            mock_settings.return_value.smtp_use_tls = True

            from mcpworks_api.services.email import _get_provider

            provider = _get_provider()
            assert isinstance(provider, SmtpProvider)

    def test_neither_selects_console(self):
        with patch("mcpworks_api.services.email.get_settings") as mock_settings:
            mock_settings.return_value.resend_api_key = ""
            mock_settings.return_value.smtp_host = ""

            from mcpworks_api.services.email import ConsoleProvider, _get_provider

            provider = _get_provider()
            assert isinstance(provider, ConsoleProvider)

    def test_smtp_falls_back_to_resend_from_email(self):
        with patch("mcpworks_api.services.email.get_settings") as mock_settings:
            mock_settings.return_value.resend_api_key = ""
            mock_settings.return_value.smtp_host = "smtp.example.com"
            mock_settings.return_value.smtp_port = 587
            mock_settings.return_value.smtp_username = "user"
            mock_settings.return_value.smtp_password = "pass"
            mock_settings.return_value.smtp_from_email = ""
            mock_settings.return_value.resend_from_email = "fallback@example.com"
            mock_settings.return_value.smtp_use_tls = True

            from mcpworks_api.services.email import _get_provider

            provider = _get_provider()
            assert isinstance(provider, SmtpProvider)
            assert provider.from_email == "fallback@example.com"

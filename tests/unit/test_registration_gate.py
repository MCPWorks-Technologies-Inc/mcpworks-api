"""Unit tests for registration gate (ALLOW_REGISTRATION setting)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_registration_disabled_returns_403():
    mock_settings = MagicMock()
    mock_settings.allow_registration = False

    with patch("mcpworks_api.api.v1.auth.get_settings", return_value=mock_settings):
        from mcpworks_api.api.v1.auth import register

        request = MagicMock()
        body = MagicMock()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await register(request=request, body=body, db=db)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "registration_disabled"


@pytest.mark.asyncio
async def test_registration_enabled_does_not_block():
    mock_settings = MagicMock()
    mock_settings.allow_registration = True

    with (
        patch("mcpworks_api.api.v1.auth.get_settings", return_value=mock_settings),
        patch("mcpworks_api.api.v1.auth._get_client_ip", return_value="127.0.0.1"),
        patch("mcpworks_api.api.v1.auth.AuthService") as mock_auth_cls,
    ):
        mock_auth = AsyncMock()
        mock_auth.register.return_value = MagicMock(
            id="test-id", email="test@example.com", status="pending_approval"
        )
        mock_auth_cls.return_value = mock_auth

        from mcpworks_api.api.v1.auth import register

        request = MagicMock()
        request.headers.get.return_value = "test-agent"
        body = MagicMock()
        body.email = "test@example.com"
        body.password = "testpass123"  # pragma: allowlist secret
        body.name = "Test"
        body.accepted_terms = True
        db = AsyncMock()

        result = await register(request=request, body=body, db=db)
        assert result is not None

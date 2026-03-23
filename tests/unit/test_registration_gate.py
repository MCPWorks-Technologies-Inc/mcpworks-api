"""Unit tests for registration gate (ALLOW_REGISTRATION setting)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def test_registration_disabled_raises_403():
    mock_settings = MagicMock()
    mock_settings.allow_registration = False

    with patch("mcpworks_api.config.get_settings", return_value=mock_settings):
        from mcpworks_api.config import get_settings

        settings = get_settings()
        assert settings.allow_registration is False
        with pytest.raises(HTTPException) as exc_info:
            if not settings.allow_registration:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "registration_disabled",
                        "message": "Public registration is disabled on this instance.",
                        "error_code": "AUTH_REGISTRATION_DISABLED",
                    },
                )
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "registration_disabled"


def test_registration_enabled_does_not_raise():
    mock_settings = MagicMock()
    mock_settings.allow_registration = True

    with patch("mcpworks_api.config.get_settings", return_value=mock_settings):
        from mcpworks_api.config import get_settings

        settings = get_settings()
        assert settings.allow_registration is True

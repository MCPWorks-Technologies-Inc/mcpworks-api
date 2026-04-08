"""Tests for the namespace telemetry webhook service."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcpworks_api.services.telemetry import (
    _build_event_payload,
    _deliver_webhook,
    sign_payload,
    validate_webhook_url,
)


class TestSignPayload:
    def test_sha256_hmac(self):
        payload = b'{"event":"tool_call","data":{}}'
        secret = "test-secret-123"
        result = sign_payload(payload, secret)
        expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert result == expected

    def test_different_secrets_produce_different_signatures(self):
        payload = b'{"event":"tool_call"}'
        sig1 = sign_payload(payload, "secret-a")
        sig2 = sign_payload(payload, "secret-b")
        assert sig1 != sig2

    def test_known_test_vector(self):
        payload = b"hello"
        secret = "key"
        result = sign_payload(payload, secret)
        expected_hex = hmac.new(b"key", b"hello", hashlib.sha256).hexdigest()
        assert result == f"sha256={expected_hex}"


class TestValidateWebhookUrl:
    def test_https_accepted(self):
        assert validate_webhook_url("https://example.com/webhook") is None

    def test_http_rejected_for_remote(self):
        error = validate_webhook_url("http://example.com/webhook")
        assert error is not None
        assert "HTTPS" in error or "HTTP" in error

    def test_http_allowed_for_localhost(self):
        assert validate_webhook_url("http://localhost:8080/webhook") is None
        assert validate_webhook_url("http://127.0.0.1:9000/hook") is None

    def test_private_ip_rejected(self):
        assert validate_webhook_url("https://10.0.0.1/hook") is not None
        assert validate_webhook_url("https://172.16.0.1/hook") is not None
        assert validate_webhook_url("https://192.168.1.1/hook") is not None

    def test_public_ip_accepted(self):
        assert validate_webhook_url("https://8.8.8.8/hook") is None

    def test_malformed_url_rejected(self):
        assert validate_webhook_url("not-a-url") is not None
        assert validate_webhook_url("ftp://example.com") is not None
        assert validate_webhook_url("") is not None

    def test_no_hostname_rejected(self):
        assert validate_webhook_url("https://") is not None


class TestBuildEventPayload:
    def test_builds_correct_structure(self):
        payload = _build_event_payload(
            namespace_name="my-ns",
            function_name="social.post",
            execution_id="exec-123",
            execution_time_ms=500,
            success=True,
            backend="code_sandbox",
            version=3,
        )
        assert payload["event"] == "tool_call"
        assert payload["namespace"] == "my-ns"
        assert payload["data"]["function"] == "social.post"
        assert payload["data"]["execution_id"] == "exec-123"
        assert payload["data"]["execution_time_ms"] == 500
        assert payload["data"]["success"] is True
        assert payload["data"]["backend"] == "code_sandbox"
        assert payload["data"]["version"] == 3
        assert "timestamp" in payload["data"]

    def test_defaults_for_missing_fields(self):
        payload = _build_event_payload(
            namespace_name="ns",
            function_name="fn",
            execution_id="id",
            execution_time_ms=0,
            success=False,
        )
        assert payload["data"]["backend"] == "unknown"
        assert payload["data"]["version"] == 0

    def test_no_user_data_in_payload(self):
        payload = _build_event_payload(
            namespace_name="ns",
            function_name="fn",
            execution_id="id",
            execution_time_ms=100,
            success=True,
        )
        payload_str = json.dumps(payload)
        assert "input" not in payload_str.lower() or "input_data" not in payload_str
        assert "output" not in payload_str.lower() or "result_data" not in payload_str
        assert "error_message" not in payload_str
        assert "stderr" not in payload_str


class TestDeliverWebhook:
    @pytest.mark.asyncio
    async def test_delivers_post_with_signature(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            payload = b'{"event":"tool_call"}'
            await _deliver_webhook("https://example.com/hook", payload, "secret")

            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args
            headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
            assert "X-MCPWorks-Signature" in headers

    @pytest.mark.asyncio
    async def test_delivers_without_signature_when_no_secret(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            payload = b'{"event":"tool_call"}'
            await _deliver_webhook("https://example.com/hook", payload, None)

            call_kwargs = mock_client.post.call_args
            headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
            assert "X-MCPWorks-Signature" not in headers

    @pytest.mark.asyncio
    async def test_error_does_not_raise(self):
        with patch("httpx.AsyncClient", side_effect=Exception("connection refused")):
            await _deliver_webhook("https://down.example.com/hook", b"{}", None)


class TestBufferEvent:
    @pytest.mark.asyncio
    async def test_buffers_to_redis(self):
        mock_redis = AsyncMock()
        mock_redis.lpush = AsyncMock()
        mock_redis.expire = AsyncMock()

        async def fake_get_redis():
            return mock_redis

        with patch(
            "mcpworks_api.core.redis.get_redis",
            side_effect=fake_get_redis,
        ):
            from mcpworks_api.services.telemetry import _buffer_event

            result = await _buffer_event("ns-id-123", b'{"event":"tool_call"}')
            assert result is True
            mock_redis.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_redis_unavailable(self):
        async def fake_get_redis():
            return None

        with patch(
            "mcpworks_api.core.redis.get_redis",
            side_effect=fake_get_redis,
        ):
            from mcpworks_api.services.telemetry import _buffer_event

            result = await _buffer_event("ns-id-123", b'{"event":"tool_call"}')
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_redis_error(self):
        async def fake_get_redis():
            raise Exception("redis down")

        with patch(
            "mcpworks_api.core.redis.get_redis",
            side_effect=fake_get_redis,
        ):
            from mcpworks_api.services.telemetry import _buffer_event

            result = await _buffer_event("ns-id-123", b'{"event":"tool_call"}')
            assert result is False

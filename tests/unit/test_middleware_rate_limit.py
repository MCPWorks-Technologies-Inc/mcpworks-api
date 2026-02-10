"""Unit tests for RateLimitMiddleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.datastructures import URL, Headers

from mcpworks_api.middleware.rate_limit import (
    RateLimitMiddleware,
    check_auth_rate_limit,
)


class MockClient:
    """Mock client for request."""

    def __init__(self, host="127.0.0.1"):
        self.host = host


class MockRequest:
    """Mock request for testing."""

    def __init__(self, path="/v1/test", headers=None, client_ip="127.0.0.1"):
        self.url = URL(f"http://test{path}")
        self.headers = Headers(headers or {})
        self.client = MockClient(client_ip)


class MockResponse:
    """Mock response for testing."""

    def __init__(self, status_code=200):
        self.status_code = status_code


@pytest.fixture
def rate_limit_middleware():
    """Create rate limit middleware instance."""
    return RateLimitMiddleware(app=MagicMock())


class TestRateLimitMiddlewareLimits:
    """Tests for rate limit configuration."""

    def test_auth_failure_limit_defined(self, rate_limit_middleware):
        """Test auth failure limit exists."""
        config = rate_limit_middleware.LIMITS["auth_failure"]
        assert config["limit"] == 5
        assert config["window"] == 60

    def test_auth_attempt_limit_defined(self, rate_limit_middleware):
        """Test auth attempt limit exists."""
        config = rate_limit_middleware.LIMITS["auth_attempt"]
        assert config["limit"] == 20
        assert config["window"] == 60

    def test_user_request_limit_defined(self, rate_limit_middleware):
        """Test user request limit exists."""
        config = rate_limit_middleware.LIMITS["user_request"]
        assert config["limit"] == 1000
        assert config["window"] == 3600

    def test_ip_request_limit_defined(self, rate_limit_middleware):
        """Test IP request limit exists."""
        config = rate_limit_middleware.LIMITS["ip_request"]
        assert config["limit"] == 100
        assert config["window"] == 3600


class TestRateLimitMiddlewareDispatch:
    """Tests for dispatch method."""

    @pytest.mark.asyncio
    async def test_dispatch_skips_health_endpoints(self, rate_limit_middleware):
        """Test that health endpoints skip rate limiting."""
        request = MockRequest(path="/v1/health")
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await rate_limit_middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_skips_health_subpaths(self, rate_limit_middleware):
        """Test that health subpaths skip rate limiting."""
        request = MockRequest(path="/v1/health/ready")
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await rate_limit_middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_auth_endpoint_checks_rate_limit(
        self, rate_limit_middleware
    ):
        """Test that auth endpoints are rate limited."""
        request = MockRequest(path="/v1/auth/token")
        call_next = AsyncMock(return_value=MockResponse(200))

        with patch.object(
            rate_limit_middleware, "_check_auth_rate_limit", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = (False, 19)  # Not limited, 19 remaining

            with patch.object(
                rate_limit_middleware,
                "_check_auth_failure_limit",
                new_callable=AsyncMock,
            ) as mock_fail_check:
                mock_fail_check.return_value = False

                response = await rate_limit_middleware.dispatch(request, call_next)

                mock_check.assert_called_once()
                mock_fail_check.assert_called_once()
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_returns_429_on_auth_rate_limit(self, rate_limit_middleware):
        """Test that exceeding auth limit returns 429."""
        request = MockRequest(path="/v1/auth/token")
        call_next = AsyncMock()

        with patch.object(
            rate_limit_middleware, "_check_auth_rate_limit", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = (True, 0)  # Limited

            response = await rate_limit_middleware.dispatch(request, call_next)

            assert response.status_code == 429
            call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_returns_429_on_auth_failure_limit(
        self, rate_limit_middleware
    ):
        """Test that too many auth failures returns 429."""
        request = MockRequest(path="/v1/auth/token")
        call_next = AsyncMock()

        with patch.object(
            rate_limit_middleware, "_check_auth_rate_limit", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = (False, 10)  # Not overall limited

            with patch.object(
                rate_limit_middleware,
                "_check_auth_failure_limit",
                new_callable=AsyncMock,
            ) as mock_fail_check:
                mock_fail_check.return_value = True  # But failure limited

                response = await rate_limit_middleware.dispatch(request, call_next)

                assert response.status_code == 429
                call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_records_auth_failure_on_401(self, rate_limit_middleware):
        """Test that 401 responses record auth failure."""
        request = MockRequest(path="/v1/auth/token")
        call_next = AsyncMock(return_value=MockResponse(401))

        with patch.object(
            rate_limit_middleware, "_check_auth_rate_limit", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = (False, 10)

            with patch.object(
                rate_limit_middleware,
                "_check_auth_failure_limit",
                new_callable=AsyncMock,
            ) as mock_fail_check:
                mock_fail_check.return_value = False

                with patch.object(
                    rate_limit_middleware,
                    "_record_auth_failure",
                    new_callable=AsyncMock,
                ) as mock_record:
                    response = await rate_limit_middleware.dispatch(request, call_next)

                    mock_record.assert_called_once()
                    assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_dispatch_no_failure_record_on_200(self, rate_limit_middleware):
        """Test that successful auth doesn't record failure."""
        request = MockRequest(path="/v1/auth/token")
        call_next = AsyncMock(return_value=MockResponse(200))

        with patch.object(
            rate_limit_middleware, "_check_auth_rate_limit", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = (False, 10)

            with patch.object(
                rate_limit_middleware,
                "_check_auth_failure_limit",
                new_callable=AsyncMock,
            ) as mock_fail_check:
                mock_fail_check.return_value = False

                with patch.object(
                    rate_limit_middleware,
                    "_record_auth_failure",
                    new_callable=AsyncMock,
                ) as mock_record:
                    response = await rate_limit_middleware.dispatch(request, call_next)

                    mock_record.assert_not_called()
                    assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_non_auth_endpoints_proceed(self, rate_limit_middleware):
        """Test that non-auth endpoints proceed without auth checks."""
        request = MockRequest(path="/v1/functions")
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await rate_limit_middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)
        assert response.status_code == 200


class TestRateLimitMiddlewareGetClientIP:
    """Tests for _get_client_ip method."""

    def test_get_client_ip_from_forwarded(self, rate_limit_middleware):
        """Test extracting IP from X-Forwarded-For."""
        request = MockRequest(headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})

        ip = rate_limit_middleware._get_client_ip(request)

        assert ip == "1.2.3.4"

    def test_get_client_ip_from_forwarded_single(self, rate_limit_middleware):
        """Test extracting single IP from X-Forwarded-For."""
        request = MockRequest(headers={"X-Forwarded-For": "1.2.3.4"})

        ip = rate_limit_middleware._get_client_ip(request)

        assert ip == "1.2.3.4"

    def test_get_client_ip_from_real_ip(self, rate_limit_middleware):
        """Test extracting IP from X-Real-IP."""
        request = MockRequest(headers={"X-Real-IP": "1.2.3.4"})

        ip = rate_limit_middleware._get_client_ip(request)

        assert ip == "1.2.3.4"

    def test_get_client_ip_prefers_forwarded(self, rate_limit_middleware):
        """Test that X-Forwarded-For takes precedence."""
        request = MockRequest(
            headers={"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"},
            client_ip="9.10.11.12",
        )

        ip = rate_limit_middleware._get_client_ip(request)

        assert ip == "1.2.3.4"

    def test_get_client_ip_from_client(self, rate_limit_middleware):
        """Test extracting IP from client."""
        request = MockRequest(client_ip="192.168.1.1")

        ip = rate_limit_middleware._get_client_ip(request)

        assert ip == "192.168.1.1"

    def test_get_client_ip_unknown_when_no_client(self, rate_limit_middleware):
        """Test that missing client returns 'unknown'."""
        request = MockRequest()
        request.client = None

        ip = rate_limit_middleware._get_client_ip(request)

        assert ip == "unknown"


class TestRateLimitMiddlewareCheckAuthRateLimit:
    """Tests for _check_auth_rate_limit method."""

    @pytest.mark.asyncio
    async def test_check_auth_rate_limit_not_limited(self, rate_limit_middleware):
        """Test check when not rate limited."""
        with patch(
            "mcpworks_api.middleware.rate_limit.get_redis_context"
        ) as mock_ctx:
            mock_redis = AsyncMock()
            mock_limiter = MagicMock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 5))
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            with patch(
                "mcpworks_api.middleware.rate_limit.RateLimiter"
            ) as mock_limiter_class:
                mock_limiter_class.return_value = mock_limiter

                is_limited, remaining = await rate_limit_middleware._check_auth_rate_limit(
                    "1.2.3.4"
                )

                assert is_limited is False
                assert remaining == 15  # 20 limit - 5 used

    @pytest.mark.asyncio
    async def test_check_auth_rate_limit_limited(self, rate_limit_middleware):
        """Test check when rate limited."""
        with patch(
            "mcpworks_api.middleware.rate_limit.get_redis_context"
        ) as mock_ctx:
            mock_redis = AsyncMock()
            mock_limiter = MagicMock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(True, 25))
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            with patch(
                "mcpworks_api.middleware.rate_limit.RateLimiter"
            ) as mock_limiter_class:
                mock_limiter_class.return_value = mock_limiter

                is_limited, remaining = await rate_limit_middleware._check_auth_rate_limit(
                    "1.2.3.4"
                )

                assert is_limited is True
                assert remaining == 0  # Max(0, 20 - 25)


class TestRateLimitMiddlewareRecordAuthFailure:
    """Tests for _record_auth_failure method."""

    @pytest.mark.asyncio
    async def test_record_auth_failure(self, rate_limit_middleware):
        """Test recording auth failure."""
        with patch(
            "mcpworks_api.middleware.rate_limit.get_redis_context"
        ) as mock_ctx:
            mock_redis = AsyncMock()
            mock_limiter = MagicMock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 1))
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            with patch(
                "mcpworks_api.middleware.rate_limit.RateLimiter"
            ) as mock_limiter_class:
                mock_limiter_class.return_value = mock_limiter

                await rate_limit_middleware._record_auth_failure("1.2.3.4")

                mock_limiter.is_rate_limited.assert_called_once()


class TestRateLimitMiddlewareCheckAuthFailureLimit:
    """Tests for _check_auth_failure_limit method."""

    @pytest.mark.asyncio
    async def test_check_auth_failure_limit_not_limited(self, rate_limit_middleware):
        """Test check when not failure limited."""
        with patch(
            "mcpworks_api.middleware.rate_limit.get_redis_context"
        ) as mock_ctx:
            mock_redis = AsyncMock()
            mock_limiter = MagicMock()
            mock_limiter.check_rate_limited = AsyncMock(return_value=(False, 2))
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            with patch(
                "mcpworks_api.middleware.rate_limit.RateLimiter"
            ) as mock_limiter_class:
                mock_limiter_class.return_value = mock_limiter

                is_limited = await rate_limit_middleware._check_auth_failure_limit(
                    "1.2.3.4"
                )

                assert is_limited is False

    @pytest.mark.asyncio
    async def test_check_auth_failure_limit_limited(self, rate_limit_middleware):
        """Test check when failure limited."""
        with patch(
            "mcpworks_api.middleware.rate_limit.get_redis_context"
        ) as mock_ctx:
            mock_redis = AsyncMock()
            mock_limiter = MagicMock()
            mock_limiter.check_rate_limited = AsyncMock(return_value=(True, 5))
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            with patch(
                "mcpworks_api.middleware.rate_limit.RateLimiter"
            ) as mock_limiter_class:
                mock_limiter_class.return_value = mock_limiter

                is_limited = await rate_limit_middleware._check_auth_failure_limit(
                    "1.2.3.4"
                )

                assert is_limited is True


class TestRateLimitMiddlewareRateLimitResponse:
    """Tests for _rate_limit_response method."""

    def test_rate_limit_response_format(self, rate_limit_middleware):
        """Test rate limit response format."""
        response = rate_limit_middleware._rate_limit_response(
            limit=10, window="1 minute", retry_after=60
        )

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"

    def test_rate_limit_response_body(self, rate_limit_middleware):
        """Test rate limit response body content."""
        response = rate_limit_middleware._rate_limit_response(
            limit=10, window="1 hour", retry_after=3600
        )

        # Response body is stored in the body attribute for JSONResponse
        import json

        body = json.loads(response.body)
        assert body["error"] == "RATE_LIMIT_EXCEEDED"
        assert "10 requests per 1 hour" in body["message"]
        assert body["details"]["limit"] == 10
        assert body["details"]["window"] == "1 hour"
        assert body["details"]["retry_after"] == 3600


class TestCheckAuthRateLimitDependency:
    """Tests for check_auth_rate_limit dependency function."""

    @pytest.mark.asyncio
    async def test_check_auth_rate_limit_not_limited(self):
        """Test dependency when not rate limited."""
        request = MockRequest()

        with patch(
            "mcpworks_api.middleware.rate_limit.get_redis_context"
        ) as mock_ctx:
            mock_redis = AsyncMock()
            mock_limiter = MagicMock()
            mock_limiter.check_rate_limited = AsyncMock(return_value=(False, 2))
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            with patch(
                "mcpworks_api.middleware.rate_limit.RateLimiter"
            ) as mock_limiter_class:
                mock_limiter_class.return_value = mock_limiter

                # Should not raise
                await check_auth_rate_limit(request)

    @pytest.mark.asyncio
    async def test_check_auth_rate_limit_raises_when_limited(self):
        """Test dependency raises when rate limited."""
        from mcpworks_api.core.exceptions import RateLimitExceededError

        request = MockRequest()

        with patch(
            "mcpworks_api.middleware.rate_limit.get_redis_context"
        ) as mock_ctx:
            mock_redis = AsyncMock()
            mock_limiter = MagicMock()
            mock_limiter.check_rate_limited = AsyncMock(return_value=(True, 5))
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            with patch(
                "mcpworks_api.middleware.rate_limit.RateLimiter"
            ) as mock_limiter_class:
                mock_limiter_class.return_value = mock_limiter

                with pytest.raises(RateLimitExceededError):
                    await check_auth_rate_limit(request)

    @pytest.mark.asyncio
    async def test_check_auth_rate_limit_extracts_forwarded_ip(self):
        """Test dependency extracts IP from X-Forwarded-For."""
        request = MockRequest(headers={"X-Forwarded-For": "1.2.3.4"})

        with patch(
            "mcpworks_api.middleware.rate_limit.get_redis_context"
        ) as mock_ctx:
            mock_redis = AsyncMock()
            mock_limiter = MagicMock()
            mock_limiter.check_rate_limited = AsyncMock(return_value=(False, 2))
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            with patch(
                "mcpworks_api.middleware.rate_limit.RateLimiter"
            ) as mock_limiter_class:
                mock_limiter_class.return_value = mock_limiter

                await check_auth_rate_limit(request)

                # Verify correct key was used (contains the IP)
                call_args = mock_limiter.check_rate_limited.call_args
                assert "1.2.3.4" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_check_auth_rate_limit_handles_no_client(self):
        """Test dependency handles missing client."""
        request = MockRequest()
        request.client = None

        with patch(
            "mcpworks_api.middleware.rate_limit.get_redis_context"
        ) as mock_ctx:
            mock_redis = AsyncMock()
            mock_limiter = MagicMock()
            mock_limiter.check_rate_limited = AsyncMock(return_value=(False, 2))
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            with patch(
                "mcpworks_api.middleware.rate_limit.RateLimiter"
            ) as mock_limiter_class:
                mock_limiter_class.return_value = mock_limiter

                await check_auth_rate_limit(request)

                # Should use "unknown" as IP
                call_args = mock_limiter.check_rate_limited.call_args
                assert "unknown" in call_args[0][0]

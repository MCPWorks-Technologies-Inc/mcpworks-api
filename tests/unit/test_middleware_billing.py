"""Unit tests for BillingMiddleware."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from mcpworks_api.middleware.billing import (
    BillingMiddleware,
    get_account_usage,
    reset_account_usage,
)


class MockAccount:
    """Mock account for testing."""

    def __init__(self, account_id=None, tier="free"):
        self.id = account_id or uuid.uuid4()
        self.tier = tier


class MockRequest:
    """Mock request for testing."""

    def __init__(self, endpoint_type=None, account=None):
        self.state = MagicMock()
        self.state.endpoint_type = endpoint_type
        self.state.account = account


class MockResponse:
    """Mock response for testing."""

    def __init__(self, status_code=200):
        self.status_code = status_code


@pytest.fixture
def billing_middleware():
    """Create billing middleware instance."""
    return BillingMiddleware(app=MagicMock())


class TestBillingMiddlewareTierLimits:
    """Tests for tier limit configuration."""

    def test_tier_limits_defined(self, billing_middleware):
        """Test that all expected tiers have limits."""
        assert "free" in billing_middleware.TIER_LIMITS
        assert "founder" in billing_middleware.TIER_LIMITS
        assert "founder_pro" in billing_middleware.TIER_LIMITS
        assert "enterprise" in billing_middleware.TIER_LIMITS

    def test_free_tier_limit(self, billing_middleware):
        """Test free tier limit is 100 per PRICING.md."""
        assert billing_middleware.TIER_LIMITS["free"] == 100

    def test_founder_tier_limit(self, billing_middleware):
        """Test founder tier limit is 1,000 per PRICING.md."""
        assert billing_middleware.TIER_LIMITS["founder"] == 1_000

    def test_founder_pro_tier_limit(self, billing_middleware):
        """Test founder_pro tier limit is 10,000 per PRICING.md."""
        assert billing_middleware.TIER_LIMITS["founder_pro"] == 10_000

    def test_enterprise_tier_limit(self, billing_middleware):
        """Test enterprise tier is capped at 100,000 per ORDER-019."""
        assert billing_middleware.TIER_LIMITS["enterprise"] == 100_000

    def test_default_limit(self, billing_middleware):
        """Test default limit for unknown tiers (matches free tier)."""
        assert billing_middleware.DEFAULT_LIMIT == 100


class TestBillingMiddlewareDispatch:
    """Tests for dispatch method."""

    @pytest.mark.asyncio
    async def test_dispatch_skips_non_run_endpoints(self, billing_middleware):
        """Test that non-run endpoints skip billing."""
        request = MockRequest(endpoint_type="create")
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await billing_middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_skips_no_endpoint_type(self, billing_middleware):
        """Test that requests without endpoint_type skip billing."""
        request = MockRequest(endpoint_type=None)
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await billing_middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_skips_no_account(self, billing_middleware):
        """Test that requests without account skip billing."""
        request = MockRequest(endpoint_type="run", account=None)
        call_next = AsyncMock(return_value=MockResponse(200))

        response = await billing_middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_checks_quota_for_run_endpoint(self, billing_middleware):
        """Test that run endpoints check quota."""
        account = MockAccount(tier="free")
        request = MockRequest(endpoint_type="run", account=account)
        call_next = AsyncMock(return_value=MockResponse(200))

        with patch.object(billing_middleware, "_check_quota", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = (50, 100)  # 50 used, 100 limit

            with patch.object(
                billing_middleware, "_increment_usage", new_callable=AsyncMock
            ) as mock_increment:
                response = await billing_middleware.dispatch(request, call_next)

                mock_check.assert_called_once_with(account)
                mock_increment.assert_called_once_with(account)
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_rejects_quota_exceeded(self, billing_middleware):
        """Test that exceeding quota returns 429."""
        account = MockAccount(tier="free")
        request = MockRequest(endpoint_type="run", account=account)
        call_next = AsyncMock()

        with patch.object(billing_middleware, "_check_quota", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = (500, 500)  # At limit

            with pytest.raises(HTTPException) as exc_info:
                await billing_middleware.dispatch(request, call_next)

            assert exc_info.value.status_code == 429
            assert exc_info.value.detail["code"] == "QUOTA_EXCEEDED"
            assert exc_info.value.detail["usage"] == 500
            assert exc_info.value.detail["limit"] == 500
            call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_allows_enterprise_under_cap(self, billing_middleware):
        """Test that enterprise tier allows usage under 100K cap (ORDER-019)."""
        account = MockAccount(tier="enterprise")
        request = MockRequest(endpoint_type="run", account=account)
        call_next = AsyncMock(return_value=MockResponse(200))

        with patch.object(billing_middleware, "_check_quota", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = (50_000, 100_000)  # Under cap

            with patch.object(billing_middleware, "_increment_usage", new_callable=AsyncMock):
                response = await billing_middleware.dispatch(request, call_next)

                assert response.status_code == 200
                call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_fails_open_on_redis_error(self, billing_middleware):
        """Test that Redis errors fail open (allow request)."""
        account = MockAccount(tier="free")
        request = MockRequest(endpoint_type="run", account=account)
        call_next = AsyncMock(return_value=MockResponse(200))

        with patch.object(billing_middleware, "_check_quota", new_callable=AsyncMock) as mock_check:
            mock_check.side_effect = Exception("Redis error")

            response = await billing_middleware.dispatch(request, call_next)

            # Request should proceed despite Redis error
            call_next.assert_called_once()
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_skips_increment_on_error_response(self, billing_middleware):
        """Test that failed responses don't increment usage."""
        account = MockAccount(tier="free")
        request = MockRequest(endpoint_type="run", account=account)
        call_next = AsyncMock(return_value=MockResponse(400))  # Error response

        with patch.object(billing_middleware, "_check_quota", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = (50, 100)

            with patch.object(
                billing_middleware, "_increment_usage", new_callable=AsyncMock
            ) as mock_increment:
                response = await billing_middleware.dispatch(request, call_next)

                mock_check.assert_called_once()
                mock_increment.assert_not_called()  # Not called for error
                assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_dispatch_handles_increment_error_gracefully(self, billing_middleware):
        """Test that increment errors don't fail the request."""
        account = MockAccount(tier="free")
        request = MockRequest(endpoint_type="run", account=account)
        call_next = AsyncMock(return_value=MockResponse(200))

        with patch.object(billing_middleware, "_check_quota", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = (50, 100)

            with patch.object(
                billing_middleware, "_increment_usage", new_callable=AsyncMock
            ) as mock_increment:
                mock_increment.side_effect = Exception("Redis write error")

                response = await billing_middleware.dispatch(request, call_next)

                # Response should succeed despite increment error
                assert response.status_code == 200


class TestBillingMiddlewareCheckQuota:
    """Tests for _check_quota method."""

    @pytest.mark.asyncio
    async def test_check_quota_free_tier(self, billing_middleware):
        """Test quota check for free tier."""
        account = MockAccount(tier="free")

        with patch("mcpworks_api.middleware.billing.get_redis_context") as mock_ctx:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = "50"
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            usage, limit = await billing_middleware._check_quota(account)

            assert usage == 50
            assert limit == 100  # PRICING.md: 100/mo free tier

    @pytest.mark.asyncio
    async def test_check_quota_founder_tier(self, billing_middleware):
        """Test quota check for founder tier."""
        account = MockAccount(tier="founder")

        with patch("mcpworks_api.middleware.billing.get_redis_context") as mock_ctx:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = "500"
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            usage, limit = await billing_middleware._check_quota(account)

            assert usage == 500
            assert limit == 1_000  # PRICING.md: 1,000/mo founder tier

    @pytest.mark.asyncio
    async def test_check_quota_zero_usage(self, billing_middleware):
        """Test quota check with zero usage (None from Redis)."""
        account = MockAccount(tier="free")

        with patch("mcpworks_api.middleware.billing.get_redis_context") as mock_ctx:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            usage, limit = await billing_middleware._check_quota(account)

            assert usage == 0
            assert limit == 100  # PRICING.md: 100/mo free tier

    @pytest.mark.asyncio
    async def test_check_quota_unknown_tier_uses_default(self, billing_middleware):
        """Test that unknown tiers use default limit."""
        account = MockAccount(tier="unknown_tier")

        with patch("mcpworks_api.middleware.billing.get_redis_context") as mock_ctx:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = "10"
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            usage, limit = await billing_middleware._check_quota(account)

            assert usage == 10
            assert limit == billing_middleware.DEFAULT_LIMIT


class TestBillingMiddlewareIncrementUsage:
    """Tests for _increment_usage method."""

    @pytest.mark.asyncio
    async def test_increment_usage_increments_counter(self, billing_middleware):
        """Test that increment increases counter."""
        account = MockAccount()

        with patch("mcpworks_api.middleware.billing.get_redis_context") as mock_ctx:
            mock_redis = AsyncMock()
            mock_redis.incr.return_value = 5  # Not first usage
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            new_count = await billing_middleware._increment_usage(account)

            mock_redis.incr.assert_called_once()
            assert new_count == 5

    @pytest.mark.asyncio
    async def test_increment_usage_sets_expiry_on_first(self, billing_middleware):
        """Test that first usage sets expiry."""
        account = MockAccount()

        with patch("mcpworks_api.middleware.billing.get_redis_context") as mock_ctx:
            mock_redis = AsyncMock()
            mock_redis.incr.return_value = 1  # First usage
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            new_count = await billing_middleware._increment_usage(account)

            mock_redis.expireat.assert_called_once()
            assert new_count == 1


class TestBillingMiddlewareUsageKey:
    """Tests for _get_usage_key method."""

    def test_usage_key_format(self, billing_middleware):
        """Test usage key format."""
        account_id = uuid.uuid4()
        now = datetime.now(UTC)

        key = billing_middleware._get_usage_key(account_id)

        assert key == f"usage:{account_id}:{now.year}:{now.month}"

    def test_usage_key_includes_month(self, billing_middleware):
        """Test that usage key changes monthly."""
        account_id = uuid.uuid4()

        with patch("mcpworks_api.middleware.billing.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.year = 2025
            mock_now.month = 1
            mock_dt.now.return_value = mock_now

            key_jan = billing_middleware._get_usage_key(account_id)

            mock_now.month = 2
            key_feb = billing_middleware._get_usage_key(account_id)

            assert key_jan != key_feb
            assert "2025:1" in key_jan
            assert "2025:2" in key_feb


class TestBillingMiddlewareEndOfMonth:
    """Tests for _end_of_next_month method."""

    def test_end_of_next_month_returns_timestamp(self, billing_middleware):
        """Test that end_of_next_month returns unix timestamp."""
        expiry = billing_middleware._end_of_next_month()

        # Should be an integer timestamp
        assert isinstance(expiry, int)

        # Should be in the future
        assert expiry > datetime.now(UTC).timestamp()

    def test_end_of_next_month_covers_billing_cycle(self, billing_middleware):
        """Test that expiry covers current + next month."""
        now = datetime.now(UTC)
        expiry = billing_middleware._end_of_next_month()

        # Should be at least 30 days in future (current month minimum)
        min_future = now + timedelta(days=30)
        assert expiry > min_future.timestamp()

        # Should be at most ~62 days in future
        max_future = now + timedelta(days=65)
        assert expiry < max_future.timestamp()


class TestGetAccountUsage:
    """Tests for get_account_usage utility function."""

    @pytest.mark.asyncio
    async def test_get_account_usage_returns_stats(self):
        """Test that get_account_usage returns usage stats."""
        account_id = uuid.uuid4()

        with patch("mcpworks_api.middleware.billing.get_redis_context") as mock_ctx:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = "42"
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            result = await get_account_usage(account_id)

            assert result["account_id"] == str(account_id)
            assert result["usage"] == 42
            assert "year" in result
            assert "month" in result

    @pytest.mark.asyncio
    async def test_get_account_usage_zero_when_none(self):
        """Test that None from Redis returns 0 usage."""
        account_id = uuid.uuid4()

        with patch("mcpworks_api.middleware.billing.get_redis_context") as mock_ctx:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            result = await get_account_usage(account_id)

            assert result["usage"] == 0

    @pytest.mark.asyncio
    async def test_get_account_usage_handles_error(self):
        """Test that errors return error response."""
        account_id = uuid.uuid4()

        with patch("mcpworks_api.middleware.billing.get_redis_context") as mock_ctx:
            mock_ctx.return_value.__aenter__.side_effect = Exception("Redis down")

            result = await get_account_usage(account_id)

            assert result["usage"] == 0
            assert "error" in result


class TestResetAccountUsage:
    """Tests for reset_account_usage utility function."""

    @pytest.mark.asyncio
    async def test_reset_account_usage_deletes_key(self):
        """Test that reset deletes the usage key."""
        account_id = uuid.uuid4()

        with patch("mcpworks_api.middleware.billing.get_redis_context") as mock_ctx:
            mock_redis = AsyncMock()
            mock_ctx.return_value.__aenter__.return_value = mock_redis

            result = await reset_account_usage(account_id)

            mock_redis.delete.assert_called_once()
            assert result is True

    @pytest.mark.asyncio
    async def test_reset_account_usage_handles_error(self):
        """Test that errors return False."""
        account_id = uuid.uuid4()

        with patch("mcpworks_api.middleware.billing.get_redis_context") as mock_ctx:
            mock_ctx.return_value.__aenter__.side_effect = Exception("Redis down")

            result = await reset_account_usage(account_id)

            assert result is False

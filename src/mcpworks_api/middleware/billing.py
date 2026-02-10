"""Billing middleware for usage tracking and quota enforcement.

Tracks executions per account per month and enforces tier-based quotas.
Usage is stored in Redis for fast access.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from mcpworks_api.core.redis import get_redis_context

logger = logging.getLogger(__name__)


class BillingMiddleware(BaseHTTPMiddleware):
    """Track usage and enforce quotas based on account tier.

    Tracks:
    - Monthly execution count per account
    - Credit usage (future)

    Enforces:
    - Monthly execution limits per tier
    - Credit balance (future)
    """

    # Tier limits (executions per month)
    TIER_LIMITS: dict[str, int] = {
        "free": 100,  # Free tier: 100 executions/month
        "founder": 1_000,  # Founder: 1,000 executions/month
        "founder_pro": 5_000,  # Founder Pro: 5,000 executions/month
        "enterprise": 100_000,  # Enterprise: 100,000 executions/month
    }

    # Default limit for unknown tiers
    DEFAULT_LIMIT = 100

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and track usage.

        Only tracks usage for run endpoints (function execution).
        Management operations via create endpoint are not metered.
        """
        # Only track for run endpoint
        endpoint_type = getattr(request.state, "endpoint_type", None)
        if endpoint_type != "run":
            return await call_next(request)

        # Get account from request state (set by auth middleware)
        account = getattr(request.state, "account", None)
        if not account:
            # No account context - let the request proceed
            # (it will likely fail auth later)
            return await call_next(request)

        # Check quota before execution
        try:
            usage, limit = await self._check_quota(account)
            if usage >= limit:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "QUOTA_EXCEEDED",
                        "message": f"Monthly execution limit ({limit}) exceeded",
                        "usage": usage,
                        "limit": limit,
                        "tier": getattr(account, "tier", "free"),
                    },
                )
        except HTTPException:
            raise
        except Exception as e:
            # Redis error - log and allow request (fail-open)
            logger.warning(f"Billing check failed: {e}")

        # Execute request
        response = await call_next(request)

        # Increment usage after successful execution
        if response.status_code < 400:
            try:
                await self._increment_usage(account)
            except Exception as e:
                # Don't fail request due to billing error
                logger.warning(f"Usage tracking failed: {e}")

        return response

    async def _check_quota(self, account: Any) -> tuple[int, int]:
        """Check current usage and limit for account.

        Args:
            account: The account object.

        Returns:
            Tuple of (current_usage, limit).
        """
        tier = getattr(account, "tier", "free")
        limit = self.TIER_LIMITS.get(tier, self.DEFAULT_LIMIT)

        async with get_redis_context() as redis:
            month_key = self._get_usage_key(account.id)
            current_usage = await redis.get(month_key)
            usage = int(current_usage) if current_usage else 0

        return usage, limit

    async def _increment_usage(self, account: Any) -> int:
        """Increment usage counter for account.

        Args:
            account: The account object.

        Returns:
            New usage count.
        """
        async with get_redis_context() as redis:
            month_key = self._get_usage_key(account.id)
            new_count = await redis.incr(month_key)

            if new_count == 1:
                # First usage this month, set expiry
                expiry = self._end_of_next_month()
                await redis.expireat(month_key, expiry)

            return new_count

    def _get_usage_key(self, account_id: Any) -> str:
        """Get Redis key for account's monthly usage.

        Key format: usage:{account_id}:{year}:{month}
        """
        now = datetime.now(UTC)
        return f"usage:{account_id}:{now.year}:{now.month}"

    def _end_of_next_month(self) -> int:
        """Get Unix timestamp for end of next month.

        Returns expiry far enough in the future to cover billing cycle.
        """
        now = datetime.now(UTC)
        # Add 62 days to cover current + next month
        future = now + timedelta(days=62)
        return int(future.timestamp())


async def get_account_usage(account_id: Any) -> dict[str, Any]:
    """Get usage stats for an account (utility function).

    Args:
        account_id: The account ID.

    Returns:
        Dict with usage statistics.
    """
    try:
        async with get_redis_context() as redis:
            now = datetime.now(UTC)
            month_key = f"usage:{account_id}:{now.year}:{now.month}"
            current_usage = await redis.get(month_key)
            usage = int(current_usage) if current_usage else 0

            return {
                "account_id": str(account_id),
                "year": now.year,
                "month": now.month,
                "usage": usage,
            }
    except Exception as e:
        logger.error(f"Failed to get usage: {e}")
        return {
            "account_id": str(account_id),
            "year": datetime.now(UTC).year,
            "month": datetime.now(UTC).month,
            "usage": 0,
            "error": "Unable to retrieve usage data",
        }


async def reset_account_usage(account_id: Any) -> bool:
    """Reset usage counter for an account (admin utility).

    Args:
        account_id: The account ID.

    Returns:
        True if reset successful.
    """
    try:
        async with get_redis_context() as redis:
            now = datetime.now(UTC)
            month_key = f"usage:{account_id}:{now.year}:{now.month}"
            await redis.delete(month_key)
            return True
    except Exception as e:
        logger.error(f"Failed to reset usage: {e}")
        return False

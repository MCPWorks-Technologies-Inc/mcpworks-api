"""Billing middleware for usage tracking and quota enforcement.

Tracks executions per account per month and enforces tier-based quotas.
Usage is stored in Redis for fast access.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from mcpworks_api.core.redis import get_redis_context

logger = structlog.get_logger(__name__)


EXECUTIONS_PER_MINUTE: dict[str, int] = {
    "trial": 100,
    "pro": 100,
    "enterprise": 300,
    "dedicated": 500,
}

MAX_CONCURRENT: dict[str, int] = {
    "trial": 10,
    "pro": 15,
    "enterprise": 50,
    "dedicated": 100,
}

DAILY_COMPUTE_BUDGETS: dict[str, int] = {
    "trial": 3600,
    "pro": 14400,
    "enterprise": 86400,
    "dedicated": 345600,
}

DAILY_EXEC_LIMITS: dict[str, int] = {
    "trial": 5000,
    "pro": 10000,
    "enterprise": 50000,
    "dedicated": -1,
}


async def check_execution_rate(account_id: Any, tier: str) -> None:
    """Pre-execution check: reject if per-minute execution rate exceeded."""
    base_tier = tier.replace("-agent", "") if tier.endswith("-agent") else tier
    rate_limit = EXECUTIONS_PER_MINUTE.get(base_tier, EXECUTIONS_PER_MINUTE["trial"])
    concurrency_limit = MAX_CONCURRENT.get(base_tier, MAX_CONCURRENT["trial"])

    async with get_redis_context() as redis:
        minute_key = f"execrate:{account_id}:{int(datetime.now(UTC).timestamp()) // 60}"
        concurrent_key = f"concurrent:{account_id}"

        current_rate = await redis.get(minute_key)
        if current_rate and int(current_rate) >= rate_limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "EXECUTION_RATE_EXCEEDED",
                    "message": f"Execution rate limit ({rate_limit}/min) exceeded",
                    "tier": tier,
                    "retry_after": 60,
                },
                headers={"Retry-After": "60"},
            )

        current_concurrent = await redis.get(concurrent_key)
        if current_concurrent and int(current_concurrent) >= concurrency_limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "CONCURRENCY_LIMIT_EXCEEDED",
                    "message": f"Concurrency limit ({concurrency_limit}) exceeded",
                    "tier": tier,
                    "retry_after": 5,
                },
                headers={"Retry-After": "5"},
            )

        pipe = redis.pipeline()
        pipe.incr(minute_key)
        pipe.expire(minute_key, 120)
        pipe.incr(concurrent_key)
        pipe.expire(concurrent_key, 600)
        await pipe.execute()


async def release_concurrency(account_id: Any) -> None:
    """Post-execution: decrement concurrency counter."""
    try:
        async with get_redis_context() as redis:
            concurrent_key = f"concurrent:{account_id}"
            current = await redis.decr(concurrent_key)
            if current < 0:
                await redis.set(concurrent_key, 0, ex=600)
    except Exception:
        pass


async def check_daily_budget(account_id: Any, tier: str) -> None:
    """Pre-execution check: reject if daily compute budget exhausted."""
    base_tier = tier.replace("-agent", "") if tier.endswith("-agent") else tier
    budget = DAILY_COMPUTE_BUDGETS.get(base_tier, DAILY_COMPUTE_BUDGETS["trial"])
    daily_limit = DAILY_EXEC_LIMITS.get(base_tier, DAILY_EXEC_LIMITS["trial"])

    now = datetime.now(UTC)
    date_key = now.strftime("%Y-%m-%d")

    async with get_redis_context() as redis:
        compute_key = f"compute:daily:{account_id}:{date_key}"
        exec_key = f"execcount:daily:{account_id}:{date_key}"

        current_compute = await redis.get(compute_key)
        current_execs = await redis.get(exec_key)

        if current_compute and float(current_compute) >= budget:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "DAILY_COMPUTE_BUDGET_EXCEEDED",
                    "message": f"Daily compute budget ({budget}s CPU) exhausted",
                    "tier": tier,
                },
            )
        if daily_limit != -1 and current_execs and int(current_execs) >= daily_limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "DAILY_EXEC_LIMIT_EXCEEDED",
                    "message": f"Daily execution limit ({daily_limit}) reached",
                    "tier": tier,
                },
            )


async def track_compute(account_id: Any, cpu_seconds: float, tier: str) -> None:
    """Post-execution: track CPU-seconds consumed."""
    base_tier = tier.replace("-agent", "") if tier.endswith("-agent") else tier
    budget = DAILY_COMPUTE_BUDGETS.get(base_tier, DAILY_COMPUTE_BUDGETS["trial"])
    date_key = datetime.now(UTC).strftime("%Y-%m-%d")

    async with get_redis_context() as redis:
        compute_key = f"compute:daily:{account_id}:{date_key}"
        exec_key = f"execcount:daily:{account_id}:{date_key}"

        current = await redis.incrbyfloat(compute_key, cpu_seconds)
        await redis.incr(exec_key)

        ttl = await redis.ttl(compute_key)
        if ttl == -1:
            await redis.expire(compute_key, 86400 * 2)
            await redis.expire(exec_key, 86400 * 2)

        if current >= budget:
            logger.warning(
                "daily_compute_budget_exceeded",
                account_id=str(account_id),
                current=current,
                budget=budget,
                tier=tier,
            )
        elif current >= budget * 0.8:
            logger.info(
                "daily_compute_budget_warning",
                account_id=str(account_id),
                current=current,
                budget=budget,
                pct=round(current / budget * 100),
            )


class BillingMiddleware(BaseHTTPMiddleware):
    """Track usage and enforce quotas based on account tier.

    Tracks:
    - Monthly execution count per account
    - Daily compute budgets (CPU-seconds and execution count)

    Enforces:
    - Monthly execution limits per tier
    - Daily compute budgets per tier
    """

    # Tier limits (executions per month) - per PRICING.md v7.0.0
    # -1 means unlimited (fair use)
    TIER_LIMITS: dict[str, int] = {
        "trial": 125_000,
        "pro": 250_000,
        "enterprise": 1_000_000,
        "dedicated": -1,
        "trial-agent": 125_000,
        "pro-agent": 250_000,
        "enterprise-agent": 1_000_000,
        "dedicated-agent": -1,
    }

    # Default limit for unknown tiers
    DEFAULT_LIMIT = 125_000

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and track usage.

        Only tracks usage for run endpoints (function execution).
        Management operations via create endpoint are not metered.
        """
        from mcpworks_api.config import get_settings

        if not get_settings().billing_enabled:
            response = await call_next(request)
            return response

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

        tier = getattr(account, "effective_tier", None) or getattr(account, "tier", "trial")

        # Check quota before execution
        try:
            usage, limit = await self._check_quota(account)
            if limit != -1 and usage >= limit:
                asyncio.create_task(
                    self._log_security_event(
                        "billing.quota_exceeded",
                        "warning",
                        actor_id=str(getattr(account, "id", "")),
                        details={
                            "usage": usage,
                            "limit": limit,
                            "tier": tier,
                        },
                    )
                )
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "QUOTA_EXCEEDED",
                        "message": f"Monthly execution limit ({limit}) exceeded",
                        "usage": usage,
                        "limit": limit,
                        "tier": tier,
                    },
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("billing_check_failed", error=str(e))

        # Check per-minute rate and concurrency limits
        try:
            await check_execution_rate(account.id, tier)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("rate_check_failed", error=str(e))

        # Execute request
        try:
            response = await call_next(request)
        finally:
            asyncio.create_task(release_concurrency(account.id))

        # Increment usage after successful execution
        if response.status_code < 400:
            try:
                await self._increment_usage(account)
            except Exception as e:
                logger.warning("usage_tracking_failed", error=str(e))

        return response

    async def _check_quota(self, account: Any) -> tuple[int, int]:
        """Check current usage and limit for account.

        Args:
            account: The account object.

        Returns:
            Tuple of (current_usage, limit).
        """
        tier = getattr(account, "effective_tier", None) or getattr(account, "tier", "trial")
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

    @staticmethod
    async def _log_security_event(
        event_type: str,
        severity: str,
        actor_ip: str | None = None,
        actor_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        """ORDER-022: Fire-and-forget security event logging."""
        from mcpworks_api.core.database import get_db_context
        from mcpworks_api.services.security_event import fire_security_event

        async with get_db_context() as db:
            await fire_security_event(
                db,
                event_type,
                severity,
                actor_ip=actor_ip,
                actor_id=actor_id,
                details=details,
            )

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
        logger.error("failed_to_get_usage", error=str(e))
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
        logger.error("failed_to_reset_usage", error=str(e))
        return False

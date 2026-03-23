"""Account endpoints - usage tracking and account management."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.redis import get_redis_context
from mcpworks_api.dependencies import ActiveUserId as CurrentUserId
from mcpworks_api.middleware.billing import BillingMiddleware
from mcpworks_api.models import User

router = APIRouter(prefix="/account", tags=["account"])


class UsageResponse(BaseModel):
    """Response for GET /v1/account/usage."""

    executions_count: int = Field(
        ...,
        description="Number of executions used this billing period",
        examples=[42],
    )
    executions_limit: int = Field(
        ...,
        description="Maximum executions allowed per billing period",
        examples=[100],
    )
    executions_remaining: int = Field(
        ...,
        description="Remaining executions this period",
        examples=[58],
    )
    billing_period_start: datetime = Field(
        ...,
        description="Start of current billing period",
    )
    billing_period_end: datetime = Field(
        ...,
        description="End of current billing period",
    )
    tier: str = Field(
        ...,
        description="Current subscription tier",
        examples=["trial", "pro", "enterprise", "dedicated"],
    )


def _get_billing_period() -> tuple[datetime, datetime]:
    """Get current billing period (calendar month)."""
    now = datetime.now(UTC)
    # Start of current month
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Start of next month
    if now.month == 12:
        period_end = period_start.replace(year=now.year + 1, month=1)
    else:
        period_end = period_start.replace(month=now.month + 1)
    return period_start, period_end


@router.get(
    "/usage",
    response_model=UsageResponse,
    responses={
        200: {"description": "Current usage statistics"},
        401: {"description": "Not authenticated"},
    },
)
async def get_usage(
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> UsageResponse:
    """Get current usage statistics for the authenticated user.

    Returns execution count, limits, and billing period information.
    Usage is tracked per calendar month.

    Execution limits by tier:
    - Trial: 125,000/month (14-day)
    - Pro: 250,000/month
    - Enterprise: 1,000,000/month
    - Dedicated: Unlimited (fair use)
    """
    from mcpworks_api.config import get_settings

    if not get_settings().billing_enabled:
        period_start, period_end = _get_billing_period()
        return UsageResponse(
            executions_count=0,
            executions_limit=-1,
            executions_remaining=-1,
            billing_period_start=period_start,
            billing_period_end=period_end,
            tier="self-hosted",
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    tier = user.effective_tier if user else "trial"

    # Get limit for tier
    limit = BillingMiddleware.TIER_LIMITS.get(tier, BillingMiddleware.DEFAULT_LIMIT)

    # Get current usage from Redis
    now = datetime.now(UTC)
    month_key = f"usage:{user_id}:{now.year}:{now.month}"

    try:
        async with get_redis_context() as redis:
            current_usage = await redis.get(month_key)
            usage = int(current_usage) if current_usage else 0
    except Exception:
        # Redis unavailable - return 0 usage (fail-open)
        usage = 0

    remaining = max(0, limit - usage)

    # Get billing period
    period_start, period_end = _get_billing_period()

    return UsageResponse(
        executions_count=usage,
        executions_limit=limit,
        executions_remaining=remaining,
        billing_period_start=period_start,
        billing_period_end=period_end,
        tier=tier,
    )

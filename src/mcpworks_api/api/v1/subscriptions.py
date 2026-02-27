"""Subscription endpoints - Stripe subscription management."""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.redis import get_redis
from mcpworks_api.dependencies import ActiveUserId as CurrentUserId
from mcpworks_api.schemas.subscription import (
    CancelSubscriptionResponse,
    CheckoutSessionResponse,
    CreateSubscriptionRequest,
    SubscriptionInfo,
    WebhookResponse,
)
from mcpworks_api.services.stripe import StripeService

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post(
    "",
    response_model=CheckoutSessionResponse,
    responses={
        200: {"description": "Checkout session created"},
        400: {"description": "Invalid tier or configuration error"},
        401: {"description": "Not authenticated"},
    },
)
async def create_subscription(
    body: CreateSubscriptionRequest,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionResponse:
    """Create a Stripe Checkout session for subscription upgrade.

    FR-BILL-001: Integrate with Stripe for subscription management.
    FR-BILL-002: Support founder, founder_pro, enterprise tiers.
    """
    stripe_service = StripeService(db)

    try:
        result = await stripe_service.create_checkout_session(
            user_id=uuid.UUID(user_id),
            tier=body.tier,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )

        return CheckoutSessionResponse(
            checkout_url=result["checkout_url"],
            session_id=result["session_id"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_REQUEST", "message": str(e)},
        )


@router.get(
    "/current",
    response_model=SubscriptionInfo,
    responses={
        200: {"description": "Current subscription details"},
        401: {"description": "Not authenticated"},
        404: {"description": "No subscription found"},
    },
)
async def get_current_subscription(
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionInfo:
    """Get current subscription details."""
    stripe_service = StripeService(db)

    subscription = await stripe_service.get_subscription(uuid.UUID(user_id))

    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "No subscription found"},
        )

    return SubscriptionInfo(
        tier=subscription.tier,
        status=subscription.status,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        monthly_executions=subscription.monthly_executions,
    )


@router.delete(
    "/current",
    response_model=CancelSubscriptionResponse,
    responses={
        200: {"description": "Subscription cancellation scheduled"},
        400: {"description": "Cannot cancel subscription"},
        401: {"description": "Not authenticated"},
        404: {"description": "No subscription found"},
    },
)
async def cancel_subscription(
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> CancelSubscriptionResponse:
    """Cancel current subscription at end of billing period.

    FR-BILL-001: Subscription marked for cancellation, not immediately deleted.
    User retains access until current billing period ends.
    """
    stripe_service = StripeService(db)

    try:
        result = await stripe_service.cancel_subscription(uuid.UUID(user_id))

        return CancelSubscriptionResponse(
            status=result["status"],
            cancel_at=result["cancel_at"],
            message=result["message"],
        )

    except ValueError as e:
        error_msg = str(e)
        # Check for "No ... found" or "not found" patterns
        if "no subscription found" in error_msg.lower() or "not found" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "NOT_FOUND", "message": error_msg},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "CANNOT_CANCEL", "message": error_msg},
        )


# Webhook endpoint (separate router for no auth)
webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@webhook_router.post(
    "/stripe",
    response_model=WebhookResponse,
    responses={
        200: {"description": "Webhook processed"},
        400: {"description": "Invalid webhook signature"},
    },
)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> WebhookResponse:
    """Handle Stripe webhook events.

    FR-BILL-004: Handle Stripe webhooks for subscription lifecycle events.

    Note: This endpoint uses Stripe signature verification for authentication
    instead of JWT, as it's called by Stripe servers.

    Implements idempotency via Redis to prevent duplicate processing.
    """
    payload = await request.body()
    stripe_service = StripeService(db, redis=redis)

    try:
        result = await stripe_service.handle_webhook_event(payload, stripe_signature)

        return WebhookResponse(
            processed=result["processed"],
            event_type=result["event_type"],
            message=result.get("message"),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_SIGNATURE", "message": str(e)},
        )

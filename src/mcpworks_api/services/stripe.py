"""Stripe service - subscription and payment management."""

import contextlib
import uuid
from datetime import UTC, datetime
from typing import Any

import stripe
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.config import get_settings
from mcpworks_api.models import (
    Subscription,
    SubscriptionStatus,
    User,
)

# Webhook idempotency settings
WEBHOOK_IDEMPOTENCY_PREFIX = "stripe:webhook:processed:"
WEBHOOK_IDEMPOTENCY_TTL = 86400  # 24 hours - Stripe retries for up to 3 days

TIER_PRICE_MAP: dict[str, dict[str, str]] = {}


def get_tier_price_map() -> dict[str, dict[str, str]]:
    """Get tier to price ID mapping from settings.

    Per PRICING.md v7.0.0 (Value Ladder):
    - pro: $179/mo or $1,790/yr
    - enterprise: $599/mo or $5,990/yr
    - dedicated: $999/mo or $9,990/yr
    """
    settings = get_settings()
    return {
        "pro": {
            "monthly": settings.stripe_price_pro_monthly,
            "annual": settings.stripe_price_pro_annual,
        },
        "enterprise": {
            "monthly": settings.stripe_price_enterprise_monthly,
            "annual": settings.stripe_price_enterprise_annual,
        },
        "dedicated": {
            "monthly": settings.stripe_price_dedicated_monthly,
            "annual": settings.stripe_price_dedicated_annual,
        },
    }


TIER_EXECUTIONS = {
    "trial": 125_000,
    "pro": 250_000,
    "enterprise": 1_000_000,
    "dedicated": -1,
    "trial-agent": 125_000,
    "pro-agent": 250_000,
    "enterprise-agent": 1_000_000,
    "dedicated-agent": -1,
}

AGENT_TIER_PRICE_IDS: dict[str, str] = {
    "trial-agent": "price_agent_trial_placeholder",
    "pro-agent": "price_agent_pro_placeholder",
    "enterprise-agent": "price_agent_enterprise_placeholder",
    "dedicated-agent": "price_agent_dedicated_placeholder",
}


class StripeService:
    """Handles Stripe subscription and payment operations."""

    def __init__(self, db: AsyncSession, redis: Redis | None = None) -> None:
        """Initialize Stripe service.

        Args:
            db: Database session for persistence
            redis: Redis client for webhook idempotency (optional for backwards compat)
        """
        self.db = db
        self.redis = redis
        self.settings = get_settings()
        stripe.api_key = self.settings.stripe_secret_key

    async def _try_claim_event(self, event_id: str) -> bool:
        """Atomically try to claim an event for processing.

        Uses Redis SETNX (SET if Not eXists) to atomically check and claim
        the event in a single operation, preventing race conditions where
        two concurrent requests both pass an exists() check.

        Args:
            event_id: Stripe event ID (e.g., evt_1234...)

        Returns:
            True if we successfully claimed the event (proceed with processing)
            False if event was already claimed (duplicate, skip processing)
        """
        if self.redis is None:
            return True  # No Redis = no idempotency, allow processing

        key = f"{WEBHOOK_IDEMPOTENCY_PREFIX}{event_id}"
        try:
            # SET with NX (only if not exists) - returns True if set, None if exists
            # This is atomic - no race condition possible
            result = await self.redis.set(key, "processing", nx=True, ex=WEBHOOK_IDEMPOTENCY_TTL)
            return result is not None
        except Exception:
            # Redis error - allow processing but log would be ideal
            # Better to risk duplicate than to block all webhooks
            return True

    async def _mark_event_completed(self, event_id: str) -> None:
        """Mark a claimed event as successfully completed.

        Updates the Redis key value from "processing" to "completed".
        This is best-effort - if Redis fails, we've already processed
        the event and don't want to cause a retry.

        Args:
            event_id: Stripe event ID to mark as completed
        """
        if self.redis is None:
            return

        key = f"{WEBHOOK_IDEMPOTENCY_PREFIX}{event_id}"
        # Best-effort update - don't fail the webhook response for Redis issues
        with contextlib.suppress(Exception):
            await self.redis.set(key, "completed", ex=WEBHOOK_IDEMPOTENCY_TTL)

    async def _release_event_claim(self, event_id: str) -> None:
        """Release the claim on an event to allow Stripe retries.

        Called when a handler fails so that Stripe can retry the webhook.
        Deletes the Redis key to remove the "processing" claim.

        Args:
            event_id: Stripe event ID to release
        """
        if self.redis is None:
            return

        key = f"{WEBHOOK_IDEMPOTENCY_PREFIX}{event_id}"
        # Best-effort delete - don't block on Redis issues
        with contextlib.suppress(Exception):
            await self.redis.delete(key)

    async def create_checkout_session(
        self,
        user_id: uuid.UUID,
        tier: str,
        interval: str,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, Any]:
        """Create a Stripe Checkout session for subscription.

        Args:
            user_id: User upgrading subscription
            tier: Target tier (builder, pro, enterprise)
            interval: Billing interval (monthly, annual)
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel

        Returns:
            Dict with checkout session URL and ID

        Raises:
            ValueError: If tier/interval is invalid or user not found
        """
        if tier not in ["pro", "enterprise", "dedicated"]:
            raise ValueError(f"Invalid tier: {tier}. Must be pro, enterprise, or dedicated")
        if interval not in ["monthly", "annual"]:
            raise ValueError(f"Invalid interval: {interval}. Must be monthly or annual")

        price_map = get_tier_price_map()
        tier_prices = price_map.get(tier)
        if not tier_prices:
            raise ValueError(f"Unknown tier: {tier}")
        price_id = tier_prices.get(interval)
        if not price_id or price_id.endswith("_placeholder"):
            raise ValueError(f"Stripe price not configured for tier: {tier} ({interval})")

        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError(f"User {user_id} not found")

        customer_id = await self._get_or_create_customer(user)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True,
            automatic_tax={"enabled": True},
            billing_address_collection="required",
            metadata={
                "user_id": str(user_id),
                "tier": tier,
                "interval": interval,
            },
        )

        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }

    async def create_portal_session(
        self,
        user_id: uuid.UUID,
        return_url: str,
    ) -> dict[str, Any]:
        """Create a Stripe Customer Portal session for self-service management.

        Args:
            user_id: User requesting portal access
            return_url: URL to redirect when user exits portal

        Returns:
            Dict with portal session URL

        Raises:
            ValueError: If no subscription or customer found
        """
        result = await self.db.execute(select(Subscription).where(Subscription.user_id == user_id))
        subscription = result.scalar_one_or_none()

        if not subscription or not subscription.stripe_customer_id:
            raise ValueError("No Stripe customer found for this user")

        session = stripe.billing_portal.Session.create(
            customer=subscription.stripe_customer_id,
            return_url=return_url,
        )

        return {"portal_url": session.url}

    def _price_id_to_tier(self, price_id: str) -> tuple[str, str] | None:
        """Reverse-map a Stripe Price ID to (tier, interval).

        Returns:
            Tuple of (tier, interval) or None if not found
        """
        price_map = get_tier_price_map()
        for tier, intervals in price_map.items():
            for interval, pid in intervals.items():
                if pid == price_id:
                    return (tier, interval)
        return None

    async def _get_or_create_customer(self, user: User) -> str:
        """Get existing Stripe customer or create new one.

        Args:
            user: User to get/create customer for

        Returns:
            Stripe customer ID
        """
        # Check if user has subscription with customer ID
        result = await self.db.execute(select(Subscription).where(Subscription.user_id == user.id))
        subscription = result.scalar_one_or_none()

        if subscription and subscription.stripe_customer_id:
            return subscription.stripe_customer_id

        # Create new customer
        customer = stripe.Customer.create(
            email=user.email,
            name=user.name,
            metadata={"user_id": str(user.id)},
        )

        return customer.id

    async def handle_webhook_event(self, payload: bytes, signature: str) -> dict[str, Any]:
        """Handle incoming Stripe webhook event.

        Implements idempotency using atomic Redis SETNX to prevent race conditions.
        The event is claimed before processing, preventing concurrent duplicates.

        Args:
            payload: Raw request body
            signature: Stripe signature header

        Returns:
            Dict with processing result

        Raises:
            ValueError: If signature verification fails
        """
        try:
            event = stripe.Webhook.construct_event(
                payload,
                signature,
                self.settings.stripe_webhook_secret,
            )
        except stripe.error.SignatureVerificationError:
            raise ValueError("Invalid webhook signature")

        event_id = event["id"]
        event_type = event["type"]
        event_data = event["data"]["object"]

        # Atomic idempotency claim - prevents race conditions
        # If we can't claim, another request is processing or has processed this event
        if not await self._try_claim_event(event_id):
            return {
                "processed": False,
                "event_type": event_type,
                "event_id": event_id,
                "message": "Event already processed (duplicate)",
            }

        # Route to appropriate handler
        handlers = {
            "customer.subscription.created": self._handle_subscription_created,
            "customer.subscription.updated": self._handle_subscription_updated,
            "customer.subscription.deleted": self._handle_subscription_deleted,
            "invoice.payment_succeeded": self._handle_payment_succeeded,
            "invoice.payment_failed": self._handle_payment_failed,
            "checkout.session.completed": self._handle_checkout_completed,
        }

        handler = handlers.get(event_type)
        if handler:
            try:
                await handler(event_data)
                # Mark as completed (best-effort, won't fail the response)
                await self._mark_event_completed(event_id)
                return {"processed": True, "event_type": event_type, "event_id": event_id}
            except Exception:
                # Handler failed - release the claim so Stripe can retry
                # This prevents the event from being blocked for 24h
                await self._release_event_claim(event_id)
                raise

        return {"processed": False, "event_type": event_type, "message": "Unhandled event type"}

    async def _handle_checkout_completed(self, session: dict[str, Any]) -> None:
        """Handle checkout.session.completed event.

        This fires when a user completes checkout for subscription purchases.
        We use metadata to link the purchase to our user.
        """
        metadata = session.get("metadata", {})
        user_id_str = metadata.get("user_id")

        if not user_id_str:
            return

        user_id = uuid.UUID(user_id_str)

        base_tier = metadata.get("tier")
        interval = metadata.get("interval", "monthly")
        subscription_id = session.get("subscription")
        customer_id = session.get("customer")

        if not subscription_id:
            return

        tier = f"{base_tier}-agent" if base_tier and not base_tier.endswith("-agent") else base_tier

        stripe_sub = stripe.Subscription.retrieve(subscription_id)

        result = await self.db.execute(select(Subscription).where(Subscription.user_id == user_id))
        subscription = result.scalar_one_or_none()

        period_start = datetime.fromtimestamp(stripe_sub.current_period_start, tz=UTC)
        period_end = datetime.fromtimestamp(stripe_sub.current_period_end, tz=UTC)

        if subscription:
            subscription.tier = tier
            subscription.status = SubscriptionStatus.ACTIVE.value
            subscription.stripe_subscription_id = subscription_id
            subscription.stripe_customer_id = customer_id
            subscription.current_period_start = period_start
            subscription.current_period_end = period_end
            subscription.cancel_at_period_end = False
            subscription.interval = interval
        else:
            subscription = Subscription(
                user_id=user_id,
                tier=tier,
                status=SubscriptionStatus.ACTIVE.value,
                stripe_subscription_id=subscription_id,
                stripe_customer_id=customer_id,
                current_period_start=period_start,
                current_period_end=period_end,
                interval=interval,
            )
            self.db.add(subscription)

        await self.db.execute(update(User).where(User.id == user_id).values(tier=tier))

        await self.db.commit()

    async def _handle_subscription_created(self, subscription_data: dict[str, Any]) -> None:
        """Handle customer.subscription.created event."""
        # Usually handled by checkout.session.completed
        # This is a backup handler
        pass

    async def _handle_subscription_updated(self, subscription_data: dict[str, Any]) -> None:
        """Handle customer.subscription.updated event.

        Syncs tier from Stripe Price ID so Customer Portal plan changes
        are reflected in our database.
        """
        stripe_sub_id = subscription_data["id"]
        status = subscription_data["status"]
        cancel_at_period_end = subscription_data.get("cancel_at_period_end", False)

        result = await self.db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            return

        status_map = {
            "active": SubscriptionStatus.ACTIVE.value,
            "past_due": SubscriptionStatus.PAST_DUE.value,
            "canceled": SubscriptionStatus.CANCELLED.value,
            "trialing": SubscriptionStatus.TRIALING.value,
        }

        new_status = status_map.get(status, subscription.status)
        subscription.status = new_status
        subscription.cancel_at_period_end = cancel_at_period_end

        period_start = datetime.fromtimestamp(subscription_data["current_period_start"], tz=UTC)
        period_end = datetime.fromtimestamp(subscription_data["current_period_end"], tz=UTC)
        subscription.current_period_start = period_start
        subscription.current_period_end = period_end

        items = subscription_data.get("items", {}).get("data", [])
        if items:
            price_id = items[0].get("price", {}).get("id")
            if price_id:
                tier_info = self._price_id_to_tier(price_id)
                if tier_info:
                    base_tier, interval = tier_info
                    agent_tier = (
                        f"{base_tier}-agent" if not base_tier.endswith("-agent") else base_tier
                    )
                    subscription.tier = agent_tier
                    subscription.interval = interval
                    await self.db.execute(
                        update(User).where(User.id == subscription.user_id).values(tier=agent_tier)
                    )

        await self.db.commit()

    async def _handle_subscription_deleted(self, subscription_data: dict[str, Any]) -> None:
        """Handle customer.subscription.deleted event."""
        stripe_sub_id = subscription_data["id"]

        # Find our subscription record
        result = await self.db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            return

        # Mark as cancelled
        subscription.status = SubscriptionStatus.CANCELLED.value

        # Downgrade user to trial-agent tier
        await self.db.execute(
            update(User).where(User.id == subscription.user_id).values(tier="trial-agent")
        )

        await self.db.commit()

    async def _handle_payment_succeeded(self, invoice: dict[str, Any]) -> None:
        """Handle invoice.payment_succeeded event.

        For subscription renewals. Usage limits are managed by BillingMiddleware.
        """
        # No action needed - usage limits reset automatically via Redis key expiry
        pass

    async def _handle_payment_failed(self, invoice: dict[str, Any]) -> None:
        """Handle invoice.payment_failed event.

        Update subscription status to past_due.
        """
        subscription_id = invoice.get("subscription")

        if not subscription_id:
            return

        # Find our subscription
        result = await self.db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            return

        # Mark as past due
        subscription.status = SubscriptionStatus.PAST_DUE.value
        await self.db.commit()

    async def cancel_subscription(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Cancel subscription at end of billing period.

        Args:
            user_id: User cancelling subscription

        Returns:
            Dict with cancellation details

        Raises:
            ValueError: If no active subscription
        """
        # Find subscription
        result = await self.db.execute(select(Subscription).where(Subscription.user_id == user_id))
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise ValueError("No subscription found")

        if not subscription.stripe_subscription_id:
            raise ValueError("No Stripe subscription linked")

        if subscription.status == SubscriptionStatus.CANCELLED.value:
            raise ValueError("Subscription already cancelled")

        stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            cancel_at_period_end=True,
        )

        # Update our record
        subscription.cancel_at_period_end = True
        await self.db.commit()

        return {
            "status": "cancelling",
            "cancel_at": subscription.current_period_end.isoformat(),
            "message": "Subscription will be cancelled at end of billing period",
        }

    async def get_subscription(self, user_id: uuid.UUID) -> Subscription | None:
        """Get user's subscription.

        Args:
            user_id: User ID

        Returns:
            Subscription or None
        """
        result = await self.db.execute(select(Subscription).where(Subscription.user_id == user_id))
        return result.scalar_one_or_none()

"""Subscription model - Stripe subscription state for a user."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from mcpworks_api.models.user import User


class SubscriptionStatus(str, Enum):
    """Subscription status matching Stripe states."""

    ACTIVE = "active"
    CANCELLED = "cancelled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"


class SubscriptionTier(str, Enum):
    """Subscription tier with monthly execution limits.

    Per PRICING.md:
    - free ($0): 100 executions/month
    - founder ($29/mo): 1,000 executions/month
    - founder_pro ($59/mo): 10,000 executions/month
    - enterprise ($129+/mo): Unlimited
    """

    FREE = "free"
    FOUNDER = "founder"
    FOUNDER_PRO = "founder_pro"
    ENTERPRISE = "enterprise"

    @property
    def monthly_executions(self) -> int:
        """Get monthly execution limit for this tier. -1 means unlimited."""
        limits = {
            SubscriptionTier.FREE: 100,
            SubscriptionTier.FOUNDER: 1_000,
            SubscriptionTier.FOUNDER_PRO: 10_000,
            SubscriptionTier.ENTERPRISE: -1,  # Unlimited
        }
        return limits.get(self, 100)


class Subscription(Base, UUIDMixin, TimestampMixin):
    """Stripe subscription record.

    One subscription per user (enforced by unique constraint).
    State is synced from Stripe via webhooks.
    """

    __tablename__ = "subscriptions"

    # User reference (one subscription per user) - Index in __table_args__
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Subscription details
    tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Stripe references - Index in __table_args__
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Billing period
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="subscription",
    )

    __table_args__ = (
        Index("idx_subscriptions_user", "user_id"),
        Index("idx_subscriptions_stripe", "stripe_subscription_id"),
    )

    @property
    def is_active(self) -> bool:
        """Check if subscription is active or trialing."""
        return self.status in (
            SubscriptionStatus.ACTIVE.value,
            SubscriptionStatus.TRIALING.value,
        )

    @property
    def is_past_due(self) -> bool:
        """Check if subscription payment is past due."""
        return self.status == SubscriptionStatus.PAST_DUE.value

    @property
    def tier_enum(self) -> SubscriptionTier:
        """Get tier as enum."""
        return SubscriptionTier(self.tier)

    @property
    def status_enum(self) -> SubscriptionStatus:
        """Get status as enum."""
        return SubscriptionStatus(self.status)

    @property
    def monthly_executions(self) -> int:
        """Get monthly execution limit for current tier. -1 means unlimited."""
        return self.tier_enum.monthly_executions

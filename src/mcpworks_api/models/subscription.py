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
    """Subscription tier with monthly credits.

    Credits per month:
    - free: 500
    - starter: 2,900
    - pro: 9,900
    - enterprise: Custom
    """

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"

    @property
    def monthly_credits(self) -> int:
        """Get monthly credit grant for this tier."""
        credits = {
            SubscriptionTier.FREE: 500,
            SubscriptionTier.STARTER: 2900,
            SubscriptionTier.PRO: 9900,
            SubscriptionTier.ENTERPRISE: 99999,  # Custom, handled separately
        }
        return credits.get(self, 0)


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
    def monthly_credits(self) -> int:
        """Get monthly credit grant for current tier."""
        return self.tier_enum.monthly_credits

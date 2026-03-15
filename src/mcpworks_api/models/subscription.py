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

    Per PRICING.md v7.0.0 (Value Ladder):
    - trial ($0, 14-day): 125,000 executions/month
    - pro ($179/mo): 250,000 executions/month
    - enterprise ($599/mo): 1,000,000 executions/month
    - dedicated ($999/mo): unlimited (fair use)
    """

    TRIAL = "trial"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    DEDICATED = "dedicated"
    TRIAL_AGENT = "trial-agent"
    PRO_AGENT = "pro-agent"
    ENTERPRISE_AGENT = "enterprise-agent"
    DEDICATED_AGENT = "dedicated-agent"

    @property
    def is_agent_tier(self) -> bool:
        return self in (
            SubscriptionTier.TRIAL_AGENT,
            SubscriptionTier.PRO_AGENT,
            SubscriptionTier.ENTERPRISE_AGENT,
            SubscriptionTier.DEDICATED_AGENT,
        )

    @property
    def functions_tier(self) -> "SubscriptionTier":
        mapping = {
            SubscriptionTier.TRIAL_AGENT: SubscriptionTier.PRO,
            SubscriptionTier.PRO_AGENT: SubscriptionTier.PRO,
            SubscriptionTier.ENTERPRISE_AGENT: SubscriptionTier.ENTERPRISE,
            SubscriptionTier.DEDICATED_AGENT: SubscriptionTier.DEDICATED,
        }
        return mapping.get(self, self)

    @property
    def monthly_executions(self) -> int:
        """Get monthly execution limit for this tier. -1 means unlimited."""
        limits = {
            SubscriptionTier.TRIAL: 125_000,
            SubscriptionTier.PRO: 250_000,
            SubscriptionTier.ENTERPRISE: 1_000_000,
            SubscriptionTier.DEDICATED: -1,
            SubscriptionTier.TRIAL_AGENT: 125_000,
            SubscriptionTier.PRO_AGENT: 250_000,
            SubscriptionTier.ENTERPRISE_AGENT: 1_000_000,
            SubscriptionTier.DEDICATED_AGENT: -1,
        }
        return limits.get(self, 125_000)


AGENT_TIER_CONFIG: dict[str, dict] = {
    "trial-agent": {
        "max_agents": 5,
        "memory_limit_mb": 512,
        "cpu_limit": 0.5,
        "min_schedule_seconds": 30,
        "max_state_bytes": 100 * 1024 * 1024,
        "run_retention_days": 14,
        "max_webhook_payload_bytes": 1 * 1024 * 1024,
    },
    "pro-agent": {
        "max_agents": 5,
        "memory_limit_mb": 512,
        "cpu_limit": 0.5,
        "min_schedule_seconds": 30,
        "max_state_bytes": 100 * 1024 * 1024,
        "run_retention_days": 30,
        "max_webhook_payload_bytes": 1 * 1024 * 1024,
    },
    "enterprise-agent": {
        "max_agents": 20,
        "memory_limit_mb": 1024,
        "cpu_limit": 1.0,
        "min_schedule_seconds": 15,
        "max_state_bytes": 1024 * 1024 * 1024,
        "run_retention_days": 90,
        "max_webhook_payload_bytes": 5 * 1024 * 1024,
    },
    "dedicated-agent": {
        "max_agents": -1,
        "memory_limit_mb": 2048,
        "cpu_limit": 2.0,
        "min_schedule_seconds": 15,
        "max_state_bytes": -1,
        "run_retention_days": 365,
        "max_webhook_payload_bytes": 10 * 1024 * 1024,
    },
}


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

    interval: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        default="monthly",
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

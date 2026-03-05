"""User model - account holder who can authenticate and use platform services."""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from mcpworks_api.models.account import Account
    from mcpworks_api.models.api_key import APIKey
    from mcpworks_api.models.execution import Execution
    from mcpworks_api.models.namespace_share import NamespaceShare
    from mcpworks_api.models.oauth_account import OAuthAccount
    from mcpworks_api.models.subscription import Subscription


class UserTier(str, Enum):
    """User subscription tier per PRICING.md v5.0.0 (Value Ladder)."""

    FREE = "free"
    BUILDER = "builder"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class UserStatus(str, Enum):
    """User account status."""

    ACTIVE = "active"
    PENDING_VERIFICATION = "pending_verification"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class User(Base, UUIDMixin, TimestampMixin):
    """User account model.

    State transitions:
        [email/password] → pending_approval → active       (admin approves)
                                            → rejected      (admin rejects)
        [OAuth]          → active
        active           → suspended → active
                                     → deleted
        active           → deleted
    """

    __tablename__ = "users"

    # Core fields - Index in __table_args__
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Status fields
    tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserTier.FREE.value,
    )
    # Index in __table_args__
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserStatus.ACTIVE.value,
    )

    # Email verification
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    verification_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    verification_pin_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    verification_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    verification_resend_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    rejection_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    tier_override: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    tier_override_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    tier_override_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ORDER-008: ToS consent tracking
    tos_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    tos_version: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # Relationships
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    subscription: Mapped["Subscription"] = relationship(
        "Subscription",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    executions: Mapped[list["Execution"]] = relationship(
        "Execution",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        "OAuthAccount",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    namespace_shares: Mapped[list["NamespaceShare"]] = relationship(
        "NamespaceShare",
        foreign_keys="[NamespaceShare.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_status", "status"),
    )

    @property
    def is_active(self) -> bool:
        """Check if user account is active."""
        return self.status == UserStatus.ACTIVE.value

    @property
    def effective_tier(self) -> str:
        """Get effective tier, respecting override if set and not expired."""
        if self.tier_override:
            if self.tier_override_expires_at is None:
                return self.tier_override
            if self.tier_override_expires_at > datetime.now(UTC):
                return self.tier_override
        return self.tier

    @property
    def tier_enum(self) -> UserTier:
        """Get tier as enum."""
        return UserTier(self.tier)

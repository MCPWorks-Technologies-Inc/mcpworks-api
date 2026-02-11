"""User model - account holder who can authenticate and use platform services."""

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from mcpworks_api.models.account import Account
    from mcpworks_api.models.api_key import APIKey
    from mcpworks_api.models.credit import Credit
    from mcpworks_api.models.execution import Execution
    from mcpworks_api.models.subscription import Subscription


class UserTier(str, Enum):
    """User subscription tier per A0-SYSTEM-SPECIFICATION.md."""

    FREE = "free"
    FOUNDER = "founder"
    FOUNDER_PRO = "founder_pro"
    ENTERPRISE = "enterprise"


class UserStatus(str, Enum):
    """User account status."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class User(Base, UUIDMixin, TimestampMixin):
    """User account model.

    State transitions:
        [new] → active → suspended → active
                                   → deleted
               active → deleted
    """

    __tablename__ = "users"

    # Core fields - Index in __table_args__
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
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

    # Relationships
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    credit: Mapped["Credit"] = relationship(
        "Credit",
        back_populates="user",
        uselist=False,
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

    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_status", "status"),
    )

    @property
    def is_active(self) -> bool:
        """Check if user account is active."""
        return self.status == UserStatus.ACTIVE.value

    @property
    def tier_enum(self) -> UserTier:
        """Get tier as enum."""
        return UserTier(self.tier)

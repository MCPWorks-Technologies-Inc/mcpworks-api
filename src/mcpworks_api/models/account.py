"""Account model - billing entity that owns namespaces and resources."""

import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from mcpworks_api.models.namespace import Namespace
    from mcpworks_api.models.user import User
    from mcpworks_api.models.webhook import Webhook


class Account(Base, UUIDMixin, TimestampMixin):
    """Account model for billing and resource ownership.

    An account is the billing entity that owns namespaces, functions, and other
    resources. Each user has one account (1:1 relationship for now, can expand
    to multi-user accounts in future).

    Relationships:
    - user: The user who owns this account
    - namespaces: Namespaces owned by this account
    - webhooks: Webhooks configured for this account
    """

    __tablename__ = "accounts"

    # Link to user (1:1 for now)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Account name for display
    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="account",
    )

    namespaces: Mapped[List["Namespace"]] = relationship(
        "Namespace",
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="Namespace.name",
    )

    webhooks: Mapped[List["Webhook"]] = relationship(
        "Webhook",
        back_populates="account",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_accounts_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<Account(id={self.id}, user_id={self.user_id}, name={self.name})>"

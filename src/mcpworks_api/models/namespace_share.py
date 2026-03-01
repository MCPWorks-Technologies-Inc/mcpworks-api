"""NamespaceShare model - grants another user access to a namespace."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin


class ShareStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REVOKED = "revoked"


class NamespaceShare(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "namespace_shares"

    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    permissions: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=["read", "execute"],
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ShareStatus.PENDING.value,
    )

    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    namespace = relationship("Namespace", back_populates="shares")
    user = relationship("User", foreign_keys=[user_id], back_populates="namespace_shares")
    granted_by = relationship("User", foreign_keys=[granted_by_user_id])

    __table_args__ = (
        UniqueConstraint("namespace_id", "user_id", name="uq_namespace_share_user"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'revoked')",
            name="ck_namespace_share_status",
        ),
        Index("ix_namespace_shares_namespace_id", "namespace_id"),
        Index("ix_namespace_shares_user_id", "user_id"),
    )

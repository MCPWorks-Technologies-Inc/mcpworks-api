"""APIKey model - credential for programmatic access to the API."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from mcpworks_api.models.namespace import Namespace
    from mcpworks_api.models.user import User


class APIKey(Base, UUIDMixin):
    """API key for authentication.

    Key format: sk_{env}_{keyNum}_{random}
    Example: sk_live_k1_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456

    Only the hash is stored; full key is shown once on creation.
    The prefix (first 12 chars) is stored for identification.
    """

    __tablename__ = "api_keys"

    # Owner reference
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Key storage (hash only, prefix for identification)
    key_hash: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    key_prefix: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    # Metadata
    name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=["read", "write", "execute"],
    )

    # Timestamps (all timezone-aware for UTC consistency)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Optional namespace scope (A0 extension)
    namespace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="api_keys",
    )
    namespace: Mapped["Namespace | None"] = relationship(
        "Namespace",
        back_populates="api_keys",
    )

    __table_args__ = (
        Index("idx_api_keys_user", "user_id"),
        Index("idx_api_keys_hash", "key_hash"),
        Index("idx_api_keys_prefix", "key_prefix"),
        Index("idx_api_keys_namespace", "namespace_id"),
    )

    @property
    def is_valid(self) -> bool:
        """Check if API key is still valid (not revoked, not expired)."""

        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            return datetime.now(UTC) < self.expires_at
        return True

    @property
    def is_revoked(self) -> bool:
        """Check if API key has been revoked."""
        return self.revoked_at is not None

    def has_scope(self, scope: str) -> bool:
        """Check if API key has a specific scope."""
        return scope in self.scopes

"""Namespace model for organizing functions and services."""

import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from mcpworks_api.models.account import Account
    from mcpworks_api.models.api_key import APIKey
    from mcpworks_api.models.namespace_git_remote import NamespaceGitRemote
    from mcpworks_api.models.namespace_mcp_server import NamespaceMcpServer
    from mcpworks_api.models.namespace_service import NamespaceService
    from mcpworks_api.models.namespace_share import NamespaceShare


class Namespace(Base, UUIDMixin, TimestampMixin):
    """Namespace model for organizing functions and services.

    Namespaces provide:
    - Unique MCP endpoint (/mcp/create/{namespace}, /mcp/run/{namespace})
    - Resource isolation between accounts
    - Network security controls (IP allowlisting)
    - Organizational boundary for services and functions

    Relationships:
    - account: The billing account that owns this namespace
    - services: Services organized within this namespace
    - api_keys: API keys scoped to this namespace
    """

    __tablename__ = "namespaces"

    # Core Fields
    # Note: Index is defined in __table_args__ with explicit name
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(63),
        nullable=False,
        unique=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Network Security
    network_allowlist: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
    )

    allowlist_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    allowlist_changes_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    call_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="namespaces",
    )

    services: Mapped[list["NamespaceService"]] = relationship(
        "NamespaceService",
        back_populates="namespace",
        cascade="all, delete-orphan",
        order_by="NamespaceService.name",
    )

    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="namespace",
        cascade="all, delete-orphan",
    )

    shares: Mapped[list["NamespaceShare"]] = relationship(
        "NamespaceShare",
        back_populates="namespace",
        cascade="all, delete-orphan",
    )

    git_remote: Mapped["NamespaceGitRemote | None"] = relationship(
        "NamespaceGitRemote",
        back_populates="namespace",
        uselist=False,
        cascade="all, delete-orphan",
    )

    mcp_servers: Mapped[list["NamespaceMcpServer"]] = relationship(
        "NamespaceMcpServer",
        back_populates="namespace",
        cascade="all, delete-orphan",
        order_by="NamespaceMcpServer.name",
    )

    __table_args__ = (
        CheckConstraint(
            "name ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'",
            name="namespace_name_format",
        ),
        CheckConstraint(
            "allowlist_changes_today >= 0",
            name="allowlist_changes_positive",
        ),
        Index("ix_namespaces_account_id", "account_id"),
        Index("ix_namespaces_name", "name"),
    )

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        """Validate namespace name follows DNS naming rules.

        Rules:
        - 1-63 characters
        - Lowercase alphanumeric and hyphens only
        - Must start and end with alphanumeric
        """
        if not value:
            raise ValueError("Namespace name cannot be empty")

        if len(value) > 63:
            raise ValueError("Namespace name must be 63 characters or less")

        if not re.match(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", value):
            raise ValueError(
                "Namespace name must be lowercase alphanumeric with hyphens, "
                "starting and ending with alphanumeric character"
            )

        return value.lower()

    def can_update_allowlist(self) -> bool:
        """Check if allowlist can be updated (rate limit check)."""
        return self.allowlist_changes_today < 5

    @property
    def create_endpoint(self) -> str:
        """Compute management endpoint URL."""
        from mcpworks_api import url_builder

        return url_builder.create_url(self.name)

    @property
    def run_endpoint(self) -> str:
        """Compute execution endpoint URL."""
        from mcpworks_api import url_builder

        return url_builder.run_url(self.name)

    def __repr__(self) -> str:
        return f"<Namespace(id={self.id}, name={self.name}, account_id={self.account_id})>"

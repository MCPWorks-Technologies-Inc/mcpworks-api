"""NamespaceService model for organizing functions within a namespace."""

import re
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from mcpworks_api.models.function import Function
    from mcpworks_api.models.namespace import Namespace


class NamespaceService(Base, UUIDMixin, TimestampMixin):
    """Service model for organizing functions within a namespace.

    Services provide:
    - Logical grouping of related functions
    - Organization unit for function management
    - Namespace for function routing (/{service}/{function})

    Note: This is different from the BackendService model which handles
    routing to downstream service endpoints.

    Relationships:
    - namespace: The namespace this service belongs to
    - functions: Functions organized under this service
    """

    __tablename__ = "namespace_services"

    # Core Fields - Index in __table_args__
    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(63),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    call_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    # Relationships
    namespace: Mapped["Namespace"] = relationship(
        "Namespace",
        back_populates="services",
    )

    functions: Mapped[list["Function"]] = relationship(
        "Function",
        back_populates="service",
        cascade="all, delete-orphan",
        order_by="Function.name",
    )

    __table_args__ = (
        UniqueConstraint(
            "namespace_id",
            "name",
            name="uq_namespace_service_name",
        ),
        CheckConstraint(
            "name ~ '^[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?$'",
            name="namespace_service_name_format",
        ),
        Index("ix_namespace_services_namespace_id", "namespace_id"),
        Index("ix_namespace_services_name", "name"),
    )

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        """Validate service name follows URL-safe naming rules.

        Rules:
        - 1-63 characters
        - Lowercase alphanumeric, hyphens, and underscores
        - Must start and end with alphanumeric
        """
        if not value:
            raise ValueError("Service name cannot be empty")

        if len(value) > 63:
            raise ValueError("Service name must be 63 characters or less")

        if not re.match(r"^[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?$", value):
            raise ValueError(
                "Service name must be lowercase alphanumeric with hyphens/underscores, "
                "starting and ending with alphanumeric character"
            )

        return value.lower()

    @property
    def function_count(self) -> int:
        """Get number of functions in this service."""
        return len(self.functions) if self.functions else 0

    def __repr__(self) -> str:
        return (
            f"<NamespaceService(id={self.id}, name={self.name}, namespace_id={self.namespace_id})>"
        )

"""Function model representing a deployable function."""

import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from mcpworks_api.models.execution import Execution
    from mcpworks_api.models.function_version import FunctionVersion
    from mcpworks_api.models.namespace_service import NamespaceService


class Function(Base, UUIDMixin, TimestampMixin):
    """Function model representing a deployable function.

    Functions provide:
    - Named, versioned executable units
    - Multi-backend support (Code Sandbox, GitHub Repo, etc.)
    - Immutable version history
    - Tag-based organization and discovery

    Relationships:
    - service: The service this function belongs to
    - versions: Immutable versions of this function
    - executions: Execution history for this function
    """

    __tablename__ = "functions"

    # Core Fields - Index in __table_args__
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespace_services.id", ondelete="CASCADE"),
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

    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
    )

    output_trust: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="prompt",
    )

    active_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    call_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    locked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    locked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    public_safe: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    # Relationships
    service: Mapped["NamespaceService"] = relationship(
        "NamespaceService",
        back_populates="functions",
    )

    versions: Mapped[list["FunctionVersion"]] = relationship(
        "FunctionVersion",
        back_populates="function",
        cascade="all, delete-orphan",
        order_by="desc(FunctionVersion.version)",
    )

    executions: Mapped[list["Execution"]] = relationship(
        "Execution",
        back_populates="function",
        order_by="desc(Execution.created_at)",
    )

    __table_args__ = (
        UniqueConstraint(
            "service_id",
            "name",
            name="uq_function_service_name",
        ),
        CheckConstraint(
            "name ~ '^[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?$'",
            name="function_name_format",
        ),
        CheckConstraint(
            "active_version > 0",
            name="function_active_version_positive",
        ),
        Index("ix_functions_service_id", "service_id"),
        Index("ix_functions_name", "name"),
        Index("ix_functions_tags", "tags", postgresql_using="gin"),
    )

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        """Validate function name follows URL-safe naming rules.

        Rules:
        - 1-63 characters
        - Lowercase alphanumeric, hyphens, and underscores
        - Must start and end with alphanumeric
        """
        if not value:
            raise ValueError("Function name cannot be empty")

        if len(value) > 63:
            raise ValueError("Function name must be 63 characters or less")

        if not re.match(r"^[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?$", value):
            raise ValueError(
                "Function name must be lowercase alphanumeric with hyphens/underscores, "
                "starting and ending with alphanumeric character"
            )

        return value.lower()

    @validates("active_version")
    def validate_active_version(self, key: str, value: int) -> int:
        """Validate active version is positive."""
        if value < 1:
            raise ValueError("Active version must be positive")
        return value

    def get_active_version_obj(self) -> Optional["FunctionVersion"]:
        """Get the active FunctionVersion object."""
        for version in self.versions:
            if version.version == self.active_version:
                return version
        return None

    @property
    def execution_count(self) -> int:
        """Get total number of executions."""
        return len(self.executions) if self.executions else 0

    def __repr__(self) -> str:
        return f"<Function(id={self.id}, name={self.name}, service_id={self.service_id}, active_v={self.active_version})>"

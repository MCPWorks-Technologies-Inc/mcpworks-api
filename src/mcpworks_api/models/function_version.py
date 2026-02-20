"""FunctionVersion model representing an immutable function deployment."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from mcpworks_api.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from mcpworks_api.models.function import Function


# Allowed backend types
ALLOWED_BACKENDS = {"code_sandbox", "activepieces", "nanobot", "github_repo"}


class FunctionVersion(Base, UUIDMixin):
    """FunctionVersion model representing an immutable function deployment.

    Function versions provide:
    - Immutable code snapshots
    - Backend-specific configuration
    - Input/output schema definitions
    - Deployment history

    IMPORTANT: Function versions are IMMUTABLE once created.
    Any changes require creating a new version.

    Relationships:
    - function: The parent function this version belongs to
    """

    __tablename__ = "function_versions"

    # Core Fields - Index in __table_args__
    function_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("functions.id", ondelete="CASCADE"),
        nullable=False,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    backend: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Backend-Specific Data
    code: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Schema Definitions
    input_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    output_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Package requirements (validated against allow-list at creation time)
    requirements: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
    )

    # Environment variable declarations (names only, never values)
    required_env: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
    )

    optional_env: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
    )

    # Timestamp (immutable - no updated_at)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    function: Mapped["Function"] = relationship(
        "Function",
        back_populates="versions",
    )

    __table_args__ = (
        UniqueConstraint(
            "function_id",
            "version",
            name="uq_function_version_number",
        ),
        CheckConstraint(
            "version > 0",
            name="function_version_positive",
        ),
        CheckConstraint(
            "backend IN ('code_sandbox', 'activepieces', 'nanobot', 'github_repo')",
            name="function_version_backend_valid",
        ),
        Index("ix_function_versions_function_id", "function_id"),
        Index("ix_function_versions_version", "function_id", "version"),
        Index("ix_function_versions_backend", "backend"),
    )

    @validates("backend")
    def validate_backend(self, key: str, value: str) -> str:
        """Validate backend is one of supported types."""
        if value not in ALLOWED_BACKENDS:
            raise ValueError(f"Backend must be one of {ALLOWED_BACKENDS}")
        return value

    @validates("version")
    def validate_version(self, key: str, value: int) -> int:
        """Validate version is positive."""
        if value < 1:
            raise ValueError("Version must be positive")
        return value

    def __repr__(self) -> str:
        return f"<FunctionVersion(id={self.id}, function_id={self.function_id}, v={self.version}, backend={self.backend})>"

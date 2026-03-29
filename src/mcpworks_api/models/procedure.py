"""Procedure models for sequential, auditable execution pipelines."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

PROCEDURE_EXECUTION_STATUSES = ("running", "completed", "failed")
STEP_STATUSES = ("pending", "running", "success", "failed", "skipped")
FAILURE_POLICIES = ("required", "allowed", "skip")
MAX_STEPS = 20
MIN_STEPS = 1
MAX_RETRIES = 5


class Procedure(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "procedures"

    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespace_services.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    versions: Mapped[list["ProcedureVersion"]] = relationship(
        "ProcedureVersion",
        back_populates="procedure",
        cascade="all, delete-orphan",
        order_by="ProcedureVersion.version",
    )
    executions: Mapped[list["ProcedureExecution"]] = relationship(
        "ProcedureExecution",
        back_populates="procedure",
        cascade="all, delete-orphan",
        order_by="desc(ProcedureExecution.created_at)",
    )

    __table_args__ = (
        Index(
            "uq_procedure_service_name",
            "service_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_procedures_namespace_id", "namespace_id"),
        Index("ix_procedures_service_id", "service_id"),
    )

    def get_active_version_obj(self) -> "ProcedureVersion | None":
        for v in self.versions:
            if v.version == self.active_version:
                return v
        return None


class ProcedureVersion(Base, UUIDMixin):
    __tablename__ = "procedure_versions"

    procedure_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("procedures.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    steps: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    procedure: Mapped["Procedure"] = relationship("Procedure", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("procedure_id", "version", name="uq_procedure_version"),
        Index("ix_procedure_versions_procedure_id", "procedure_id"),
    )

    @validates("steps")
    def validate_steps(self, key: str, value: list) -> list:
        if not isinstance(value, list):
            raise ValueError("steps must be a list")
        if len(value) < MIN_STEPS or len(value) > MAX_STEPS:
            raise ValueError(f"Procedure must have between {MIN_STEPS} and {MAX_STEPS} steps")
        for i, step in enumerate(value):
            if not isinstance(step, dict):
                raise ValueError(f"Step {i + 1} must be an object")
            if "function_ref" not in step:
                raise ValueError(f"Step {i + 1} must have a function_ref")
            if "name" not in step:
                raise ValueError(f"Step {i + 1} must have a name")
            if "instructions" not in step:
                raise ValueError(f"Step {i + 1} must have instructions")
            policy = step.get("failure_policy", "required")
            if policy not in FAILURE_POLICIES:
                raise ValueError(
                    f"Step {i + 1} failure_policy must be one of: {', '.join(FAILURE_POLICIES)}"
                )
            retries = step.get("max_retries", 1)
            if not isinstance(retries, int) or retries < 0 or retries > MAX_RETRIES:
                raise ValueError(f"Step {i + 1} max_retries must be 0-{MAX_RETRIES}")
        return value


class ProcedureExecution(Base, UUIDMixin):
    __tablename__ = "procedure_executions"

    procedure_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("procedures.id", ondelete="CASCADE"),
        nullable=False,
    )
    procedure_version: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    step_results: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    input_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    procedure: Mapped["Procedure"] = relationship("Procedure", back_populates="executions")

    __table_args__ = (
        Index("ix_procedure_executions_procedure_id", "procedure_id"),
        Index("ix_procedure_executions_agent_id", "agent_id"),
        Index("ix_procedure_executions_status", "procedure_id", "status"),
    )

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        if value not in PROCEDURE_EXECUTION_STATUSES:
            raise ValueError(f"Invalid execution status: {value}")
        return value

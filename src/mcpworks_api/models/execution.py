"""Execution model - tracks workflow executions."""

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from mcpworks_api.models.credit_transaction import CreditTransaction
    from mcpworks_api.models.function import Function
    from mcpworks_api.models.user import User


class ExecutionStatus(enum.Enum):
    """Execution status values."""

    PENDING = "pending"  # Created, waiting to start
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"  # Execution failed
    CANCELLED = "cancelled"  # Manually cancelled
    TIMED_OUT = "timed_out"  # Exceeded max execution time


class Execution(Base, UUIDMixin, TimestampMixin):
    """Workflow execution record.

    Tracks the lifecycle of a workflow execution from creation to completion.
    Stores execution results and integrates with credit hold/commit/release.
    """

    __tablename__ = "executions"

    # User who initiated the execution
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # A0 Extension: Function that was executed
    function_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("functions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # A0 Extension: Function version that was executed
    function_version_num: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    # A0 Extension: Backend that executed the function
    backend: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Workflow being executed (from mcpworks-agent)
    workflow_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    # Execution status
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ExecutionStatus.PENDING.value,
        index=True,
    )

    # Credit hold transaction ID (for commit/release on completion)
    hold_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credit_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Input parameters for the workflow
    input_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Execution result (on completion)
    result_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Error information (on failure)
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # A0 Extension: Credit cost for this execution
    credit_cost: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # A0 Extension: Backend-specific metadata
    backend_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(  # noqa: F821
        back_populates="executions",
        lazy="selectin",
    )

    hold_transaction: Mapped["CreditTransaction"] = relationship(  # noqa: F821
        lazy="selectin",
    )

    function: Mapped["Function | None"] = relationship(
        "Function",
        back_populates="executions",
        lazy="selectin",
    )

    @property
    def duration_seconds(self) -> float | None:
        """Calculate execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_terminal(self) -> bool:
        """Check if execution is in a terminal state."""
        return self.status in [
            ExecutionStatus.COMPLETED.value,
            ExecutionStatus.FAILED.value,
            ExecutionStatus.CANCELLED.value,
            ExecutionStatus.TIMED_OUT.value,
        ]

    def mark_running(self) -> None:
        """Mark execution as running."""
        self.status = ExecutionStatus.RUNNING.value
        self.started_at = datetime.now(UTC)

    def mark_completed(self, result: dict[str, Any] | None = None) -> None:
        """Mark execution as completed successfully."""
        self.status = ExecutionStatus.COMPLETED.value
        self.completed_at = datetime.now(UTC)
        self.result_data = result

    def mark_failed(self, error_message: str, error_code: str | None = None) -> None:
        """Mark execution as failed."""
        self.status = ExecutionStatus.FAILED.value
        self.completed_at = datetime.now(UTC)
        self.error_message = error_message
        self.error_code = error_code

    def mark_cancelled(self) -> None:
        """Mark execution as cancelled."""
        self.status = ExecutionStatus.CANCELLED.value
        self.completed_at = datetime.now(UTC)

    def mark_timed_out(self) -> None:
        """Mark execution as timed out."""
        self.status = ExecutionStatus.TIMED_OUT.value
        self.completed_at = datetime.now(UTC)
        self.error_message = "Execution timed out"
        self.error_code = "EXECUTION_TIMEOUT"

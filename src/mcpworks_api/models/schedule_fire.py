"""Schedule fire audit trail — records each cron schedule fire event."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from mcpworks_api.models.base import Base, UUIDMixin

FIRE_STATUSES = ("started", "error", "skipped")


class ScheduleFire(Base, UUIDMixin):
    __tablename__ = "schedule_fires"

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_schedules.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    schedule: Mapped["AgentSchedule"] = relationship("AgentSchedule")  # noqa: F821
    agent_run: Mapped["AgentRun | None"] = relationship(  # noqa: F821
        "AgentRun", back_populates="schedule_fires"
    )

    __table_args__ = (
        Index("ix_schedule_fires_schedule_fired", "schedule_id", "fired_at"),
        Index("ix_schedule_fires_agent_fired", "agent_id", "fired_at"),
        Index("ix_schedule_fires_created", "created_at"),
    )

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        if value not in FIRE_STATUSES:
            raise ValueError(f"Invalid fire status: {value}")
        return value

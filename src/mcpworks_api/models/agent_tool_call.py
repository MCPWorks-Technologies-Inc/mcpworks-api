"""Agent tool call audit trail — persists individual tool calls from orchestration runs."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base, UUIDMixin

TOOL_CALL_SOURCES = ("namespace", "mcp", "platform")
TOOL_CALL_STATUSES = ("success", "error")

MAX_TOOL_INPUT_BYTES = 2048
MAX_RESULT_PREVIEW_CHARS = 500
MAX_ERROR_CHARS = 500


class AgentToolCall(Base, UUIDMixin):
    __tablename__ = "agent_tool_calls"

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_input: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    agent_run: Mapped["AgentRun"] = relationship(  # noqa: F821
        "AgentRun", back_populates="tool_calls"
    )

    __table_args__ = (
        Index("ix_agent_tool_calls_run_seq", "agent_run_id", "sequence_number"),
        Index("ix_agent_tool_calls_created", "created_at"),
    )

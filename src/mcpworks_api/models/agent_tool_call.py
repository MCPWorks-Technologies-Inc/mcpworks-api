"""Agent tool call audit trail — persists individual tool calls from orchestration runs."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from mcpworks_api.models.base import Base, UUIDMixin

TOOL_CALL_SOURCES = ("namespace", "mcp", "platform")
TOOL_CALL_STATUSES = ("success", "error")
DECISION_TYPES = ("call", "skip", "no_action", "limit_check")
REASON_CATEGORIES = (
    "success",
    "error",
    "quality_threshold_not_met",
    "no_matching_data",
    "limit_reached",
    "rate_limited",
    "access_denied",
    "timeout",
    "not_applicable",
)

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
    decision_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="call", default="call"
    )
    reason_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    agent_run: Mapped["AgentRun"] = relationship(  # noqa: F821
        "AgentRun", back_populates="tool_calls"
    )

    @validates("decision_type")
    def validate_decision_type(self, key: str, value: str) -> str:
        if value not in DECISION_TYPES:
            raise ValueError(f"Invalid decision type: {value}")
        return value

    @validates("reason_category")
    def validate_reason_category(self, key: str, value: str | None) -> str | None:
        if value is not None and value not in REASON_CATEGORIES:
            raise ValueError(f"Invalid reason category: {value}")
        return value

    __table_args__ = (
        Index("ix_agent_tool_calls_run_seq", "agent_run_id", "sequence_number"),
        Index("ix_agent_tool_calls_created", "created_at"),
    )

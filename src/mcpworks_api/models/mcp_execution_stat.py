"""McpExecutionStat model — per-execution MCP usage and token savings."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mcpworks_api.models.base import Base, UUIDMixin


class McpExecutionStat(Base, UUIDMixin):
    __tablename__ = "mcp_execution_stats"

    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_id: Mapped[str] = mapped_column(String(64), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    input_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mcp_calls_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mcp_bytes_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_saved_est: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_mcp_execution_stats_ns_time", "namespace_id", "executed_at"),)

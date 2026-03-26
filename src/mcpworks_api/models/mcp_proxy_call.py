"""McpProxyCall model — per-call telemetry from the MCP proxy."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mcpworks_api.models.base import Base, UUIDMixin


class McpProxyCall(Base, UUIDMixin):
    __tablename__ = "mcp_proxy_calls"

    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    server_name: Mapped[str] = mapped_column(String(63), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    response_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    response_tokens_est: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    injections_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_mcp_proxy_calls_ns_time", "namespace_id", "called_at"),
        Index(
            "ix_mcp_proxy_calls_ns_server_tool_time",
            "namespace_id",
            "server_name",
            "tool_name",
            "called_at",
        ),
    )

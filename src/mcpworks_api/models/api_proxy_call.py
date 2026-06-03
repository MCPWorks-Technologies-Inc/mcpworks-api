"""ApiProxyCall model — per-call telemetry from the API proxy (feature 019).

Parallel to McpProxyCall (008/010). Credential values and request/response
bodies are never recorded.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mcpworks_api.models.base import Base, UUIDMixin


class ApiProxyCall(Base, UUIDMixin):
    __tablename__ = "api_proxy_calls"

    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    api_server: Mapped[str] = mapped_column(String(63), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    response_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_api_proxy_calls_ns_time", "namespace_id", "called_at"),
        Index("ix_api_proxy_calls_ns_server", "namespace_id", "api_server"),
    )

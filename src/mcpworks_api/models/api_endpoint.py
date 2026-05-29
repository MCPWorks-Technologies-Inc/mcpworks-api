"""ApiEndpoint model — one endpoint of a registered REST API (feature 019).

Separate table (not a JSONB blob on the server) because each endpoint carries
queryable per-row state: ``enabled`` (LLM curation → sandbox primitive) and
``published`` (opt-in raw MCP-tool exposure).
"""

import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin


class ApiEndpoint(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "api_endpoints"

    api_server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespace_api_servers.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Stable handle → api__{server}__{operation_id}. Identifier-safe.
    operation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Location-bucketed params: {"path": {...}, "query": {...}, "header": {...}}
    param_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    request_body_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Generated as a sandbox primitive when true (default false for imported, true for manual).
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Exposed as a direct raw MCP tool when true.
    published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="imported")

    api_server = relationship("NamespaceApiServer", back_populates="endpoints")

    __table_args__ = (
        UniqueConstraint("api_server_id", "operation_id", name="uq_api_endpoint_operation"),
        Index("ix_api_endpoints_server_enabled", "api_server_id", "enabled"),
        Index("ix_api_endpoints_server_published", "api_server_id", "published"),
    )

    def __repr__(self) -> str:
        return f"<ApiEndpoint(server_id={self.api_server_id}, op={self.operation_id})>"

"""NamespaceMcpServer model for external MCP server integration per namespace."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

AUTH_TYPES = ("bearer", "oauth2", "none")

DEFAULT_SETTINGS = {
    "response_limit_bytes": 1048576,
    "timeout_seconds": 30,
    "max_calls_per_execution": 50,
    "retry_on_failure": True,
    "retry_count": 2,
}


class NamespaceMcpServer(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "namespace_mcp_servers"

    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(63), nullable=False)
    transport: Mapped[str] = mapped_column(String(20), nullable=False, default="streamable_http")
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    command: Mapped[str | None] = mapped_column(String(500), nullable=True)
    command_args: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    headers_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    headers_dek_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    env_vars: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    rules: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default='{"request":[],"response":[]}'
    )
    tool_schemas: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    tool_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    auth_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="bearer", server_default="bearer"
    )
    oauth_config_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    oauth_config_dek: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    oauth_tokens_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    oauth_tokens_dek: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    oauth_tokens_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    namespace = relationship("Namespace", back_populates="mcp_servers")

    __table_args__ = (
        UniqueConstraint("namespace_id", "name", name="uq_namespace_mcp_server_name"),
    )

    def get_settings(self) -> dict:
        merged = dict(DEFAULT_SETTINGS)
        merged.update(self.settings or {})
        return merged

    @validates("auth_type")
    def validate_auth_type(self, key: str, value: str) -> str:
        if value not in AUTH_TYPES:
            raise ValueError(f"Invalid auth_type: {value}. Must be one of: {AUTH_TYPES}")
        return value

    def __repr__(self) -> str:
        return f"<NamespaceMcpServer(namespace_id={self.namespace_id}, name={self.name})>"

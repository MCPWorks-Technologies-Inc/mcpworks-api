"""NamespaceApiServer model — register a plain REST API as an ad-hoc MCP (feature 019).

Inverse mirror of NamespaceMcpServer (008): instead of wrapping a remote MCP server,
this wraps a plain REST/HTTP API whose endpoints become sandbox-callable primitives.

Credential definitions live in the ``auth`` JSONB; stored secret VALUES live in a
separate encrypted column keyed by injection name (so redaction is structural).
"""

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

DEFAULT_SETTINGS = {
    "response_limit_bytes": 1048576,
    "timeout_seconds": 30,
    "max_calls_per_execution": 50,
    "retry_on_failure": True,
    "retry_count": 2,
}

# Methods that may be safely auto-retried (idempotent). POST/PATCH are never retried.
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS"})

# Upper bound on endpoints imported from a single spec (FR-001a safety ceiling).
MAX_ENDPOINTS_PER_SERVER = 1000

VALID_SPEC_SOURCES = frozenset({"openapi_url", "openapi_file", "manual"})


class NamespaceApiServer(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "namespace_api_servers"

    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(63), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    spec_source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    openapi_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Credential-injection DEFINITIONS only (name, location, key, format, source, env_var).
    # Never holds secret values — see credentials_encrypted.
    auth: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    # name -> secret map for `stored` injections, envelope-encrypted (KEK/DEK).
    credentials_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    credentials_dek_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    # Static non-secret default headers (e.g. Accept), encrypted at rest for uniformity.
    default_headers_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    default_headers_dek_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    endpoint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    namespace = relationship("Namespace", back_populates="api_servers")
    endpoints = relationship(
        "ApiEndpoint",
        back_populates="api_server",
        cascade="all, delete-orphan",
        order_by="ApiEndpoint.operation_id",
    )

    __table_args__ = (
        UniqueConstraint("namespace_id", "name", name="uq_namespace_api_server_name"),
    )

    def get_settings(self) -> dict:
        merged = dict(DEFAULT_SETTINGS)
        merged.update(self.settings or {})
        return merged

    def __repr__(self) -> str:
        return f"<NamespaceApiServer(namespace_id={self.namespace_id}, name={self.name})>"

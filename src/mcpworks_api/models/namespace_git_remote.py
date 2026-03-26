"""NamespaceGitRemote model for storing Git push targets per namespace."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin


class NamespaceGitRemote(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "namespace_git_remotes"

    namespace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("namespaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    git_url: Mapped[str] = mapped_column(String(500), nullable=False)
    git_branch: Mapped[str] = mapped_column(String(100), nullable=False, default="main")
    token_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    token_dek_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    last_export_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_export_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    namespace = relationship("Namespace", back_populates="git_remote")

    __table_args__ = (
        UniqueConstraint("namespace_id", name="uq_namespace_git_remote_namespace"),
    )

    def __repr__(self) -> str:
        return f"<NamespaceGitRemote(namespace_id={self.namespace_id}, url={self.git_url})>"

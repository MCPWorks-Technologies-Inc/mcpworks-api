"""EmailLog model - audit trail for all outbound transactional emails."""

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin


class EmailLog(Base, UUIDMixin, TimestampMixin):
    """Records every outbound email for audit and debugging."""

    __tablename__ = "email_logs"

    recipient: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    email_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="sent",
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    __table_args__ = (
        Index("idx_email_logs_type_created", "email_type", "created_at"),
        Index("idx_email_logs_recipient_created", "recipient", "created_at"),
    )

"""Webhook model for event notification delivery."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from mcpworks_api.models.account import Account


class Webhook(Base, UUIDMixin, TimestampMixin):
    """Webhook model for event notification delivery.

    Webhooks provide:
    - Real-time event notifications to external URLs
    - Filtered event subscriptions
    - Signature-based authentication
    - Enable/disable control

    Event Types:
    - function.execution.completed
    - function.execution.failed
    - function.created
    - function.updated
    - service.created
    - namespace.created
    - etc.

    Relationships:
    - account: The account that owns this webhook
    """

    __tablename__ = "webhooks"

    # Core Fields - Index in __table_args__
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )

    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    secret_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    events: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="webhooks",
    )

    __table_args__ = (
        CheckConstraint(
            "url ~ '^https://'",
            name="webhook_url_https",
        ),
        Index("ix_webhooks_account_id", "account_id"),
        Index("ix_webhooks_enabled", "enabled"),
        Index("ix_webhooks_events", "events", postgresql_using="gin"),
    )

    @validates("url")
    def validate_url(self, key: str, value: str) -> str:
        """Validate webhook URL is HTTPS."""
        if not value.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS")
        return value

    @validates("events")
    def validate_events(self, key: str, value: list[str]) -> list[str]:
        """Validate events list is not empty."""
        if not value or len(value) == 0:
            raise ValueError("Webhook must subscribe to at least one event")
        return value

    def __repr__(self) -> str:
        return f"<Webhook(id={self.id}, account_id={self.account_id}, enabled={self.enabled}, events={len(self.events)})>"

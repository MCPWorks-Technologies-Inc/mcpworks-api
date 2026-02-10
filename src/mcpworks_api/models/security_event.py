"""SecurityEvent model for tracking security-relevant events."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from mcpworks_api.models.base import Base, UUIDMixin

# Allowed severity levels
ALLOWED_SEVERITIES = {"info", "warning", "error", "critical"}


class SecurityEvent(Base, UUIDMixin):
    """SecurityEvent model for tracking security-relevant events.

    Security events provide:
    - Audit trail for SOC 2 compliance
    - Incident detection and response data
    - Access pattern analysis
    - Security monitoring and alerting

    Event Types:
    - auth.login_failed
    - auth.api_key_created
    - auth.api_key_revoked
    - namespace.whitelist_updated
    - function.execution_blocked
    - admin.user_suspended
    - etc.

    Severity Levels:
    - info: Normal operations
    - warning: Suspicious but not malicious
    - error: Failed operations requiring review
    - critical: Security incidents requiring immediate action
    """

    __tablename__ = "security_events"

    # Event Metadata
    # Note: Indexes are defined in __table_args__ with explicit names
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Actor Information
    actor_ip: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
    )

    actor_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Event Details
    details: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'warning', 'error', 'critical')",
            name="security_event_severity_valid",
        ),
        Index("ix_security_events_timestamp", "timestamp"),
        Index("ix_security_events_event_type", "event_type"),
        Index("ix_security_events_severity", "severity"),
        Index("ix_security_events_actor_id", "actor_id"),
        Index(
            "ix_security_events_timestamp_severity",
            "timestamp",
            "severity",
        ),
    )

    @validates("severity")
    def validate_severity(self, key: str, value: str) -> str:
        """Validate severity is one of allowed values."""
        if value not in ALLOWED_SEVERITIES:
            raise ValueError(f"Severity must be one of {ALLOWED_SEVERITIES}")
        return value

    @validates("event_type")
    def validate_event_type(self, key: str, value: str) -> str:
        """Validate event type follows namespace format."""
        if not value or "." not in value:
            raise ValueError("Event type must be in format 'category.action'")
        return value

    def __repr__(self) -> str:
        return f"<SecurityEvent(id={self.id}, type={self.event_type}, severity={self.severity}, timestamp={self.timestamp})>"

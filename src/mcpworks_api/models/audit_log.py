"""AuditLog model - security and compliance audit trail."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mcpworks_api.models.base import Base, UUIDMixin


class AuditAction(str, Enum):
    """Common audit log actions."""

    # User lifecycle
    USER_REGISTERED = "user_registered"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"

    # API key management
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    API_KEY_USED = "api_key_used"

    # Credit operations
    CREDIT_HOLD = "credit_hold"
    CREDIT_COMMIT = "credit_commit"
    CREDIT_RELEASE = "credit_release"
    CREDIT_PURCHASE = "credit_purchase"
    CREDIT_GRANT = "credit_grant"
    CREDIT_REFUND = "credit_refund"

    # Subscription management
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_UPDATED = "subscription_updated"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"

    # Service routing
    SERVICE_ROUTED = "service_routed"
    SERVICE_ERROR = "service_error"

    # Authentication
    AUTH_FAILED = "auth_failed"
    TOKEN_ISSUED = "token_issued"
    TOKEN_REFRESHED = "token_refreshed"


class AuditLog(Base, UUIDMixin):
    """Security and compliance audit trail.

    Immutable record of all significant system events.
    Used for:
    - Security auditing and compliance
    - Debugging and support
    - Analytics and monitoring
    """

    __tablename__ = "audit_logs"

    # Who performed the action (null for system actions)
    # Note: Indexes are defined in __table_args__ with explicit names
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # What action was performed
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # What resource was affected
    resource_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # Request context
    ip_address: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Additional context
    event_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Timestamp (immutable) - Index in __table_args__
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_created", "created_at", postgresql_ops={"created_at": "DESC"}),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )

    @property
    def action_enum(self) -> AuditAction | None:
        """Get action as enum (if valid)."""
        try:
            return AuditAction(self.action)
        except ValueError:
            # Custom action not in enum
            return None

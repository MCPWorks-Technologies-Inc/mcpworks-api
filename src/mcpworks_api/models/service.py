"""Service model - registry of backend services for routing."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from mcpworks_api.models.base import Base, TimestampMixin, UUIDMixin


class ServiceStatus(str, Enum):
    """Service health status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DEGRADED = "degraded"


class Service(Base, UUIDMixin, TimestampMixin):
    """Backend service registry entry.

    Used for routing requests to downstream services (math, agent, etc.)
    and tracking their health status.
    """

    __tablename__ = "services"

    # Identity
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Routing
    url: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    health_check_url: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Pricing and access
    credit_cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    tier_required: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="free",
    )

    # Health status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ServiceStatus.ACTIVE.value,
        index=True,
    )
    last_health_check: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_services_name", "name"),
        Index("idx_services_status", "status"),
    )

    @property
    def is_available(self) -> bool:
        """Check if service is available for requests."""
        return self.status in (ServiceStatus.ACTIVE.value, ServiceStatus.DEGRADED.value)

    @property
    def is_healthy(self) -> bool:
        """Check if service is fully healthy."""
        return self.status == ServiceStatus.ACTIVE.value

    @property
    def status_enum(self) -> ServiceStatus:
        """Get status as enum."""
        return ServiceStatus(self.status)

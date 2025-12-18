"""Credit model - balance tracking for a user."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base

if TYPE_CHECKING:
    from mcpworks_api.models.credit_transaction import CreditTransaction
    from mcpworks_api.models.user import User


class Credit(Base):
    """Credit balance for a user.

    One row per user. Uses row-level locking (SELECT FOR UPDATE)
    for transaction safety in hold/commit/release pattern.

    Invariants:
    - available_balance >= 0 (enforced by CHECK constraint)
    - held_balance >= 0 (enforced by CHECK constraint)
    - lifetime_earned >= lifetime_spent (business logic)
    """

    __tablename__ = "credits"

    # Primary key is user_id (one credit row per user)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Balances
    available_balance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    held_balance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    # Lifetime totals
    lifetime_earned: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    lifetime_spent: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    # Last update
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="credit",
    )
    transactions: Mapped[list["CreditTransaction"]] = relationship(
        "CreditTransaction",
        back_populates="credit",
        foreign_keys="[CreditTransaction.user_id]",
        primaryjoin="Credit.user_id == CreditTransaction.user_id",
        order_by="CreditTransaction.created_at.desc()",
    )

    __table_args__ = (
        CheckConstraint(
            "available_balance >= 0",
            name="chk_available_non_negative",
        ),
        CheckConstraint(
            "held_balance >= 0",
            name="chk_held_non_negative",
        ),
    )

    @property
    def total_balance(self) -> Decimal:
        """Total balance including held credits."""
        return self.available_balance + self.held_balance

    def can_afford(self, amount: Decimal) -> bool:
        """Check if user has enough available credits."""
        return self.available_balance >= amount

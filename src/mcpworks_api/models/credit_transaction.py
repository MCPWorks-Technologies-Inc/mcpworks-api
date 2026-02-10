"""CreditTransaction model - audit trail for all credit operations."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mcpworks_api.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from mcpworks_api.models.credit import Credit


class TransactionType(str, Enum):
    """Credit transaction types.

    Amount Sign:
    - hold: negative (credits moved from available to held)
    - commit: negative (credits deducted from held)
    - release: positive (credits returned from held to available)
    - purchase: positive (credits added via payment)
    - grant: positive (credits added via subscription or promo)
    - refund: positive (credits returned due to error/dispute)
    """

    HOLD = "hold"
    COMMIT = "commit"
    RELEASE = "release"
    PURCHASE = "purchase"
    GRANT = "grant"
    REFUND = "refund"


class CreditTransaction(Base, UUIDMixin):
    """Credit transaction audit record.

    Every credit operation creates a transaction record for:
    - Audit trail and compliance
    - Debugging and support
    - Analytics and reporting
    """

    __tablename__ = "credit_transactions"

    # User reference - Index in __table_args__
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Transaction details - Index in __table_args__
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    # Balance snapshot (for audit trail)
    balance_before: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    balance_after: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    # References
    hold_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credit_transactions.id"),
        nullable=True,
    )
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # Additional context
    transaction_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Timestamp - Index in __table_args__
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    credit: Mapped["Credit"] = relationship(
        "Credit",
        back_populates="transactions",
        foreign_keys=[user_id],
        primaryjoin="CreditTransaction.user_id == Credit.user_id",
    )
    original_hold: Mapped["CreditTransaction"] = relationship(
        "CreditTransaction",
        remote_side="CreditTransaction.id",
        foreign_keys=[hold_id],
    )

    __table_args__ = (
        Index("idx_credit_txn_user", "user_id"),
        Index("idx_credit_txn_hold", "hold_id", postgresql_where="hold_id IS NOT NULL"),
        Index("idx_credit_txn_created", "created_at", postgresql_ops={"created_at": "DESC"}),
        Index("idx_credit_txn_type", "type"),
    )

    @property
    def type_enum(self) -> TransactionType:
        """Get type as enum."""
        return TransactionType(self.type)

    @property
    def is_debit(self) -> bool:
        """Check if this transaction reduces available balance."""
        return self.type in (TransactionType.HOLD.value, TransactionType.COMMIT.value)

    @property
    def is_credit(self) -> bool:
        """Check if this transaction increases available balance."""
        return self.type in (
            TransactionType.RELEASE.value,
            TransactionType.PURCHASE.value,
            TransactionType.GRANT.value,
            TransactionType.REFUND.value,
        )

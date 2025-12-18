"""Credit service - hold/commit/release pattern for credit management."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.exceptions import InsufficientCreditsError, InvalidHoldError
from mcpworks_api.models import Credit, CreditTransaction
from mcpworks_api.models.credit_transaction import TransactionType


class CreditService:
    """Service for credit balance management.

    Implements the hold/commit/release pattern for transaction-safe credit operations:
    1. HOLD: Reserve credits before an operation (moves from available to held)
    2. COMMIT: Finalize the charge after success (deducts from held)
    3. RELEASE: Return credits if operation fails or is cancelled (returns held to available)

    All operations use row-level locking (SELECT FOR UPDATE) to prevent race conditions.
    """

    # Hold expiration time
    HOLD_EXPIRY_HOURS = 1

    def __init__(self, db: AsyncSession) -> None:
        """Initialize credit service with database session."""
        self.db = db

    async def get_balance(self, user_id: uuid.UUID) -> Credit:
        """Get user's credit balance.

        Creates a credit record if one doesn't exist.

        Args:
            user_id: User's UUID

        Returns:
            Credit record for the user
        """
        result = await self.db.execute(select(Credit).where(Credit.user_id == user_id))
        credit = result.scalar_one_or_none()

        if credit is None:
            # Create initial credit record
            credit = Credit(
                user_id=user_id,
                available_balance=Decimal("0.00"),
                held_balance=Decimal("0.00"),
                lifetime_earned=Decimal("0.00"),
                lifetime_spent=Decimal("0.00"),
            )
            self.db.add(credit)
            await self.db.flush()

        return credit

    async def hold(
        self,
        user_id: uuid.UUID,
        amount: Decimal,
        execution_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> CreditTransaction:
        """Hold credits for a pending operation.

        Moves credits from available_balance to held_balance.
        Uses SELECT FOR UPDATE to prevent race conditions.

        Args:
            user_id: User's UUID
            amount: Amount to hold (must be positive)
            execution_id: Optional reference to the execution/operation
            metadata: Optional metadata for the transaction

        Returns:
            CreditTransaction record for the hold

        Raises:
            InsufficientCreditsError: If user doesn't have enough available credits
            ValueError: If amount is not positive
        """
        if amount <= 0:
            raise ValueError("Hold amount must be positive")

        # Lock the credit row for update
        result = await self.db.execute(
            select(Credit).where(Credit.user_id == user_id).with_for_update()
        )
        credit = result.scalar_one_or_none()

        if credit is None:
            # Create initial credit record (still under lock)
            credit = Credit(
                user_id=user_id,
                available_balance=Decimal("0.00"),
                held_balance=Decimal("0.00"),
                lifetime_earned=Decimal("0.00"),
                lifetime_spent=Decimal("0.00"),
            )
            self.db.add(credit)
            await self.db.flush()

        # Check if user has enough credits
        if credit.available_balance < amount:
            raise InsufficientCreditsError(
                required=float(amount),
                available=float(credit.available_balance),
            )

        # Record balance before
        balance_before = credit.available_balance

        # Move credits from available to held
        credit.available_balance -= amount
        credit.held_balance += amount

        # Create transaction record
        transaction = CreditTransaction(
            user_id=user_id,
            type=TransactionType.HOLD.value,
            amount=amount,
            balance_before=balance_before,
            balance_after=credit.available_balance,
            execution_id=execution_id,
            transaction_data=metadata,
        )
        self.db.add(transaction)
        await self.db.flush()

        return transaction

    async def commit(
        self,
        hold_id: uuid.UUID,
        amount: Decimal | None = None,
        metadata: dict | None = None,
    ) -> CreditTransaction:
        """Commit a hold, finalizing the credit charge.

        If amount is less than the held amount, excess is returned to available_balance.
        If amount is None, the full held amount is committed.

        Args:
            hold_id: UUID of the original hold transaction
            amount: Amount to commit (None = full hold amount)
            metadata: Optional metadata for the transaction

        Returns:
            CreditTransaction record for the commit

        Raises:
            InvalidHoldError: If hold doesn't exist, is expired, or already processed
            ValueError: If amount exceeds held amount
        """
        # Get the original hold transaction
        result = await self.db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.id == hold_id)
            .where(CreditTransaction.type == TransactionType.HOLD.value)
        )
        hold_txn = result.scalar_one_or_none()

        if hold_txn is None:
            raise InvalidHoldError(hold_id=str(hold_id), reason="Hold not found")

        # Check if hold is expired
        hold_expiry = hold_txn.created_at + timedelta(hours=self.HOLD_EXPIRY_HOURS)
        if datetime.now(UTC) > hold_expiry:
            raise InvalidHoldError(hold_id=str(hold_id), reason="Hold has expired")

        # Check if hold is already processed (has a commit or release)
        result = await self.db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.hold_id == hold_id)
            .where(
                CreditTransaction.type.in_(
                    [
                        TransactionType.COMMIT.value,
                        TransactionType.RELEASE.value,
                    ]
                )
            )
        )
        if result.scalar_one_or_none() is not None:
            raise InvalidHoldError(hold_id=str(hold_id), reason="Hold already processed")

        held_amount = hold_txn.amount
        commit_amount = amount if amount is not None else held_amount

        if commit_amount > held_amount:
            raise ValueError(f"Commit amount {commit_amount} exceeds held amount {held_amount}")

        if commit_amount < 0:
            raise ValueError("Commit amount must be non-negative")

        # Lock the credit row for update
        result = await self.db.execute(
            select(Credit).where(Credit.user_id == hold_txn.user_id).with_for_update()
        )
        credit = result.scalar_one()

        # Record balance before
        balance_before = credit.available_balance

        # Deduct from held balance
        credit.held_balance -= held_amount

        # Return excess to available (if partial commit)
        excess = held_amount - commit_amount
        if excess > 0:
            credit.available_balance += excess

        # Update lifetime spent
        credit.lifetime_spent += commit_amount

        # Create transaction record
        transaction = CreditTransaction(
            user_id=hold_txn.user_id,
            type=TransactionType.COMMIT.value,
            amount=commit_amount,
            balance_before=balance_before,
            balance_after=credit.available_balance,
            hold_id=hold_id,
            execution_id=hold_txn.execution_id,
            transaction_data=metadata,
        )
        self.db.add(transaction)
        await self.db.flush()

        return transaction

    async def release(
        self,
        hold_id: uuid.UUID,
        metadata: dict | None = None,
    ) -> CreditTransaction:
        """Release a hold, returning credits to available balance.

        Args:
            hold_id: UUID of the original hold transaction
            metadata: Optional metadata for the transaction

        Returns:
            CreditTransaction record for the release

        Raises:
            InvalidHoldError: If hold doesn't exist, is expired, or already processed
        """
        # Get the original hold transaction
        result = await self.db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.id == hold_id)
            .where(CreditTransaction.type == TransactionType.HOLD.value)
        )
        hold_txn = result.scalar_one_or_none()

        if hold_txn is None:
            raise InvalidHoldError(hold_id=str(hold_id), reason="Hold not found")

        # Check if hold is already processed (has a commit or release)
        result = await self.db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.hold_id == hold_id)
            .where(
                CreditTransaction.type.in_(
                    [
                        TransactionType.COMMIT.value,
                        TransactionType.RELEASE.value,
                    ]
                )
            )
        )
        if result.scalar_one_or_none() is not None:
            raise InvalidHoldError(hold_id=str(hold_id), reason="Hold already processed")

        held_amount = hold_txn.amount

        # Lock the credit row for update
        result = await self.db.execute(
            select(Credit).where(Credit.user_id == hold_txn.user_id).with_for_update()
        )
        credit = result.scalar_one()

        # Record balance before
        balance_before = credit.available_balance

        # Return credits from held to available
        credit.held_balance -= held_amount
        credit.available_balance += held_amount

        # Create transaction record
        transaction = CreditTransaction(
            user_id=hold_txn.user_id,
            type=TransactionType.RELEASE.value,
            amount=held_amount,
            balance_before=balance_before,
            balance_after=credit.available_balance,
            hold_id=hold_id,
            execution_id=hold_txn.execution_id,
            transaction_data=metadata,
        )
        self.db.add(transaction)
        await self.db.flush()

        return transaction

    async def add_credits(
        self,
        user_id: uuid.UUID,
        amount: Decimal,
        transaction_type: TransactionType = TransactionType.GRANT,
        metadata: dict | None = None,
    ) -> CreditTransaction:
        """Add credits to a user's available balance.

        Used for purchases, grants (subscription), and refunds.

        Args:
            user_id: User's UUID
            amount: Amount to add (must be positive)
            transaction_type: Type of credit addition (PURCHASE, GRANT, or REFUND)
            metadata: Optional metadata for the transaction

        Returns:
            CreditTransaction record

        Raises:
            ValueError: If amount is not positive or invalid transaction type
        """
        if amount <= 0:
            raise ValueError("Credit amount must be positive")

        if transaction_type not in (
            TransactionType.PURCHASE,
            TransactionType.GRANT,
            TransactionType.REFUND,
        ):
            raise ValueError(f"Invalid transaction type for adding credits: {transaction_type}")

        # Lock the credit row for update
        result = await self.db.execute(
            select(Credit).where(Credit.user_id == user_id).with_for_update()
        )
        credit = result.scalar_one_or_none()

        if credit is None:
            credit = Credit(
                user_id=user_id,
                available_balance=Decimal("0.00"),
                held_balance=Decimal("0.00"),
                lifetime_earned=Decimal("0.00"),
                lifetime_spent=Decimal("0.00"),
            )
            self.db.add(credit)
            await self.db.flush()
            # Re-fetch with lock
            result = await self.db.execute(
                select(Credit).where(Credit.user_id == user_id).with_for_update()
            )
            credit = result.scalar_one()

        # Record balance before
        balance_before = credit.available_balance

        # Add credits
        credit.available_balance += amount
        credit.lifetime_earned += amount

        # Create transaction record
        transaction = CreditTransaction(
            user_id=user_id,
            type=transaction_type.value,
            amount=amount,
            balance_before=balance_before,
            balance_after=credit.available_balance,
            transaction_data=metadata,
        )
        self.db.add(transaction)
        await self.db.flush()

        return transaction

    async def get_transactions(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CreditTransaction]:
        """Get transaction history for a user.

        Args:
            user_id: User's UUID
            limit: Maximum number of transactions to return
            offset: Number of transactions to skip

        Returns:
            List of CreditTransaction records, most recent first
        """
        result = await self.db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .order_by(CreditTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

"""Test factories for Credit and CreditTransaction models."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import factory

from mcpworks_api.models import Credit, CreditTransaction, TransactionType


class CreditFactory(factory.Factory):
    """Factory for creating test Credit instances."""

    class Meta:
        model = Credit

    user_id = factory.LazyFunction(uuid.uuid4)
    available_balance = Decimal("500.00")
    held_balance = Decimal("0.00")
    lifetime_earned = Decimal("500.00")
    lifetime_spent = Decimal("0.00")
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class EmptyCreditFactory(CreditFactory):
    """Factory for creating credits with zero balance."""

    available_balance = Decimal("0.00")
    held_balance = Decimal("0.00")
    lifetime_earned = Decimal("0.00")
    lifetime_spent = Decimal("0.00")


class HighBalanceCreditFactory(CreditFactory):
    """Factory for creating credits with high balance."""

    available_balance = Decimal("10000.00")
    held_balance = Decimal("0.00")
    lifetime_earned = Decimal("10000.00")
    lifetime_spent = Decimal("0.00")


class CreditTransactionFactory(factory.Factory):
    """Factory for creating test CreditTransaction instances."""

    class Meta:
        model = CreditTransaction

    id = factory.LazyFunction(uuid.uuid4)
    user_id = factory.LazyFunction(uuid.uuid4)
    type = TransactionType.GRANT.value
    amount = Decimal("100.00")
    balance_before = Decimal("0.00")
    balance_after = Decimal("100.00")
    hold_id = None
    execution_id = None
    metadata = None
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class HoldTransactionFactory(CreditTransactionFactory):
    """Factory for creating hold transactions."""

    type = TransactionType.HOLD.value
    amount = Decimal("-50.00")
    balance_before = Decimal("500.00")
    balance_after = Decimal("450.00")


class CommitTransactionFactory(CreditTransactionFactory):
    """Factory for creating commit transactions."""

    type = TransactionType.COMMIT.value
    amount = Decimal("-50.00")
    balance_before = Decimal("50.00")  # held balance
    balance_after = Decimal("0.00")
    hold_id = factory.LazyFunction(uuid.uuid4)


class ReleaseTransactionFactory(CreditTransactionFactory):
    """Factory for creating release transactions."""

    type = TransactionType.RELEASE.value
    amount = Decimal("50.00")
    balance_before = Decimal("450.00")
    balance_after = Decimal("500.00")
    hold_id = factory.LazyFunction(uuid.uuid4)

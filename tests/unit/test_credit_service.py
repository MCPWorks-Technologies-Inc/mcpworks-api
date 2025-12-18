"""Unit tests for CreditService."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcpworks_api.core.exceptions import InsufficientCreditsError, InvalidHoldError
from mcpworks_api.models import Credit, CreditTransaction
from mcpworks_api.models.credit_transaction import TransactionType
from mcpworks_api.services.credit import CreditService


class TestGetBalance:
    """Tests for get_balance method."""

    @pytest.mark.asyncio
    async def test_get_balance_existing_user(self):
        """Test getting balance for user with existing credit record."""
        user_id = uuid.uuid4()
        mock_credit = Credit(
            user_id=user_id,
            available_balance=Decimal("100.00"),
            held_balance=Decimal("10.00"),
            lifetime_earned=Decimal("200.00"),
            lifetime_spent=Decimal("100.00"),
        )

        # Mock database session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_credit
        mock_db.execute.return_value = mock_result

        service = CreditService(mock_db)
        credit = await service.get_balance(user_id)

        assert credit.available_balance == Decimal("100.00")
        assert credit.held_balance == Decimal("10.00")

    @pytest.mark.asyncio
    async def test_get_balance_creates_new_record(self):
        """Test that get_balance creates record for new user."""
        user_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = CreditService(mock_db)
        credit = await service.get_balance(user_id)

        # Should have added a new credit record
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

        # New credit should have zero balances
        assert credit.available_balance == Decimal("0.00")
        assert credit.held_balance == Decimal("0.00")


class TestHold:
    """Tests for hold method."""

    @pytest.mark.asyncio
    async def test_hold_success(self):
        """Test successful credit hold."""
        user_id = uuid.uuid4()
        mock_credit = Credit(
            user_id=user_id,
            available_balance=Decimal("100.00"),
            held_balance=Decimal("0.00"),
            lifetime_earned=Decimal("100.00"),
            lifetime_spent=Decimal("0.00"),
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_credit
        mock_db.execute.return_value = mock_result

        service = CreditService(mock_db)
        txn = await service.hold(user_id, Decimal("30.00"))

        # Balance should be updated
        assert mock_credit.available_balance == Decimal("70.00")
        assert mock_credit.held_balance == Decimal("30.00")

        # Transaction should be recorded
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        assert txn.amount == Decimal("30.00")
        assert txn.type == TransactionType.HOLD.value

    @pytest.mark.asyncio
    async def test_hold_insufficient_credits(self):
        """Test hold fails when insufficient credits."""
        user_id = uuid.uuid4()
        mock_credit = Credit(
            user_id=user_id,
            available_balance=Decimal("20.00"),
            held_balance=Decimal("0.00"),
            lifetime_earned=Decimal("20.00"),
            lifetime_spent=Decimal("0.00"),
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_credit
        mock_db.execute.return_value = mock_result

        service = CreditService(mock_db)

        with pytest.raises(InsufficientCreditsError) as exc_info:
            await service.hold(user_id, Decimal("50.00"))

        assert exc_info.value.details["required"] == 50.0
        assert exc_info.value.details["available"] == 20.0

    @pytest.mark.asyncio
    async def test_hold_negative_amount_rejected(self):
        """Test hold rejects negative amounts."""
        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        service = CreditService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.hold(user_id, Decimal("-10.00"))

        assert "positive" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_hold_zero_amount_rejected(self):
        """Test hold rejects zero amount."""
        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        service = CreditService(mock_db)

        with pytest.raises(ValueError):
            await service.hold(user_id, Decimal("0"))


class TestCommit:
    """Tests for commit method."""

    @pytest.mark.asyncio
    async def test_commit_full_amount(self):
        """Test committing full held amount."""
        user_id = uuid.uuid4()
        hold_id = uuid.uuid4()

        mock_hold_txn = CreditTransaction(
            id=hold_id,
            user_id=user_id,
            type=TransactionType.HOLD.value,
            amount=Decimal("30.00"),
            balance_before=Decimal("100.00"),
            balance_after=Decimal("70.00"),
        )
        mock_hold_txn.created_at = datetime.now(timezone.utc)

        mock_credit = Credit(
            user_id=user_id,
            available_balance=Decimal("70.00"),
            held_balance=Decimal("30.00"),
            lifetime_earned=Decimal("100.00"),
            lifetime_spent=Decimal("0.00"),
        )

        mock_db = AsyncMock()

        # First call returns hold transaction, second returns None (no existing commit/release)
        # Third call returns credit record
        mock_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_hold_txn)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(scalar_one=MagicMock(return_value=mock_credit)),
        ]
        mock_db.execute.side_effect = mock_results

        service = CreditService(mock_db)
        txn = await service.commit(hold_id)

        # Held balance should be deducted
        assert mock_credit.held_balance == Decimal("0.00")
        assert mock_credit.lifetime_spent == Decimal("30.00")
        assert txn.amount == Decimal("30.00")
        assert txn.type == TransactionType.COMMIT.value

    @pytest.mark.asyncio
    async def test_commit_partial_amount(self):
        """Test committing partial amount returns excess."""
        user_id = uuid.uuid4()
        hold_id = uuid.uuid4()

        mock_hold_txn = CreditTransaction(
            id=hold_id,
            user_id=user_id,
            type=TransactionType.HOLD.value,
            amount=Decimal("30.00"),
            balance_before=Decimal("100.00"),
            balance_after=Decimal("70.00"),
        )
        mock_hold_txn.created_at = datetime.now(timezone.utc)

        mock_credit = Credit(
            user_id=user_id,
            available_balance=Decimal("70.00"),
            held_balance=Decimal("30.00"),
            lifetime_earned=Decimal("100.00"),
            lifetime_spent=Decimal("0.00"),
        )

        mock_db = AsyncMock()
        mock_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_hold_txn)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(scalar_one=MagicMock(return_value=mock_credit)),
        ]
        mock_db.execute.side_effect = mock_results

        service = CreditService(mock_db)
        txn = await service.commit(hold_id, amount=Decimal("20.00"))

        # Excess should be returned to available
        assert mock_credit.held_balance == Decimal("0.00")
        assert mock_credit.available_balance == Decimal("80.00")  # 70 + 10 excess
        assert mock_credit.lifetime_spent == Decimal("20.00")
        assert txn.amount == Decimal("20.00")

    @pytest.mark.asyncio
    async def test_commit_exceeds_held_amount_rejected(self):
        """Test commit fails if amount exceeds held."""
        user_id = uuid.uuid4()
        hold_id = uuid.uuid4()

        mock_hold_txn = CreditTransaction(
            id=hold_id,
            user_id=user_id,
            type=TransactionType.HOLD.value,
            amount=Decimal("30.00"),
            balance_before=Decimal("100.00"),
            balance_after=Decimal("70.00"),
        )
        mock_hold_txn.created_at = datetime.now(timezone.utc)

        mock_db = AsyncMock()
        mock_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_hold_txn)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        mock_db.execute.side_effect = mock_results

        service = CreditService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.commit(hold_id, amount=Decimal("50.00"))

        assert "exceeds held amount" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_commit_invalid_hold_not_found(self):
        """Test commit fails for non-existent hold."""
        hold_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = CreditService(mock_db)

        with pytest.raises(InvalidHoldError) as exc_info:
            await service.commit(hold_id)

        assert "not found" in exc_info.value.details["reason"].lower()

    @pytest.mark.asyncio
    async def test_commit_expired_hold_rejected(self):
        """Test commit fails for expired hold."""
        user_id = uuid.uuid4()
        hold_id = uuid.uuid4()

        mock_hold_txn = CreditTransaction(
            id=hold_id,
            user_id=user_id,
            type=TransactionType.HOLD.value,
            amount=Decimal("30.00"),
            balance_before=Decimal("100.00"),
            balance_after=Decimal("70.00"),
        )
        # Hold created 2 hours ago (expired)
        mock_hold_txn.created_at = datetime.now(timezone.utc) - timedelta(hours=2)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_hold_txn
        mock_db.execute.return_value = mock_result

        service = CreditService(mock_db)

        with pytest.raises(InvalidHoldError) as exc_info:
            await service.commit(hold_id)

        assert "expired" in exc_info.value.details["reason"].lower()

    @pytest.mark.asyncio
    async def test_commit_already_processed_rejected(self):
        """Test commit fails for already processed hold."""
        user_id = uuid.uuid4()
        hold_id = uuid.uuid4()

        mock_hold_txn = CreditTransaction(
            id=hold_id,
            user_id=user_id,
            type=TransactionType.HOLD.value,
            amount=Decimal("30.00"),
            balance_before=Decimal("100.00"),
            balance_after=Decimal("70.00"),
        )
        mock_hold_txn.created_at = datetime.now(timezone.utc)

        # Existing commit transaction
        mock_commit_txn = CreditTransaction(
            id=uuid.uuid4(),
            user_id=user_id,
            type=TransactionType.COMMIT.value,
            amount=Decimal("30.00"),
            balance_before=Decimal("70.00"),
            balance_after=Decimal("70.00"),
            hold_id=hold_id,
        )

        mock_db = AsyncMock()
        mock_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_hold_txn)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_commit_txn)),
        ]
        mock_db.execute.side_effect = mock_results

        service = CreditService(mock_db)

        with pytest.raises(InvalidHoldError) as exc_info:
            await service.commit(hold_id)

        assert "already processed" in exc_info.value.details["reason"].lower()


class TestRelease:
    """Tests for release method."""

    @pytest.mark.asyncio
    async def test_release_success(self):
        """Test successful credit release."""
        user_id = uuid.uuid4()
        hold_id = uuid.uuid4()

        mock_hold_txn = CreditTransaction(
            id=hold_id,
            user_id=user_id,
            type=TransactionType.HOLD.value,
            amount=Decimal("30.00"),
            balance_before=Decimal("100.00"),
            balance_after=Decimal("70.00"),
        )
        mock_hold_txn.created_at = datetime.now(timezone.utc)

        mock_credit = Credit(
            user_id=user_id,
            available_balance=Decimal("70.00"),
            held_balance=Decimal("30.00"),
            lifetime_earned=Decimal("100.00"),
            lifetime_spent=Decimal("0.00"),
        )

        mock_db = AsyncMock()
        mock_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_hold_txn)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(scalar_one=MagicMock(return_value=mock_credit)),
        ]
        mock_db.execute.side_effect = mock_results

        service = CreditService(mock_db)
        txn = await service.release(hold_id)

        # Credits should be returned to available
        assert mock_credit.available_balance == Decimal("100.00")
        assert mock_credit.held_balance == Decimal("0.00")
        assert txn.amount == Decimal("30.00")
        assert txn.type == TransactionType.RELEASE.value

    @pytest.mark.asyncio
    async def test_release_invalid_hold_not_found(self):
        """Test release fails for non-existent hold."""
        hold_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = CreditService(mock_db)

        with pytest.raises(InvalidHoldError) as exc_info:
            await service.release(hold_id)

        assert "not found" in exc_info.value.details["reason"].lower()


class TestAddCredits:
    """Tests for add_credits method."""

    @pytest.mark.asyncio
    async def test_add_credits_grant(self):
        """Test adding credits via grant."""
        user_id = uuid.uuid4()
        mock_credit = Credit(
            user_id=user_id,
            available_balance=Decimal("50.00"),
            held_balance=Decimal("0.00"),
            lifetime_earned=Decimal("50.00"),
            lifetime_spent=Decimal("0.00"),
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_credit
        mock_db.execute.return_value = mock_result

        service = CreditService(mock_db)
        txn = await service.add_credits(
            user_id, Decimal("100.00"), TransactionType.GRANT
        )

        assert mock_credit.available_balance == Decimal("150.00")
        assert mock_credit.lifetime_earned == Decimal("150.00")
        assert txn.amount == Decimal("100.00")
        assert txn.type == TransactionType.GRANT.value

    @pytest.mark.asyncio
    async def test_add_credits_purchase(self):
        """Test adding credits via purchase."""
        user_id = uuid.uuid4()
        mock_credit = Credit(
            user_id=user_id,
            available_balance=Decimal("0.00"),
            held_balance=Decimal("0.00"),
            lifetime_earned=Decimal("0.00"),
            lifetime_spent=Decimal("0.00"),
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_credit
        mock_db.execute.return_value = mock_result

        service = CreditService(mock_db)
        txn = await service.add_credits(
            user_id, Decimal("500.00"), TransactionType.PURCHASE
        )

        assert mock_credit.available_balance == Decimal("500.00")
        assert txn.type == TransactionType.PURCHASE.value

    @pytest.mark.asyncio
    async def test_add_credits_refund(self):
        """Test adding credits via refund."""
        user_id = uuid.uuid4()
        mock_credit = Credit(
            user_id=user_id,
            available_balance=Decimal("10.00"),
            held_balance=Decimal("0.00"),
            lifetime_earned=Decimal("100.00"),
            lifetime_spent=Decimal("90.00"),
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_credit
        mock_db.execute.return_value = mock_result

        service = CreditService(mock_db)
        txn = await service.add_credits(
            user_id, Decimal("25.00"), TransactionType.REFUND
        )

        assert mock_credit.available_balance == Decimal("35.00")
        assert txn.type == TransactionType.REFUND.value

    @pytest.mark.asyncio
    async def test_add_credits_invalid_type_rejected(self):
        """Test add_credits rejects invalid transaction types."""
        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        service = CreditService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.add_credits(user_id, Decimal("100.00"), TransactionType.HOLD)

        assert "invalid transaction type" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_add_credits_negative_amount_rejected(self):
        """Test add_credits rejects negative amounts."""
        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        service = CreditService(mock_db)

        with pytest.raises(ValueError):
            await service.add_credits(user_id, Decimal("-50.00"), TransactionType.GRANT)


class TestGetTransactions:
    """Tests for get_transactions method."""

    @pytest.mark.asyncio
    async def test_get_transactions_returns_list(self):
        """Test getting transaction history."""
        user_id = uuid.uuid4()
        mock_txns = [
            CreditTransaction(
                id=uuid.uuid4(),
                user_id=user_id,
                type=TransactionType.GRANT.value,
                amount=Decimal("100.00"),
                balance_before=Decimal("0.00"),
                balance_after=Decimal("100.00"),
            ),
            CreditTransaction(
                id=uuid.uuid4(),
                user_id=user_id,
                type=TransactionType.HOLD.value,
                amount=Decimal("20.00"),
                balance_before=Decimal("100.00"),
                balance_after=Decimal("80.00"),
            ),
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_txns
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        service = CreditService(mock_db)
        txns = await service.get_transactions(user_id)

        assert len(txns) == 2
        assert txns[0].type == TransactionType.GRANT.value
        assert txns[1].type == TransactionType.HOLD.value

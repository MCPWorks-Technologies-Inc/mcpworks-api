"""Unit tests for ExecutionService."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcpworks_api.core.exceptions import (
    InsufficientCreditsError,
    InsufficientTierError,
    ServiceUnavailableError,
)
from mcpworks_api.models import CreditTransaction, Execution, ExecutionStatus, Service, ServiceStatus
from mcpworks_api.services.execution import ExecutionService


class TestStartExecution:
    """Tests for start_execution method."""

    @pytest.mark.asyncio
    async def test_start_execution_service_not_found(self):
        """Test that missing agent service raises error."""
        mock_db = AsyncMock()

        # Mock get_service to return None
        with patch.object(ExecutionService, "__init__", return_value=None):
            service = ExecutionService.__new__(ExecutionService)
            service.db = mock_db
            service.router = MagicMock()
            service.router.get_service = AsyncMock(return_value=None)
            service.credit_service = MagicMock()

            with pytest.raises(ServiceUnavailableError):
                await service.start_execution(
                    workflow_id="wf_123",
                    user_id=uuid.uuid4(),
                    user_tier="free",
                )

    @pytest.mark.asyncio
    async def test_start_execution_service_unavailable(self):
        """Test that unavailable service raises error."""
        mock_db = AsyncMock()
        mock_service = MagicMock(spec=Service)
        mock_service.is_available = False

        with patch.object(ExecutionService, "__init__", return_value=None):
            service = ExecutionService.__new__(ExecutionService)
            service.db = mock_db
            service.router = MagicMock()
            service.router.get_service = AsyncMock(return_value=mock_service)
            service.credit_service = MagicMock()

            with pytest.raises(ServiceUnavailableError):
                await service.start_execution(
                    workflow_id="wf_123",
                    user_id=uuid.uuid4(),
                    user_tier="free",
                )

    @pytest.mark.asyncio
    async def test_start_execution_tier_check_fails(self):
        """Test that insufficient tier raises error."""
        mock_db = AsyncMock()
        mock_service = MagicMock(spec=Service)
        mock_service.is_available = True
        mock_service.tier_required = "pro"

        with patch.object(ExecutionService, "__init__", return_value=None):
            service = ExecutionService.__new__(ExecutionService)
            service.db = mock_db
            service.router = MagicMock()
            service.router.get_service = AsyncMock(return_value=mock_service)
            service.router.can_access_service = MagicMock(return_value=False)
            service.credit_service = MagicMock()

            with pytest.raises(InsufficientTierError):
                await service.start_execution(
                    workflow_id="wf_123",
                    user_id=uuid.uuid4(),
                    user_tier="free",
                )


class TestHandleCallback:
    """Tests for handle_callback method."""

    @pytest.mark.asyncio
    async def test_callback_execution_not_found(self):
        """Test that callback with invalid execution raises error."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(ExecutionService, "__init__", return_value=None):
            service = ExecutionService.__new__(ExecutionService)
            service.db = mock_db
            service.router = MagicMock()
            service.credit_service = MagicMock()

            with pytest.raises(ValueError, match="not found"):
                await service.handle_callback(
                    execution_id=uuid.uuid4(),
                    status="completed",
                )

    @pytest.mark.asyncio
    async def test_callback_execution_already_terminal(self):
        """Test that callback on completed execution raises error."""
        mock_db = AsyncMock()
        mock_execution = MagicMock(spec=Execution)
        mock_execution.is_terminal = True
        mock_execution.status = "completed"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_execution
        mock_db.execute.return_value = mock_result

        with patch.object(ExecutionService, "__init__", return_value=None):
            service = ExecutionService.__new__(ExecutionService)
            service.db = mock_db
            service.router = MagicMock()
            service.credit_service = MagicMock()

            with pytest.raises(ValueError, match="terminal state"):
                await service.handle_callback(
                    execution_id=uuid.uuid4(),
                    status="completed",
                )

    @pytest.mark.asyncio
    async def test_callback_success_commits_credits(self):
        """Test that successful callback commits credits."""
        mock_db = AsyncMock()
        execution_id = uuid.uuid4()
        hold_txn_id = uuid.uuid4()

        mock_execution = MagicMock(spec=Execution)
        mock_execution.id = execution_id
        mock_execution.is_terminal = False
        mock_execution.hold_transaction_id = hold_txn_id
        mock_execution.workflow_id = "wf_123"

        mock_hold_txn = MagicMock(spec=CreditTransaction)
        mock_hold_txn.id = hold_txn_id
        mock_hold_txn.amount = Decimal("1.00")

        # Setup execute to return different results for each call
        call_count = 0
        def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                mock_result.scalar_one_or_none.return_value = mock_execution
            else:
                mock_result.scalar_one_or_none.return_value = mock_hold_txn
            return mock_result

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch.object(ExecutionService, "__init__", return_value=None):
            service = ExecutionService.__new__(ExecutionService)
            service.db = mock_db
            service.router = MagicMock()
            service.credit_service = MagicMock()
            service.credit_service.commit = AsyncMock()

            result, action, amount = await service.handle_callback(
                execution_id=execution_id,
                status="completed",
                result_data={"output": "success"},
            )

            assert action == "committed"
            assert amount == Decimal("1.00")
            service.credit_service.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_failure_releases_credits(self):
        """Test that failed callback releases credits."""
        mock_db = AsyncMock()
        execution_id = uuid.uuid4()
        hold_txn_id = uuid.uuid4()

        mock_execution = MagicMock(spec=Execution)
        mock_execution.id = execution_id
        mock_execution.is_terminal = False
        mock_execution.hold_transaction_id = hold_txn_id
        mock_execution.workflow_id = "wf_123"

        mock_hold_txn = MagicMock(spec=CreditTransaction)
        mock_hold_txn.id = hold_txn_id
        mock_hold_txn.amount = Decimal("1.00")

        call_count = 0
        def execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                mock_result.scalar_one_or_none.return_value = mock_execution
            else:
                mock_result.scalar_one_or_none.return_value = mock_hold_txn
            return mock_result

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch.object(ExecutionService, "__init__", return_value=None):
            service = ExecutionService.__new__(ExecutionService)
            service.db = mock_db
            service.router = MagicMock()
            service.credit_service = MagicMock()
            service.credit_service.release = AsyncMock()

            result, action, amount = await service.handle_callback(
                execution_id=execution_id,
                status="failed",
                error_message="Workflow error",
                error_code="WF_ERROR",
            )

            assert action == "released"
            assert amount == Decimal("1.00")
            service.credit_service.release.assert_called_once()


class TestGetExecution:
    """Tests for get_execution method."""

    @pytest.mark.asyncio
    async def test_get_existing_execution(self):
        """Test getting an existing execution."""
        mock_db = AsyncMock()
        execution_id = uuid.uuid4()

        mock_execution = MagicMock(spec=Execution)
        mock_execution.id = execution_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_execution
        mock_db.execute.return_value = mock_result

        with patch.object(ExecutionService, "__init__", return_value=None):
            service = ExecutionService.__new__(ExecutionService)
            service.db = mock_db
            service.router = MagicMock()
            service.credit_service = MagicMock()

            result = await service.get_execution(execution_id)

            assert result is not None
            assert result.id == execution_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_execution(self):
        """Test getting a nonexistent execution."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(ExecutionService, "__init__", return_value=None):
            service = ExecutionService.__new__(ExecutionService)
            service.db = mock_db
            service.router = MagicMock()
            service.credit_service = MagicMock()

            result = await service.get_execution(uuid.uuid4())

            assert result is None


class TestCancelExecution:
    """Tests for cancel_execution method."""

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_execution(self):
        """Test cancelling nonexistent execution raises error."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(ExecutionService, "__init__", return_value=None):
            service = ExecutionService.__new__(ExecutionService)
            service.db = mock_db
            service.router = MagicMock()
            service.credit_service = MagicMock()

            with pytest.raises(ValueError, match="not found"):
                await service.cancel_execution(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancel_completed_execution(self):
        """Test cancelling completed execution raises error."""
        mock_db = AsyncMock()

        mock_execution = MagicMock(spec=Execution)
        mock_execution.is_terminal = True
        mock_execution.status = "completed"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_execution
        mock_db.execute.return_value = mock_result

        with patch.object(ExecutionService, "__init__", return_value=None):
            service = ExecutionService.__new__(ExecutionService)
            service.db = mock_db
            service.router = MagicMock()
            service.credit_service = MagicMock()

            with pytest.raises(ValueError, match="Cannot cancel"):
                await service.cancel_execution(uuid.uuid4())


class TestExecutionStatus:
    """Tests for ExecutionStatus enum."""

    def test_execution_status_values(self):
        """Test all execution status values exist."""
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.CANCELLED.value == "cancelled"
        assert ExecutionStatus.TIMED_OUT.value == "timed_out"

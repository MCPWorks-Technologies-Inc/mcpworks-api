"""Unit tests for ExecutionService."""

import uuid

import pytest

from mcpworks_api.models import (
    Execution,
    ExecutionStatus,
    User,
)
from mcpworks_api.services.execution import ExecutionService


@pytest.fixture
async def test_user(db):
    """Create a test user."""
    user = User(
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed_password",
        name="Test User",
        tier="free",
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def test_execution(db, test_user):
    """Create a test execution."""
    execution = Execution(
        user_id=test_user.id,
        workflow_id="test-workflow-123",
        status=ExecutionStatus.PENDING.value,
        input_data={"key": "value"},
    )
    db.add(execution)
    await db.flush()
    return execution


@pytest.fixture
async def running_execution(db, test_user):
    """Create a running execution."""
    execution = Execution(
        user_id=test_user.id,
        workflow_id="test-workflow-456",
        status=ExecutionStatus.RUNNING.value,
        input_data={"key": "value"},
    )
    db.add(execution)
    await db.flush()
    return execution


@pytest.fixture
async def completed_execution(db, test_user):
    """Create a completed execution."""
    execution = Execution(
        user_id=test_user.id,
        workflow_id="test-workflow-789",
        status=ExecutionStatus.COMPLETED.value,
        input_data={"key": "value"},
        result_data={"output": "result"},
    )
    db.add(execution)
    await db.flush()
    return execution


class TestExecutionServiceGetExecution:
    """Tests for ExecutionService.get_execution()."""

    @pytest.mark.asyncio
    async def test_get_execution_found(self, db, test_execution):
        """Test getting an existing execution."""
        service = ExecutionService(db)

        execution = await service.get_execution(test_execution.id)

        assert execution is not None
        assert execution.id == test_execution.id
        assert execution.workflow_id == "test-workflow-123"

    @pytest.mark.asyncio
    async def test_get_execution_not_found(self, db):
        """Test getting a non-existent execution returns None."""
        service = ExecutionService(db)

        execution = await service.get_execution(uuid.uuid4())

        assert execution is None


class TestExecutionServiceGetUserExecutions:
    """Tests for ExecutionService.get_user_executions()."""

    @pytest.mark.asyncio
    async def test_get_user_executions_empty(self, db, test_user):
        """Test getting executions for user with none."""
        service = ExecutionService(db)

        executions, total = await service.get_user_executions(test_user.id)

        assert executions == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_user_executions_multiple(self, db, test_user):
        """Test getting multiple executions for user."""
        # Create multiple executions
        for i in range(3):
            execution = Execution(
                user_id=test_user.id,
                workflow_id=f"workflow-{i}",
                status=ExecutionStatus.PENDING.value,
            )
            db.add(execution)
        await db.flush()

        service = ExecutionService(db)

        executions, total = await service.get_user_executions(test_user.id)

        assert len(executions) == 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_get_user_executions_pagination(self, db, test_user):
        """Test pagination of user executions."""
        # Create 5 executions
        for i in range(5):
            execution = Execution(
                user_id=test_user.id,
                workflow_id=f"workflow-{i}",
                status=ExecutionStatus.PENDING.value,
            )
            db.add(execution)
        await db.flush()

        service = ExecutionService(db)

        # Get first page
        page1, total = await service.get_user_executions(test_user.id, limit=2, offset=0)
        assert len(page1) == 2
        assert total == 5

        # Get second page
        page2, _ = await service.get_user_executions(test_user.id, limit=2, offset=2)
        assert len(page2) == 2

        # Get third page (partial)
        page3, _ = await service.get_user_executions(test_user.id, limit=2, offset=4)
        assert len(page3) == 1

    @pytest.mark.asyncio
    async def test_get_user_executions_only_own(self, db, test_user):
        """Test that only the user's executions are returned."""
        # Create execution for test_user
        execution1 = Execution(
            user_id=test_user.id,
            workflow_id="my-workflow",
            status=ExecutionStatus.PENDING.value,
        )
        db.add(execution1)

        # Create another user with execution
        other_user = User(
            email=f"other-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password",
            tier="free",
            status="active",
        )
        db.add(other_user)
        await db.flush()

        execution2 = Execution(
            user_id=other_user.id,
            workflow_id="other-workflow",
            status=ExecutionStatus.PENDING.value,
        )
        db.add(execution2)
        await db.flush()

        service = ExecutionService(db)

        executions, total = await service.get_user_executions(test_user.id)

        assert len(executions) == 1
        assert total == 1
        assert executions[0].workflow_id == "my-workflow"


class TestExecutionServiceCancelExecution:
    """Tests for ExecutionService.cancel_execution()."""

    @pytest.mark.asyncio
    async def test_cancel_pending_execution(self, db, test_execution):
        """Test cancelling a pending execution."""
        service = ExecutionService(db)

        cancelled = await service.cancel_execution(test_execution.id)

        assert cancelled.status == ExecutionStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_cancel_running_execution(self, db, running_execution):
        """Test cancelling a running execution."""
        service = ExecutionService(db)

        cancelled = await service.cancel_execution(running_execution.id)

        assert cancelled.status == ExecutionStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_cancel_completed_execution_fails(self, db, completed_execution):
        """Test that completed execution cannot be cancelled."""
        service = ExecutionService(db)

        with pytest.raises(ValueError) as exc_info:
            await service.cancel_execution(completed_execution.id)

        assert "Cannot cancel" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_execution_fails(self, db):
        """Test cancelling non-existent execution fails."""
        service = ExecutionService(db)

        with pytest.raises(ValueError) as exc_info:
            await service.cancel_execution(uuid.uuid4())

        assert "not found" in str(exc_info.value)


class TestExecutionServiceHandleCallback:
    """Tests for ExecutionService.handle_callback()."""

    @pytest.mark.asyncio
    async def test_handle_callback_completed(self, db, running_execution):
        """Test handling a successful completion callback."""
        service = ExecutionService(db)

        execution = await service.handle_callback(
            execution_id=running_execution.id,
            status="completed",
            result_data={"output": "success"},
        )

        assert execution.status == ExecutionStatus.COMPLETED.value
        # ORDER-020: result_data is intentionally not persisted (PII risk)
        assert execution.result_data is None

    @pytest.mark.asyncio
    async def test_handle_callback_failed(self, db, running_execution):
        """Test handling a failure callback."""
        service = ExecutionService(db)

        execution = await service.handle_callback(
            execution_id=running_execution.id,
            status="failed",
            error_message="Something went wrong",
            error_code="TEST_ERROR",
        )

        assert execution.status == ExecutionStatus.FAILED.value
        assert execution.error_message == "Something went wrong"
        assert execution.error_code == "TEST_ERROR"

    @pytest.mark.asyncio
    async def test_handle_callback_not_found(self, db):
        """Test callback for non-existent execution fails."""
        service = ExecutionService(db)

        with pytest.raises(ValueError) as exc_info:
            await service.handle_callback(
                execution_id=uuid.uuid4(),
                status="completed",
            )

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handle_callback_already_completed(self, db, completed_execution):
        """Test callback for already completed execution fails."""
        service = ExecutionService(db)

        with pytest.raises(ValueError) as exc_info:
            await service.handle_callback(
                execution_id=completed_execution.id,
                status="completed",
            )

        assert "terminal state" in str(exc_info.value)

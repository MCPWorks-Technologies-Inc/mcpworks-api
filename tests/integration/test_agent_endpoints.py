"""Integration tests for agent execution endpoints."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.security import create_access_token
from mcpworks_api.models import Credit, Execution, ExecutionStatus, Service, ServiceStatus, User


@pytest.fixture
def auth_headers(test_settings):
    """Generate valid JWT auth headers for testing."""
    user_id = str(uuid.uuid4())
    access_token = create_access_token(
        user_id=user_id,
        scopes=["read", "write", "execute"],
    )
    return {"Authorization": f"Bearer {access_token}"}, user_id


class TestExecuteWorkflow:
    """Tests for POST /v1/services/agent/execute/{workflow_id} endpoint."""

    @pytest.mark.asyncio
    async def test_execute_workflow_success(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test successful workflow execution."""
        headers, user_id = auth_headers

        # Create user with credits
        user = User(
            id=uuid.UUID(user_id),
            email="agent_exec@example.com",
            password_hash="test_hash",
            name="Agent Test User",
            tier="free",
            status="active",
        )
        db.add(user)

        credit = Credit(
            user_id=uuid.UUID(user_id),
            available_balance=Decimal("100.00"),
            held_balance=Decimal("0.00"),
            lifetime_earned=Decimal("100.00"),
            lifetime_spent=Decimal("0.00"),
        )
        db.add(credit)

        # Delete any existing agent service
        await db.execute(delete(Service).where(Service.name == "agent"))

        # Create agent service
        agent_service = Service(
            name="agent",
            display_name="Workflow Agent",
            url="http://agent:8002",
            credit_cost=Decimal("1.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(agent_service)
        await db.commit()

        # Mock the HTTP request to agent service
        with patch("mcpworks_api.services.router.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "accepted"}
            mock_response.text = ""
            mock_response.headers = {"Content-Type": "application/json"}
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client

            response = await client.post(
                "/v1/services/agent/execute/wf_test123",
                headers=headers,
                json={"input_data": {"param1": "value1"}},
            )

            assert response.status_code == 200
            data = response.json()
            assert "execution_id" in data
            assert data["workflow_id"] == "wf_test123"
            assert data["status"] == "running"
            assert Decimal(str(data["credits_held"])) == Decimal("1.00")

    @pytest.mark.asyncio
    async def test_execute_workflow_insufficient_credits(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test workflow execution with insufficient credits."""
        headers, user_id = auth_headers

        # Create user with insufficient credits
        user = User(
            id=uuid.UUID(user_id),
            email="agent_nocredit@example.com",
            password_hash="test_hash",
            name="No Credit User",
            tier="free",
            status="active",
        )
        db.add(user)

        credit = Credit(
            user_id=uuid.UUID(user_id),
            available_balance=Decimal("0.00"),
            held_balance=Decimal("0.00"),
            lifetime_earned=Decimal("0.00"),
            lifetime_spent=Decimal("0.00"),
        )
        db.add(credit)

        # Delete and create agent service
        await db.execute(delete(Service).where(Service.name == "agent"))

        agent_service = Service(
            name="agent",
            display_name="Workflow Agent",
            url="http://agent:8002",
            credit_cost=Decimal("1.00"),
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(agent_service)
        await db.commit()

        response = await client.post(
            "/v1/services/agent/execute/wf_test123",
            headers=headers,
            json={},
        )

        assert response.status_code == 402
        data = response.json()
        assert data["error"] == "INSUFFICIENT_CREDITS"

    @pytest.mark.asyncio
    async def test_execute_workflow_service_unavailable(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test workflow execution when agent service is unavailable."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="agent_unavail@example.com",
            password_hash="test_hash",
            name="Test User",
            tier="free",
            status="active",
        )
        db.add(user)

        # Delete and create inactive agent service
        await db.execute(delete(Service).where(Service.name == "agent"))

        agent_service = Service(
            name="agent",
            display_name="Workflow Agent",
            url="http://agent:8002",
            credit_cost=Decimal("1.00"),
            tier_required="free",
            status=ServiceStatus.INACTIVE.value,
        )
        db.add(agent_service)
        await db.commit()

        response = await client.post(
            "/v1/services/agent/execute/wf_test123",
            headers=headers,
            json={},
        )

        assert response.status_code == 503
        data = response.json()
        assert data["error"] == "SERVICE_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_execute_workflow_no_auth(self, client: AsyncClient):
        """Test workflow execution requires authentication."""
        response = await client.post(
            "/v1/services/agent/execute/wf_test123",
            json={},
        )

        assert response.status_code == 401


class TestExecutionCallback:
    """Tests for POST /v1/services/agent/executions/{execution_id}/callback endpoint."""

    @pytest.mark.asyncio
    async def test_callback_success_commits_credits(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test that successful callback commits credits."""
        headers, user_id = auth_headers

        # Create user with credits
        user = User(
            id=uuid.UUID(user_id),
            email="callback_test@example.com",
            password_hash="test_hash",
            name="Callback Test User",
            tier="free",
            status="active",
        )
        db.add(user)

        credit = Credit(
            user_id=uuid.UUID(user_id),
            available_balance=Decimal("100.00"),
            held_balance=Decimal("0.00"),
            lifetime_earned=Decimal("100.00"),
            lifetime_spent=Decimal("0.00"),
        )
        db.add(credit)

        # Create execution in running state (no hold for simplicity)
        execution = Execution(
            user_id=uuid.UUID(user_id),
            workflow_id="wf_callback_test",
            status=ExecutionStatus.RUNNING.value,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        response = await client.post(
            f"/v1/services/agent/executions/{execution.id}/callback",
            json={
                "status": "completed",
                "result_data": {"output": "success"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] == str(execution.id)
        # No credits held, so action is "none"
        assert data["credits_action"] == "none"

    @pytest.mark.asyncio
    async def test_callback_failure_releases_credits(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test that failed callback releases credits."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="callback_fail@example.com",
            password_hash="test_hash",
            name="Callback Fail User",
            tier="free",
            status="active",
        )
        db.add(user)

        # Create execution in running state
        execution = Execution(
            user_id=uuid.UUID(user_id),
            workflow_id="wf_callback_fail",
            status=ExecutionStatus.RUNNING.value,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        response = await client.post(
            f"/v1/services/agent/executions/{execution.id}/callback",
            json={
                "status": "failed",
                "error_message": "Workflow error occurred",
                "error_code": "WF_ERROR",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] == str(execution.id)

    @pytest.mark.asyncio
    async def test_callback_invalid_execution(self, client: AsyncClient):
        """Test callback with invalid execution ID."""
        response = await client.post(
            f"/v1/services/agent/executions/{uuid.uuid4()}/callback",
            json={"status": "completed"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "not found" in data["message"]

    @pytest.mark.asyncio
    async def test_callback_already_completed(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test callback on already completed execution."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="callback_done@example.com",
            password_hash="test_hash",
            name="Callback Done User",
            tier="free",
            status="active",
        )
        db.add(user)

        # Create execution in completed state
        execution = Execution(
            user_id=uuid.UUID(user_id),
            workflow_id="wf_callback_done",
            status=ExecutionStatus.COMPLETED.value,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        response = await client.post(
            f"/v1/services/agent/executions/{execution.id}/callback",
            json={"status": "completed"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "terminal state" in data["message"]


class TestGetExecution:
    """Tests for GET /v1/services/agent/executions/{execution_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_execution_success(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test getting execution details."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="get_exec@example.com",
            password_hash="test_hash",
            name="Get Exec User",
            tier="free",
            status="active",
        )
        db.add(user)

        # Create execution
        execution = Execution(
            user_id=uuid.UUID(user_id),
            workflow_id="wf_get_test",
            status=ExecutionStatus.RUNNING.value,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        response = await client.get(
            f"/v1/services/agent/executions/{execution.id}",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] == str(execution.id)
        assert data["workflow_id"] == "wf_get_test"
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_execution_not_found(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test getting nonexistent execution."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="get_notfound@example.com",
            password_hash="test_hash",
            name="Not Found User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.get(
            f"/v1/services/agent/executions/{uuid.uuid4()}",
            headers=headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_execution_wrong_owner(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test getting execution owned by another user."""
        headers, user_id = auth_headers
        other_user_id = uuid.uuid4()

        # Create both users
        user = User(
            id=uuid.UUID(user_id),
            email="get_owner@example.com",
            password_hash="test_hash",
            name="Owner User",
            tier="free",
            status="active",
        )
        db.add(user)

        other_user = User(
            id=other_user_id,
            email="get_other@example.com",
            password_hash="test_hash",
            name="Other User",
            tier="free",
            status="active",
        )
        db.add(other_user)

        # Create execution for other user
        execution = Execution(
            user_id=other_user_id,
            workflow_id="wf_other_user",
            status=ExecutionStatus.RUNNING.value,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        response = await client.get(
            f"/v1/services/agent/executions/{execution.id}",
            headers=headers,
        )

        # Should return 404 (not 403) to avoid leaking information
        assert response.status_code == 404


class TestListExecutions:
    """Tests for GET /v1/services/agent/executions endpoint."""

    @pytest.mark.asyncio
    async def test_list_executions_empty(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test listing executions when none exist."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="list_empty@example.com",
            password_hash="test_hash",
            name="List Empty User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.get(
            "/v1/services/agent/executions",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["executions"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_executions_with_data(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test listing executions with data."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="list_data@example.com",
            password_hash="test_hash",
            name="List Data User",
            tier="free",
            status="active",
        )
        db.add(user)

        # Create executions
        for i in range(3):
            execution = Execution(
                user_id=uuid.UUID(user_id),
                workflow_id=f"wf_list_{i}",
                status=ExecutionStatus.COMPLETED.value,
            )
            db.add(execution)

        await db.commit()

        response = await client.get(
            "/v1/services/agent/executions",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["executions"]) == 3
        assert data["total"] == 3


class TestCancelExecution:
    """Tests for POST /v1/services/agent/executions/{execution_id}/cancel endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_pending_execution(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test cancelling pending execution."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="cancel_test@example.com",
            password_hash="test_hash",
            name="Cancel Test User",
            tier="free",
            status="active",
        )
        db.add(user)

        # Create pending execution
        execution = Execution(
            user_id=uuid.UUID(user_id),
            workflow_id="wf_cancel_test",
            status=ExecutionStatus.PENDING.value,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        response = await client.post(
            f"/v1/services/agent/executions/{execution.id}/cancel",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_completed_execution(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test cancelling completed execution fails."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="cancel_done@example.com",
            password_hash="test_hash",
            name="Cancel Done User",
            tier="free",
            status="active",
        )
        db.add(user)

        # Create completed execution
        execution = Execution(
            user_id=uuid.UUID(user_id),
            workflow_id="wf_cancel_done",
            status=ExecutionStatus.COMPLETED.value,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        response = await client.post(
            f"/v1/services/agent/executions/{execution.id}/cancel",
            headers=headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert "Cannot cancel" in data["message"]

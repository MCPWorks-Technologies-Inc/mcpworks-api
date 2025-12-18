"""Integration tests for credit endpoints."""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.security import create_access_token
from mcpworks_api.models import Credit, CreditTransaction, User
from mcpworks_api.models.credit_transaction import TransactionType


@pytest.fixture
def auth_headers(test_settings):
    """Generate valid JWT auth headers for testing."""
    user_id = str(uuid.uuid4())
    access_token = create_access_token(
        user_id=user_id,
        scopes=["read", "write", "execute"],
    )

    return {"Authorization": f"Bearer {access_token}"}, user_id


class TestGetCreditBalance:
    """Tests for GET /v1/credits endpoint."""

    @pytest.mark.asyncio
    async def test_get_credit_balance_new_user(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test getting balance creates record for new user."""
        headers, user_id = auth_headers

        # Create user first
        user = User(
            id=uuid.UUID(user_id),
            email="credit_test@example.com",
            password_hash="test_hash",
            name="Credit Test User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.get("/v1/credits", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["available_credits"])) == Decimal("0.00")
        assert Decimal(str(data["held_credits"])) == Decimal("0.00")
        assert Decimal(str(data["lifetime_earned"])) == Decimal("0.00")
        assert Decimal(str(data["lifetime_spent"])) == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_get_credit_balance_existing_user(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test getting balance for user with credits."""
        headers, user_id = auth_headers

        # Create user and credit record
        user = User(
            id=uuid.UUID(user_id),
            email="credit_existing@example.com",
            password_hash="test_hash",
            name="Credit Test User",
            tier="free",
            status="active",
        )
        db.add(user)

        credit = Credit(
            user_id=uuid.UUID(user_id),
            available_balance=Decimal("150.00"),
            held_balance=Decimal("25.00"),
            lifetime_earned=Decimal("200.00"),
            lifetime_spent=Decimal("50.00"),
        )
        db.add(credit)
        await db.commit()

        response = await client.get("/v1/credits", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["available_credits"])) == Decimal("150.00")
        assert Decimal(str(data["held_credits"])) == Decimal("25.00")

    @pytest.mark.asyncio
    async def test_get_credit_balance_no_auth(self, client: AsyncClient):
        """Test getting balance requires authentication."""
        response = await client.get("/v1/credits")
        assert response.status_code == 401


class TestAddCredits:
    """Tests for POST /v1/credits/add endpoint."""

    @pytest.mark.asyncio
    async def test_add_credits_grant(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test adding credits via grant."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="add_credits@example.com",
            password_hash="test_hash",
            name="Add Credits User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.post(
            "/v1/credits/add",
            headers=headers,
            json={
                "amount": "100.00",
                "transaction_type": "grant",
                "metadata": {"reason": "welcome_bonus"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["amount"])) == Decimal("100.00")
        assert Decimal(str(data["available_balance"])) == Decimal("100.00")
        assert "transaction_id" in data

    @pytest.mark.asyncio
    async def test_add_credits_invalid_type(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test add_credits rejects invalid transaction type."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="add_invalid@example.com",
            password_hash="test_hash",
            name="Add Invalid User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.post(
            "/v1/credits/add",
            headers=headers,
            json={
                "amount": "100.00",
                "transaction_type": "hold",  # Invalid
            },
        )

        assert response.status_code == 422  # Validation error from regex pattern


class TestHoldCommitRelease:
    """Tests for hold/commit/release flow."""

    @pytest.mark.asyncio
    async def test_full_hold_commit_flow(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test complete hold -> commit flow."""
        headers, user_id = auth_headers

        # Create user with credits
        user = User(
            id=uuid.UUID(user_id),
            email="hold_commit@example.com",
            password_hash="test_hash",
            name="Hold Commit User",
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
        await db.commit()

        # Step 1: Create hold
        hold_response = await client.post(
            "/v1/credits/hold",
            headers=headers,
            json={
                "amount": "30.00",
                "metadata": {"operation": "test_execution"},
            },
        )

        assert hold_response.status_code == 200
        hold_data = hold_response.json()
        assert Decimal(str(hold_data["amount"])) == Decimal("30.00")
        assert Decimal(str(hold_data["available_balance"])) == Decimal("70.00")
        hold_id = hold_data["hold_id"]

        # Step 2: Commit the hold
        commit_response = await client.post(
            f"/v1/credits/hold/{hold_id}/commit",
            headers=headers,
            json={
                "amount": "25.00",  # Partial commit
                "metadata": {"actual_cost": "25.00"},
            },
        )

        assert commit_response.status_code == 200
        commit_data = commit_response.json()
        assert Decimal(str(commit_data["committed_amount"])) == Decimal("25.00")
        assert Decimal(str(commit_data["released_amount"])) == Decimal("5.00")
        assert Decimal(str(commit_data["available_balance"])) == Decimal("75.00")  # 70 + 5 excess

    @pytest.mark.asyncio
    async def test_full_hold_release_flow(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test complete hold -> release flow (operation cancelled)."""
        headers, user_id = auth_headers

        # Create user with credits
        user = User(
            id=uuid.UUID(user_id),
            email="hold_release@example.com",
            password_hash="test_hash",
            name="Hold Release User",
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
        await db.commit()

        # Step 1: Create hold
        hold_response = await client.post(
            "/v1/credits/hold",
            headers=headers,
            json={"amount": "50.00"},
        )

        assert hold_response.status_code == 200
        hold_data = hold_response.json()
        hold_id = hold_data["hold_id"]

        # Step 2: Release the hold (operation cancelled)
        release_response = await client.post(
            f"/v1/credits/hold/{hold_id}/release",
            headers=headers,
            json={"metadata": {"reason": "operation_cancelled"}},
        )

        assert release_response.status_code == 200
        release_data = release_response.json()
        assert Decimal(str(release_data["released_amount"])) == Decimal("50.00")
        assert Decimal(str(release_data["available_balance"])) == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_hold_insufficient_credits(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test hold fails when insufficient credits."""
        headers, user_id = auth_headers

        # Create user with limited credits
        user = User(
            id=uuid.UUID(user_id),
            email="hold_insufficient@example.com",
            password_hash="test_hash",
            name="Insufficient Credits User",
            tier="free",
            status="active",
        )
        db.add(user)

        credit = Credit(
            user_id=uuid.UUID(user_id),
            available_balance=Decimal("20.00"),
            held_balance=Decimal("0.00"),
            lifetime_earned=Decimal("20.00"),
            lifetime_spent=Decimal("0.00"),
        )
        db.add(credit)
        await db.commit()

        response = await client.post(
            "/v1/credits/hold",
            headers=headers,
            json={"amount": "50.00"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "INSUFFICIENT_CREDITS"
        assert data["details"]["required"] == 50.0
        assert data["details"]["available"] == 20.0

    @pytest.mark.asyncio
    async def test_commit_invalid_hold_id(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test commit fails for non-existent hold."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="commit_invalid@example.com",
            password_hash="test_hash",
            name="Invalid Commit User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        fake_hold_id = uuid.uuid4()
        response = await client.post(
            f"/v1/credits/hold/{fake_hold_id}/commit",
            headers=headers,
            json={},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "INVALID_HOLD"

    @pytest.mark.asyncio
    async def test_double_commit_rejected(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test commit fails for already committed hold."""
        headers, user_id = auth_headers

        # Create user with credits
        user = User(
            id=uuid.UUID(user_id),
            email="double_commit@example.com",
            password_hash="test_hash",
            name="Double Commit User",
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
        await db.commit()

        # Create and commit hold
        hold_response = await client.post(
            "/v1/credits/hold",
            headers=headers,
            json={"amount": "30.00"},
        )
        hold_id = hold_response.json()["hold_id"]

        # First commit succeeds
        first_commit = await client.post(
            f"/v1/credits/hold/{hold_id}/commit",
            headers=headers,
            json={},
        )
        assert first_commit.status_code == 200

        # Second commit should fail
        second_commit = await client.post(
            f"/v1/credits/hold/{hold_id}/commit",
            headers=headers,
            json={},
        )
        assert second_commit.status_code == 400
        assert second_commit.json()["error"] == "INVALID_HOLD"


class TestGetTransactions:
    """Tests for GET /v1/credits/transactions endpoint."""

    @pytest.mark.asyncio
    async def test_get_transactions_empty(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test getting transactions for user with no history."""
        headers, user_id = auth_headers

        # Create user
        user = User(
            id=uuid.UUID(user_id),
            email="txn_empty@example.com",
            password_hash="test_hash",
            name="Empty Transactions User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.get("/v1/credits/transactions", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["transactions"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_get_transactions_with_history(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test getting transactions with history."""
        headers, user_id = auth_headers

        # Create user with credits
        user = User(
            id=uuid.UUID(user_id),
            email="txn_history@example.com",
            password_hash="test_hash",
            name="Transaction History User",
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
        await db.commit()

        # Add some credits to generate transaction
        await client.post(
            "/v1/credits/add",
            headers=headers,
            json={"amount": "50.00", "transaction_type": "grant"},
        )

        # Get transactions
        response = await client.get("/v1/credits/transactions", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["transactions"]) >= 1
        # Most recent transaction should be the grant
        assert data["transactions"][0]["type"] == "grant"

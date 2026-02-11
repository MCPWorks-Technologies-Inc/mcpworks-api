"""Integration tests for subscription endpoints."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.security import create_access_token
from mcpworks_api.models import Subscription, SubscriptionStatus, User


@pytest.fixture
def auth_headers(test_settings):
    """Generate valid JWT auth headers for testing."""
    user_id = str(uuid.uuid4())
    access_token = create_access_token(
        user_id=user_id,
        scopes=["read", "write"],
    )
    return {"Authorization": f"Bearer {access_token}"}, user_id


class TestCreateSubscription:
    """Tests for POST /v1/subscriptions endpoint."""

    @pytest.mark.asyncio
    async def test_create_subscription_invalid_tier(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test that invalid tier is rejected."""
        headers, user_id = auth_headers

        # Create user with unique email
        user = User(
            id=uuid.UUID(user_id),
            email=f"sub_invalid_{user_id}@example.com",
            password_hash="test_hash",
            name="Sub Test User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.post(
            "/v1/subscriptions",
            headers=headers,
            json={
                "tier": "invalid",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_subscription_no_auth(self, client: AsyncClient):
        """Test that subscription creation requires authentication."""
        response = await client.post(
            "/v1/subscriptions",
            json={
                "tier": "founder",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_subscription_price_not_configured(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test error when Stripe price not configured."""
        headers, user_id = auth_headers

        # Create user with unique email
        user = User(
            id=uuid.UUID(user_id),
            email=f"sub_noconfig_{user_id}@example.com",
            password_hash="test_hash",
            name="Sub Test User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.post(
            "/v1/subscriptions",
            headers=headers,
            json={
                "tier": "founder",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )

        # Should fail because Stripe prices are placeholders
        assert response.status_code == 400
        data = response.json()
        assert (
            "not configured" in data["message"].lower() or "placeholder" in data["message"].lower()
        )


class TestGetCurrentSubscription:
    """Tests for GET /v1/subscriptions/current endpoint."""

    @pytest.mark.asyncio
    async def test_get_subscription_not_found(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test getting subscription when none exists."""
        headers, user_id = auth_headers

        # Create user without subscription (unique email)
        user = User(
            id=uuid.UUID(user_id),
            email=f"sub_notfound_{user_id}@example.com",
            password_hash="test_hash",
            name="Sub Test User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.get(
            "/v1/subscriptions/current",
            headers=headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_subscription_success(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test getting existing subscription."""
        headers, user_id = auth_headers

        # Create user with unique email
        user = User(
            id=uuid.UUID(user_id),
            email=f"sub_found_{user_id}@example.com",
            password_hash="test_hash",
            name="Sub Test User",
            tier="founder",
            status="active",
        )
        db.add(user)

        # Create subscription
        now = datetime.now(UTC)
        subscription = Subscription(
            user_id=uuid.UUID(user_id),
            tier="founder",
            status=SubscriptionStatus.ACTIVE.value,
            stripe_subscription_id="sub_test123",
            stripe_customer_id="cus_test123",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(subscription)
        await db.commit()

        response = await client.get(
            "/v1/subscriptions/current",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "founder"
        assert data["status"] == "active"
        assert data["cancel_at_period_end"] is False
        assert data["monthly_credits"] == 2900

    @pytest.mark.asyncio
    async def test_get_subscription_no_auth(self, client: AsyncClient):
        """Test that getting subscription requires authentication."""
        response = await client.get("/v1/subscriptions/current")
        assert response.status_code == 401


class TestCancelSubscription:
    """Tests for DELETE /v1/subscriptions/current endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_no_subscription(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test cancelling when no subscription exists."""
        headers, user_id = auth_headers

        # Create user without subscription (unique email)
        user = User(
            id=uuid.UUID(user_id),
            email=f"cancel_nosub_{user_id}@example.com",
            password_hash="test_hash",
            name="Cancel Test User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.delete(
            "/v1/subscriptions/current",
            headers=headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test cancelling already cancelled subscription."""
        headers, user_id = auth_headers

        # Create user with unique email
        user = User(
            id=uuid.UUID(user_id),
            email=f"cancel_done_{user_id}@example.com",
            password_hash="test_hash",
            name="Cancel Test User",
            tier="founder",
            status="active",
        )
        db.add(user)

        # Create cancelled subscription
        now = datetime.now(UTC)
        subscription = Subscription(
            user_id=uuid.UUID(user_id),
            tier="founder",
            status=SubscriptionStatus.CANCELLED.value,
            stripe_subscription_id="sub_cancelled",
            stripe_customer_id="cus_test123",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(subscription)
        await db.commit()

        response = await client.delete(
            "/v1/subscriptions/current",
            headers=headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert "cancelled" in data["message"].lower()


class TestPurchaseCredits:
    """Tests for POST /v1/subscriptions/credits endpoint."""

    @pytest.mark.asyncio
    async def test_purchase_credits_minimum(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test that minimum credit purchase is enforced."""
        headers, user_id = auth_headers

        # Create user with unique email
        user = User(
            id=uuid.UUID(user_id),
            email=f"purchase_min_{user_id}@example.com",
            password_hash="test_hash",
            name="Purchase Test User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        response = await client.post(
            "/v1/subscriptions/credits",
            headers=headers,
            json={
                "credits": 50,  # Below minimum of 100
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_purchase_credits_no_auth(self, client: AsyncClient):
        """Test that credit purchase requires authentication."""
        response = await client.post(
            "/v1/subscriptions/credits",
            json={
                "credits": 1000,
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )

        assert response.status_code == 401


class TestStripeWebhook:
    """Tests for POST /v1/webhooks/stripe endpoint."""

    @pytest.mark.asyncio
    async def test_webhook_missing_signature(self, client: AsyncClient):
        """Test that missing signature is rejected."""
        response = await client.post(
            "/v1/webhooks/stripe",
            content=b'{"type": "test"}',
        )

        assert response.status_code == 422  # Missing header

    @pytest.mark.asyncio
    async def test_webhook_invalid_signature(self, client: AsyncClient):
        """Test that invalid signature is rejected."""
        response = await client.post(
            "/v1/webhooks/stripe",
            content=b'{"type": "test"}',
            headers={"Stripe-Signature": "invalid_signature"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "signature" in data["message"].lower() or "INVALID" in data.get("error", "")

    @pytest.mark.asyncio
    async def test_webhook_valid_unhandled_event(
        self,
        client: AsyncClient,
        db: AsyncSession,  # noqa: ARG002
    ):
        """Test that unhandled event types are acknowledged."""
        with patch("stripe.Webhook.construct_event") as mock_construct:
            mock_construct.return_value = {
                "id": "evt_test_unknown_123",
                "type": "unknown.event",
                "data": {"object": {}},
            }

            response = await client.post(
                "/v1/webhooks/stripe",
                content=b'{"type": "unknown.event"}',
                headers={"Stripe-Signature": "valid_sig_mock"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["processed"] is False
            assert data["event_type"] == "unknown.event"

    @pytest.mark.asyncio
    async def test_webhook_subscription_created(self, client: AsyncClient, db: AsyncSession):
        """Test handling checkout.session.completed webhook."""
        user_id = uuid.uuid4()

        # Create user with unique email
        user = User(
            id=user_id,
            email=f"webhook_test_{user_id}@example.com",
            password_hash="test_hash",
            name="Webhook Test User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        # Mock Stripe responses
        with (
            patch("stripe.Webhook.construct_event") as mock_construct,
            patch("stripe.Subscription.retrieve") as mock_retrieve,
        ):
            now = datetime.now(UTC)
            mock_construct.return_value = {
                "id": "evt_test_checkout_sub_123",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "metadata": {
                            "user_id": str(user_id),
                            "tier": "founder",
                        },
                        "subscription": "sub_new123",
                        "customer": "cus_new123",
                    }
                },
            }

            mock_stripe_sub = MagicMock()
            mock_stripe_sub.current_period_start = int(now.timestamp())
            mock_stripe_sub.current_period_end = int((now + timedelta(days=30)).timestamp())
            mock_retrieve.return_value = mock_stripe_sub

            response = await client.post(
                "/v1/webhooks/stripe",
                content=b'{"type": "checkout.session.completed"}',
                headers={"Stripe-Signature": "valid_sig_mock"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["processed"] is True
            assert data["event_type"] == "checkout.session.completed"

    @pytest.mark.asyncio
    async def test_webhook_credit_purchase(self, client: AsyncClient, db: AsyncSession):
        """Test handling checkout.session.completed for credit purchase."""
        user_id = uuid.uuid4()

        # Create user with unique email
        user = User(
            id=user_id,
            email=f"credit_purchase_{user_id}@example.com",
            password_hash="test_hash",
            name="Credit Purchase User",
            tier="free",
            status="active",
        )
        db.add(user)
        await db.commit()

        # Mock Stripe response for credit purchase
        with patch("stripe.Webhook.construct_event") as mock_construct:
            mock_construct.return_value = {
                "id": "evt_test_credit_purchase_123",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_test_credit_purchase",
                        "metadata": {
                            "user_id": str(user_id),
                            "credits": "500",
                            "type": "credit_purchase",
                        },
                        # No subscription field for payment mode
                        "customer": "cus_credit123",
                    }
                },
            }

            response = await client.post(
                "/v1/webhooks/stripe",
                content=b'{"type": "checkout.session.completed"}',
                headers={"Stripe-Signature": "valid_sig_mock"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["processed"] is True
            assert data["event_type"] == "checkout.session.completed"

        # Verify credits were added
        from mcpworks_api.models import Credit

        result = await db.execute(select(Credit).where(Credit.user_id == user_id))
        credit = result.scalar_one_or_none()
        assert credit is not None
        assert credit.available_balance == Decimal("500.00")

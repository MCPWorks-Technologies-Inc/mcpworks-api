"""Unit tests for StripeService."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcpworks_api.models import Subscription, SubscriptionStatus
from mcpworks_api.services.stripe import TIER_CREDITS, StripeService


class TestTierCredits:
    """Tests for tier credit configuration."""

    def test_free_tier_credits(self):
        """Test free tier has 500 credits."""
        assert TIER_CREDITS["free"] == 500

    def test_starter_tier_credits(self):
        """Test starter tier has 2900 credits."""
        assert TIER_CREDITS["starter"] == 2900

    def test_pro_tier_credits(self):
        """Test pro tier has 9900 credits."""
        assert TIER_CREDITS["pro"] == 9900

    def test_enterprise_tier_credits(self):
        """Test enterprise tier has custom credits."""
        assert TIER_CREDITS["enterprise"] == 99999


class TestCreateCheckoutSession:
    """Tests for create_checkout_session method."""

    @pytest.mark.asyncio
    async def test_invalid_tier_rejected(self):
        """Test that invalid tier is rejected."""
        mock_db = AsyncMock()

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db
            service.settings = MagicMock()

            with pytest.raises(ValueError, match="Invalid tier"):
                await service.create_checkout_session(
                    user_id=uuid.uuid4(),
                    tier="invalid",
                    success_url="https://example.com/success",
                    cancel_url="https://example.com/cancel",
                )

    @pytest.mark.asyncio
    async def test_user_not_found_rejected(self):
        """Test that missing user is rejected."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db
            service.settings = MagicMock()

            # Mock get_tier_price_map to return valid price ID so we can test user lookup
            with patch("mcpworks_api.services.stripe.get_tier_price_map") as mock_price_map:
                mock_price_map.return_value = {"starter": "price_valid123"}

                with pytest.raises(ValueError, match="not found"):
                    await service.create_checkout_session(
                        user_id=uuid.uuid4(),
                        tier="starter",
                        success_url="https://example.com/success",
                        cancel_url="https://example.com/cancel",
                    )


class TestGetSubscription:
    """Tests for get_subscription method."""

    @pytest.mark.asyncio
    async def test_get_existing_subscription(self):
        """Test getting an existing subscription."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()

        mock_subscription = MagicMock(spec=Subscription)
        mock_subscription.user_id = user_id
        mock_subscription.tier = "starter"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_subscription
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db
            service.settings = MagicMock()

            result = await service.get_subscription(user_id)

            assert result is not None
            assert result.tier == "starter"

    @pytest.mark.asyncio
    async def test_get_nonexistent_subscription(self):
        """Test getting a nonexistent subscription returns None."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db
            service.settings = MagicMock()

            result = await service.get_subscription(uuid.uuid4())

            assert result is None


class TestCancelSubscription:
    """Tests for cancel_subscription method."""

    @pytest.mark.asyncio
    async def test_cancel_no_subscription(self):
        """Test cancelling when no subscription exists."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db
            service.settings = MagicMock()

            with pytest.raises(ValueError, match="No subscription found"):
                await service.cancel_subscription(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancel_no_stripe_subscription(self):
        """Test cancelling when no Stripe subscription linked."""
        mock_db = AsyncMock()

        mock_subscription = MagicMock(spec=Subscription)
        mock_subscription.stripe_subscription_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_subscription
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db
            service.settings = MagicMock()

            with pytest.raises(ValueError, match="No Stripe subscription"):
                await service.cancel_subscription(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled(self):
        """Test cancelling already cancelled subscription."""
        mock_db = AsyncMock()

        mock_subscription = MagicMock(spec=Subscription)
        mock_subscription.stripe_subscription_id = "sub_123"
        mock_subscription.status = SubscriptionStatus.CANCELLED.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_subscription
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db
            service.settings = MagicMock()

            with pytest.raises(ValueError, match="already cancelled"):
                await service.cancel_subscription(uuid.uuid4())


class TestHandleWebhookEvent:
    """Tests for handle_webhook_event method."""

    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self):
        """Test that invalid signature is rejected."""
        import stripe

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = AsyncMock()
            service.settings = MagicMock()
            service.settings.stripe_webhook_secret = "whsec_test"

            with patch("stripe.Webhook.construct_event") as mock_construct:
                mock_construct.side_effect = stripe.error.SignatureVerificationError(
                    "Invalid signature", "sig_header"
                )

                with pytest.raises(ValueError, match="Invalid webhook signature"):
                    await service.handle_webhook_event(b"payload", "invalid_sig")

    @pytest.mark.asyncio
    async def test_unhandled_event_type(self):
        """Test that unhandled event types are acknowledged."""
        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = AsyncMock()
            service.settings = MagicMock()
            service.settings.stripe_webhook_secret = "whsec_test"

            with patch("stripe.Webhook.construct_event") as mock_construct:
                mock_construct.return_value = {
                    "type": "unknown.event.type",
                    "data": {"object": {}},
                }

                result = await service.handle_webhook_event(b"payload", "valid_sig")

                assert result["processed"] is False
                assert result["event_type"] == "unknown.event.type"


class TestGrantMonthlyCredits:
    """Tests for _grant_monthly_credits method."""

    @pytest.mark.asyncio
    async def test_grants_correct_credits(self):
        """Test that correct credit amounts are granted."""
        mock_db = AsyncMock()

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db
            service.settings = MagicMock()

            with patch("mcpworks_api.services.stripe.CreditService") as mock_credit_service:
                mock_instance = MagicMock()
                mock_instance.add_credits = AsyncMock()
                mock_credit_service.return_value = mock_instance

                user_id = uuid.uuid4()
                await service._grant_monthly_credits(user_id, "starter")

                mock_instance.add_credits.assert_called_once()
                call_args = mock_instance.add_credits.call_args
                assert call_args.kwargs["amount"] == Decimal("2900")
                # Uses TransactionType.GRANT enum
                assert str(call_args.kwargs["transaction_type"]) == "TransactionType.GRANT"

    @pytest.mark.asyncio
    async def test_no_credits_for_unknown_tier(self):
        """Test that unknown tier grants no credits."""
        mock_db = AsyncMock()

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db
            service.settings = MagicMock()

            with patch("mcpworks_api.services.stripe.CreditService") as mock_credit_service:
                mock_instance = MagicMock()
                mock_instance.add_credits = AsyncMock()
                mock_credit_service.return_value = mock_instance

                await service._grant_monthly_credits(uuid.uuid4(), "unknown")

                # Should not call add_credits for unknown tier
                mock_instance.add_credits.assert_not_called()


class TestSubscriptionStatus:
    """Tests for SubscriptionStatus enum."""

    def test_subscription_status_values(self):
        """Test all subscription status values exist."""
        assert SubscriptionStatus.ACTIVE.value == "active"
        assert SubscriptionStatus.CANCELLED.value == "cancelled"
        assert SubscriptionStatus.PAST_DUE.value == "past_due"
        assert SubscriptionStatus.TRIALING.value == "trialing"

"""Unit tests for StripeService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcpworks_api.models import Subscription, SubscriptionStatus
from mcpworks_api.services.stripe import TIER_EXECUTIONS, StripeService


class TestTierExecutions:
    """Tests for tier execution limit configuration per PRICING.md."""

    def test_free_tier_executions(self):
        """Test free tier has 100 executions/month."""
        assert TIER_EXECUTIONS["free"] == 100

    def test_builder_tier_executions(self):
        """Test builder tier has 2,500 executions/month."""
        assert TIER_EXECUTIONS["builder"] == 2_500

    def test_pro_tier_executions(self):
        """Test pro tier has 15,000 executions/month."""
        assert TIER_EXECUTIONS["pro"] == 15_000

    def test_enterprise_tier_executions(self):
        """Test enterprise tier has 100,000 executions/month."""
        assert TIER_EXECUTIONS["enterprise"] == 100_000


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
                    interval="monthly",
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

            with patch("mcpworks_api.services.stripe.get_tier_price_map") as mock_price_map:
                mock_price_map.return_value = {
                    "builder": {"monthly": "price_valid123", "annual": "price_valid456"},
                }

                with pytest.raises(ValueError, match="not found"):
                    await service.create_checkout_session(
                        user_id=uuid.uuid4(),
                        tier="builder",
                        interval="monthly",
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
        mock_subscription.tier = "builder"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_subscription
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db
            service.settings = MagicMock()

            result = await service.get_subscription(user_id)

            assert result is not None
            assert result.tier == "builder"

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
            service.redis = None  # No Redis for unit test
            service.settings = MagicMock()
            service.settings.stripe_webhook_secret = "whsec_test"

            with patch("stripe.Webhook.construct_event") as mock_construct:
                mock_construct.return_value = {
                    "id": "evt_test_unhandled_123",
                    "type": "unknown.event.type",
                    "data": {"object": {}},
                }

                result = await service.handle_webhook_event(b"payload", "valid_sig")

                assert result["processed"] is False
                assert result["event_type"] == "unknown.event.type"


class TestSubscriptionStatus:
    """Tests for SubscriptionStatus enum."""

    def test_subscription_status_values(self):
        """Test all subscription status values exist."""
        assert SubscriptionStatus.ACTIVE.value == "active"
        assert SubscriptionStatus.CANCELLED.value == "cancelled"
        assert SubscriptionStatus.PAST_DUE.value == "past_due"
        assert SubscriptionStatus.TRIALING.value == "trialing"


class TestTryClaimEvent:
    """Tests for _try_claim_event method."""

    @pytest.mark.asyncio
    async def test_claim_event_without_redis(self):
        """Test claiming event without Redis always succeeds."""
        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.redis = None  # No Redis

            result = await service._try_claim_event("evt_test123")

            assert result is True

    @pytest.mark.asyncio
    async def test_claim_event_with_redis_success(self):
        """Test successfully claiming an event with Redis."""
        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.redis = AsyncMock()
            service.redis.set = AsyncMock(return_value=True)  # SETNX success

            result = await service._try_claim_event("evt_test123")

            assert result is True
            service.redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_claim_event_already_claimed(self):
        """Test claiming already claimed event returns False."""
        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.redis = AsyncMock()
            service.redis.set = AsyncMock(return_value=None)  # Already exists

            result = await service._try_claim_event("evt_test123")

            assert result is False

    @pytest.mark.asyncio
    async def test_claim_event_redis_error_allows_processing(self):
        """Test Redis error allows processing (fail-open)."""
        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.redis = AsyncMock()
            service.redis.set = AsyncMock(side_effect=Exception("Redis error"))

            result = await service._try_claim_event("evt_test123")

            assert result is True  # Fail-open


class TestMarkEventCompleted:
    """Tests for _mark_event_completed method."""

    @pytest.mark.asyncio
    async def test_mark_completed_without_redis(self):
        """Test marking completed without Redis does nothing."""
        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.redis = None

            # Should not raise
            await service._mark_event_completed("evt_test123")

    @pytest.mark.asyncio
    async def test_mark_completed_with_redis(self):
        """Test marking event as completed."""
        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.redis = AsyncMock()

            await service._mark_event_completed("evt_test123")

            service.redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_completed_redis_error_suppressed(self):
        """Test Redis error is suppressed."""
        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.redis = AsyncMock()
            service.redis.set = AsyncMock(side_effect=Exception("Redis error"))

            # Should not raise
            await service._mark_event_completed("evt_test123")


class TestReleaseEventClaim:
    """Tests for _release_event_claim method."""

    @pytest.mark.asyncio
    async def test_release_without_redis(self):
        """Test releasing without Redis does nothing."""
        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.redis = None

            # Should not raise
            await service._release_event_claim("evt_test123")

    @pytest.mark.asyncio
    async def test_release_with_redis(self):
        """Test releasing event claim."""
        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.redis = AsyncMock()

            await service._release_event_claim("evt_test123")

            service.redis.delete.assert_called_once()


class TestHandleSubscriptionUpdated:
    """Tests for _handle_subscription_updated method."""

    @pytest.mark.asyncio
    async def test_subscription_not_found(self):
        """Test handler ignores unknown subscriptions."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db

            # Should not raise
            await service._handle_subscription_updated(
                {
                    "id": "sub_unknown",
                    "status": "active",
                    "current_period_start": 1704067200,
                    "current_period_end": 1706745600,
                }
            )

    @pytest.mark.asyncio
    async def test_status_mapping_active(self):
        """Test active status is mapped correctly."""
        mock_db = AsyncMock()
        mock_subscription = MagicMock(spec=Subscription)
        mock_subscription.status = "trialing"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_subscription
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db

            await service._handle_subscription_updated(
                {
                    "id": "sub_123",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_start": 1704067200,
                    "current_period_end": 1706745600,
                }
            )

            assert mock_subscription.status == SubscriptionStatus.ACTIVE.value


class TestHandleSubscriptionDeleted:
    """Tests for _handle_subscription_deleted method."""

    @pytest.mark.asyncio
    async def test_subscription_not_found(self):
        """Test handler ignores unknown subscriptions."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db

            # Should not raise
            await service._handle_subscription_deleted({"id": "sub_unknown"})

    @pytest.mark.asyncio
    async def test_marks_cancelled_and_downgrades(self):
        """Test subscription is cancelled and user downgraded."""
        mock_db = AsyncMock()
        mock_subscription = MagicMock(spec=Subscription)
        mock_subscription.user_id = uuid.uuid4()
        mock_subscription.status = SubscriptionStatus.ACTIVE.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_subscription
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db

            await service._handle_subscription_deleted({"id": "sub_123"})

            assert mock_subscription.status == SubscriptionStatus.CANCELLED.value
            mock_db.commit.assert_called()


class TestHandlePaymentSucceeded:
    """Tests for _handle_payment_succeeded method.

    NOTE: As of PRICING.md update, billing is execution-based with Redis
    tracking. This handler is now a no-op since usage limits reset
    automatically via Redis key expiry.
    """

    @pytest.mark.asyncio
    async def test_payment_succeeded_is_noop(self):
        """Test handler is a no-op (usage tracking via Redis)."""
        mock_db = AsyncMock()

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db

            # Should not raise - method is a no-op
            await service._handle_payment_succeeded(
                {
                    "subscription": "sub_123",
                    "billing_reason": "subscription_cycle",
                }
            )


class TestHandlePaymentFailed:
    """Tests for _handle_payment_failed method."""

    @pytest.mark.asyncio
    async def test_no_subscription_id(self):
        """Test handler ignores events without subscription."""
        mock_db = AsyncMock()

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db

            # Should not raise
            await service._handle_payment_failed({"subscription": None})

    @pytest.mark.asyncio
    async def test_subscription_not_found(self):
        """Test handler ignores unknown subscriptions."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db

            # Should not raise
            await service._handle_payment_failed({"subscription": "sub_unknown"})

    @pytest.mark.asyncio
    async def test_marks_past_due(self):
        """Test subscription is marked past due."""
        mock_db = AsyncMock()
        mock_subscription = MagicMock(spec=Subscription)
        mock_subscription.status = SubscriptionStatus.ACTIVE.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_subscription
        mock_db.execute.return_value = mock_result

        with patch.object(StripeService, "__init__", return_value=None):
            service = StripeService.__new__(StripeService)
            service.db = mock_db

            await service._handle_payment_failed({"subscription": "sub_123"})

            assert mock_subscription.status == SubscriptionStatus.PAST_DUE.value

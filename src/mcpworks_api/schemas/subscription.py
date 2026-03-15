"""Pydantic schemas for subscription endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateSubscriptionRequest(BaseModel):
    """Request body for POST /v1/subscriptions."""

    tier: str = Field(
        ...,
        description="Target subscription tier",
        pattern="^(pro|enterprise|dedicated|trial-agent|pro-agent|enterprise-agent|dedicated-agent)$",
    )
    interval: str = Field(
        default="monthly",
        description="Billing interval: monthly or annual",
        pattern="^(monthly|annual)$",
    )
    success_url: str = Field(
        ...,
        description="URL to redirect after successful checkout",
    )
    cancel_url: str = Field(
        ...,
        description="URL to redirect if checkout is cancelled",
    )


class CheckoutSessionResponse(BaseModel):
    """Response for checkout session creation."""

    checkout_url: str = Field(
        ...,
        description="Stripe Checkout URL to redirect user to",
    )
    session_id: str = Field(
        ...,
        description="Stripe Checkout session ID",
    )


class SubscriptionInfo(BaseModel):
    """Subscription details."""

    tier: str = Field(
        ...,
        description="Current subscription tier",
    )
    status: str = Field(
        ...,
        description="Subscription status: active, cancelled, past_due, trialing",
    )
    current_period_start: datetime = Field(
        ...,
        description="Start of current billing period",
    )
    current_period_end: datetime = Field(
        ...,
        description="End of current billing period",
    )
    cancel_at_period_end: bool = Field(
        ...,
        description="Whether subscription will cancel at period end",
    )
    interval: str | None = Field(
        default=None,
        description="Billing interval: monthly or annual",
    )
    monthly_executions: int = Field(
        ...,
        description="Monthly execution limit for this tier",
    )

    model_config = ConfigDict(from_attributes=True)


class PortalSessionResponse(BaseModel):
    """Response for customer portal session creation."""

    portal_url: str = Field(
        ...,
        description="Stripe Customer Portal URL to redirect user to",
    )


class CancelSubscriptionResponse(BaseModel):
    """Response for subscription cancellation."""

    status: str = Field(
        ...,
        description="Cancellation status",
    )
    cancel_at: str = Field(
        ...,
        description="ISO timestamp when subscription will end",
    )
    message: str = Field(
        ...,
        description="Status message",
    )


class WebhookResponse(BaseModel):
    """Response for webhook processing."""

    processed: bool = Field(
        ...,
        description="Whether event was processed",
    )
    event_type: str = Field(
        ...,
        description="Type of Stripe event",
    )
    message: str | None = Field(
        default=None,
        description="Optional status message",
    )

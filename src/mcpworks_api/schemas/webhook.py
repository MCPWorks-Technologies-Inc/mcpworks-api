"""Pydantic schemas for Webhook model."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WebhookBase(BaseModel):
    """Base webhook fields."""

    url: str = Field(
        ...,
        description="Webhook delivery URL (HTTPS required)",
        examples=["https://api.example.com/webhooks/mcpworks"],
    )

    events: list[str] = Field(
        ...,
        min_length=1,
        description="Event types to subscribe to",
        examples=[["function.execution.completed", "function.execution.failed"]],
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate webhook URL is HTTPS."""
        if not v.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS")
        return v


class WebhookCreate(WebhookBase):
    """Schema for creating a webhook."""

    secret: str = Field(
        ...,
        min_length=32,
        description="Webhook secret for signature verification (will be hashed)",
    )


class WebhookUpdate(BaseModel):
    """Schema for updating a webhook."""

    url: str | None = None
    events: list[str] | None = None
    enabled: bool | None = None
    secret: str | None = Field(
        None,
        min_length=32,
        description="New webhook secret (will be hashed)",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        """Validate webhook URL is HTTPS if provided."""
        if v is not None and not v.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS")
        return v


class WebhookResponse(BaseModel):
    """Schema for webhook responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    url: str
    events: list[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime | None = None


class WebhookList(BaseModel):
    """Schema for webhook list."""

    webhooks: list[WebhookResponse]
    total: int

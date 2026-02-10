"""Pydantic schemas for Webhook model."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WebhookBase(BaseModel):
    """Base webhook fields."""

    url: str = Field(
        ...,
        description="Webhook delivery URL (HTTPS required)",
        examples=["https://api.example.com/webhooks/mcpworks"],
    )

    events: List[str] = Field(
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

    url: Optional[str] = None
    events: Optional[List[str]] = None
    enabled: Optional[bool] = None
    secret: Optional[str] = Field(
        None,
        min_length=32,
        description="New webhook secret (will be hashed)",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
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
    events: List[str]
    enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class WebhookList(BaseModel):
    """Schema for webhook list."""

    webhooks: List[WebhookResponse]
    total: int

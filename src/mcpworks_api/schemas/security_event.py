"""Pydantic schemas for SecurityEvent model."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SecurityEventResponse(BaseModel):
    """Schema for security event responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    timestamp: datetime
    event_type: str
    actor_ip: str | None = None
    actor_id: str | None = None
    details: dict[str, Any] | None = None
    severity: str


class SecurityEventList(BaseModel):
    """Schema for security event list."""

    events: list[SecurityEventResponse]
    total: int
    page: int = 1
    page_size: int = 50
    has_more: bool

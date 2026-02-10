"""Pydantic schemas for SecurityEvent model."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SecurityEventResponse(BaseModel):
    """Schema for security event responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    timestamp: datetime
    event_type: str
    actor_ip: Optional[str] = None
    actor_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    severity: str


class SecurityEventList(BaseModel):
    """Schema for security event list."""

    events: List[SecurityEventResponse]
    total: int
    page: int = 1
    page_size: int = 50
    has_more: bool

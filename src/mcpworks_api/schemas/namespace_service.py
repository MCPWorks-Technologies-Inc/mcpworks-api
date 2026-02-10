"""Pydantic schemas for NamespaceService model."""

import re
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NamespaceServiceBase(BaseModel):
    """Base service fields."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=63,
        description="Service name (URL-safe)",
        examples=["auth", "payment-processing", "data_sync"],
    )

    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Human-readable description",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate service name is URL-safe."""
        if not re.match(r"^[a-z0-9]([a-z0-9-_]{0,61}[a-z0-9])?$", v):
            raise ValueError(
                "Service name must be lowercase alphanumeric with hyphens/underscores"
            )
        return v.lower()


class NamespaceServiceCreate(NamespaceServiceBase):
    """Schema for creating a service."""

    pass


class NamespaceServiceUpdate(BaseModel):
    """Schema for updating a service."""

    description: Optional[str] = Field(None, max_length=1000)


class NamespaceServiceResponse(NamespaceServiceBase):
    """Schema for service responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    namespace_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    function_count: int = Field(
        default=0,
        description="Number of functions in this service",
    )


class NamespaceServiceList(BaseModel):
    """Schema for service list."""

    services: List[NamespaceServiceResponse]
    total: int

"""Pydantic schemas for Namespace model."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NamespaceBase(BaseModel):
    """Base namespace fields."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=63,
        description="Namespace name (DNS-compliant)",
        examples=["acme", "my-company", "prod-env"],
    )

    description: str | None = Field(
        None,
        max_length=1000,
        description="Human-readable description",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate namespace name follows DNS rules."""
        if not re.match(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", v):
            raise ValueError(
                "Namespace name must be lowercase alphanumeric with hyphens, "
                "starting and ending with alphanumeric character"
            )
        return v.lower()


class NamespaceCreate(NamespaceBase):
    """Schema for creating a namespace."""

    network_whitelist: list[str] | None = Field(
        None,
        description="Optional IP whitelist (CIDR format)",
        examples=[["192.168.1.0/24", "10.0.0.1"]],
    )


class NamespaceUpdate(BaseModel):
    """Schema for updating a namespace."""

    description: str | None = Field(None, max_length=1000)
    network_whitelist: list[str] | None = None


class NamespaceResponse(NamespaceBase):
    """Schema for namespace responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    network_whitelist: list[str] | None = None
    whitelist_updated_at: datetime | None = None
    whitelist_changes_today: int
    created_at: datetime
    updated_at: datetime | None = None
    create_endpoint: str = Field(
        ...,
        description="Management endpoint URL",
    )
    run_endpoint: str = Field(
        ...,
        description="Execution endpoint URL",
    )


class NamespaceList(BaseModel):
    """Schema for paginated namespace list."""

    namespaces: list[NamespaceResponse]
    total: int
    page: int = 1
    page_size: int = 50
    has_more: bool

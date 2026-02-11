"""Pydantic schemas for user-related endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserProfile(BaseModel):
    """User profile returned by GET /users/me."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(
        ...,
        description="User's unique identifier",
    )
    email: EmailStr = Field(
        ...,
        description="User's email address",
    )
    name: str | None = Field(
        default=None,
        description="User's display name",
    )
    tier: str = Field(
        ...,
        description="Subscription tier (free, founder, founder_pro, enterprise)",
    )
    status: str = Field(
        ...,
        description="Account status (active, suspended, deleted)",
    )
    email_verified: bool = Field(
        ...,
        description="Whether email has been verified",
    )
    created_at: datetime = Field(
        ...,
        description="Account creation timestamp",
    )


class ApiKeySummary(BaseModel):
    """Summary of an API key (does not include the actual key)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(
        ...,
        description="API key's unique identifier",
    )
    key_prefix: str = Field(
        ...,
        description="First 12 characters of the key for identification",
    )
    name: str | None = Field(
        default=None,
        description="Human-readable label for the key",
    )
    scopes: list[str] = Field(
        ...,
        description="Permissions granted to this key",
    )
    created_at: datetime = Field(
        ...,
        description="Key creation timestamp",
    )
    last_used_at: datetime | None = Field(
        default=None,
        description="Last time the key was used",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Key expiration time (null = never expires)",
    )
    is_revoked: bool = Field(
        ...,
        description="Whether the key has been revoked",
    )


class ApiKeyCreated(BaseModel):
    """Response when creating a new API key (includes the full key once)."""

    id: uuid.UUID = Field(
        ...,
        description="API key's unique identifier",
    )
    key: str = Field(
        ...,
        description="The full API key (shown only once, save it securely)",
    )
    key_prefix: str = Field(
        ...,
        description="First 12 characters of the key for identification",
    )
    name: str | None = Field(
        default=None,
        description="Human-readable label for the key",
    )
    scopes: list[str] = Field(
        ...,
        description="Permissions granted to this key",
    )
    created_at: datetime = Field(
        ...,
        description="Key creation timestamp",
    )


class ApiKeyList(BaseModel):
    """List of API keys for a user."""

    items: list[ApiKeySummary] = Field(
        ...,
        description="List of API keys",
    )
    total: int = Field(
        ...,
        description="Total number of API keys",
    )


class CreateApiKeyRequest(BaseModel):
    """Request body for creating a new API key."""

    name: str | None = Field(
        default=None,
        description="Human-readable label for the key",
        max_length=100,
    )
    scopes: list[str] = Field(
        default=["read", "write", "execute"],
        description="Permissions to grant to this key",
    )
    expires_in_days: int | None = Field(
        default=None,
        description="Number of days until key expires (null = never expires)",
        ge=1,
        le=730,  # Max 2 years
    )

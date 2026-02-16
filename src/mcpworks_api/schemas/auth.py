"""Pydantic schemas for authentication endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Request body for POST /auth/register."""

    email: EmailStr = Field(
        ...,
        description="User's email address",
        examples=["user@example.com"],
    )
    password: str = Field(
        ...,
        description="Password (min 8 chars, must include letter and number)",
        min_length=8,
        max_length=128,
    )
    name: str | None = Field(
        default=None,
        description="User's display name",
        max_length=255,
    )
    accept_tos: bool = Field(
        default=False,
        description="Must be true to accept Terms of Service and Privacy Policy",
    )


class RegisterResponse(BaseModel):
    """Response body for POST /auth/register."""

    user: "UserInfo" = Field(
        ...,
        description="Newly created user information",
    )
    access_token: str = Field(
        ...,
        description="JWT access token for immediate use",
    )
    refresh_token: str = Field(
        ...,
        description="JWT refresh token for obtaining new access tokens",
    )
    token_type: str = Field(
        default="bearer",
        description="Token type (always 'bearer')",
    )
    expires_in: int = Field(
        ...,
        description="Access token expiration time in seconds",
    )
    legal_urls: dict[str, str] = Field(
        default={
            "terms": "https://api.mcpworks.io/v1/legal/terms",
            "privacy": "https://api.mcpworks.io/v1/legal/privacy",
            "aup": "https://api.mcpworks.io/v1/legal/aup",
        },
        description="URLs for legal documents",
    )


class UserInfo(BaseModel):
    """Basic user information returned in auth responses."""

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
    created_at: datetime = Field(
        ...,
        description="Account creation timestamp",
    )


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""

    email: EmailStr = Field(
        ...,
        description="User's email address",
        examples=["user@example.com"],
    )
    password: str = Field(
        ...,
        description="User's password",
    )


class LoginResponse(BaseModel):
    """Response body for POST /auth/login."""

    access_token: str = Field(
        ...,
        description="JWT access token for API authorization",
    )
    refresh_token: str = Field(
        ...,
        description="JWT refresh token for obtaining new access tokens",
    )
    token_type: str = Field(
        default="bearer",
        description="Token type (always 'bearer')",
    )
    expires_in: int = Field(
        ...,
        description="Access token expiration time in seconds",
    )


class TokenRequest(BaseModel):
    """Request body for POST /auth/token (API key exchange)."""

    api_key: str = Field(
        ...,
        description="API key in format mcpw_{random}",
        min_length=10,
        examples=["mcpw_a1b2c3d4e5f6..."],
    )


class TokenResponse(BaseModel):
    """Response body for POST /auth/token."""

    access_token: str = Field(
        ...,
        description="JWT access token for API authorization",
    )
    refresh_token: str = Field(
        ...,
        description="JWT refresh token for obtaining new access tokens",
    )
    token_type: str = Field(
        default="bearer",
        description="Token type (always 'bearer')",
    )
    expires_in: int = Field(
        ...,
        description="Access token expiration time in seconds",
    )


class RefreshRequest(BaseModel):
    """Request body for POST /auth/refresh."""

    refresh_token: str = Field(
        ...,
        description="JWT refresh token",
    )


class RefreshResponse(BaseModel):
    """Response body for POST /auth/refresh."""

    access_token: str = Field(
        ...,
        description="New JWT access token",
    )
    token_type: str = Field(
        default="bearer",
        description="Token type (always 'bearer')",
    )
    expires_in: int = Field(
        ...,
        description="Access token expiration time in seconds",
    )


class LogoutAllRequest(BaseModel):
    """Request body for POST /auth/logout-all (optional)."""

    pass  # No body needed, user identified by JWT


class CreateApiKeyRequest(BaseModel):
    """Request body for POST /auth/api-keys."""

    name: str | None = Field(
        default=None,
        description="Human-readable label for the API key",
        max_length=255,
    )
    scopes: list[str] | None = Field(
        default=None,
        description="Permissions granted to this key",
        examples=[["read", "write", "execute"]],
    )
    expires_in_days: int | None = Field(
        default=None,
        description="Days until expiration (None = never)",
        ge=1,
        le=365,
    )


class ApiKeyInfo(BaseModel):
    """API key information returned in responses."""

    id: uuid.UUID = Field(
        ...,
        description="API key unique identifier",
    )
    name: str | None = Field(
        default=None,
        description="Human-readable label",
    )
    key_prefix: str = Field(
        ...,
        description="First 12 characters of the key (for identification)",
    )
    scopes: list[str] = Field(
        ...,
        description="Permissions granted to this key",
    )
    created_at: datetime = Field(
        ...,
        description="Key creation timestamp",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Key expiration timestamp",
    )
    last_used_at: datetime | None = Field(
        default=None,
        description="Last time the key was used",
    )


class CreateApiKeyResponse(BaseModel):
    """Response body for POST /auth/api-keys."""

    api_key: ApiKeyInfo = Field(
        ...,
        description="API key information",
    )
    raw_key: str = Field(
        ...,
        description="Full API key (only shown once, save it securely)",
    )

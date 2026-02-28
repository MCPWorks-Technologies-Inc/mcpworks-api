"""Pydantic schemas for Function and FunctionVersion models."""

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_BACKENDS = {"code_sandbox", "activepieces", "nanobot", "github_repo"}


class FunctionVersionCreate(BaseModel):
    """Schema for creating a function version."""

    backend: str = Field(
        ...,
        description="Function backend",
        examples=["code_sandbox", "activepieces"],
    )

    code: str | None = Field(
        None,
        description="Function code (for code_sandbox backend)",
    )

    config: dict[str, Any] | None = Field(
        None,
        description="Backend-specific configuration",
    )

    input_schema: dict[str, Any] | None = Field(
        None,
        description="JSON Schema for input validation",
    )

    output_schema: dict[str, Any] | None = Field(
        None,
        description="JSON Schema for output validation",
    )

    required_env: list[str] | None = Field(
        None,
        description="Environment variables required for execution",
    )

    optional_env: list[str] | None = Field(
        None,
        description="Optional environment variables",
    )

    created_by: str | None = Field(
        None,
        max_length=100,
        description="Who created this version (e.g. 'Claude Opus 4.6')",
    )

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        """Validate backend is supported."""
        if v not in ALLOWED_BACKENDS:
            raise ValueError(f"Backend must be one of {ALLOWED_BACKENDS}")
        return v


class FunctionVersionResponse(BaseModel):
    """Schema for function version responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    function_id: UUID
    version: int
    backend: str
    code: str | None = None
    config: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    required_env: list[str] | None = None
    optional_env: list[str] | None = None
    created_by: str | None = None
    created_at: datetime


class FunctionBase(BaseModel):
    """Base function fields."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=63,
        description="Function name (URL-safe)",
        examples=["authenticate_user", "process-payment", "sync_data"],
    )

    description: str | None = Field(
        None,
        max_length=1000,
        description="Human-readable description",
    )

    tags: list[str] | None = Field(
        None,
        description="Tags for categorization",
        examples=[["auth", "security"], ["payment", "stripe"]],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate function name is URL-safe."""
        if not re.match(r"^[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?$", v):
            raise ValueError(
                "Function name must be lowercase alphanumeric with hyphens/underscores"
            )
        return v.lower()


class FunctionCreate(FunctionBase):
    """Schema for creating a function."""

    initial_version: FunctionVersionCreate = Field(
        ...,
        description="Initial function version",
    )


class FunctionUpdate(BaseModel):
    """Schema for updating a function (creates new version)."""

    description: str | None = Field(None, max_length=1000)
    tags: list[str] | None = None
    new_version: FunctionVersionCreate | None = Field(
        None,
        description="New function version (creates and activates)",
    )


class FunctionResponse(FunctionBase):
    """Schema for function responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    service_id: UUID
    active_version: int
    created_at: datetime
    updated_at: datetime | None = None

    call_count: int = Field(default=0, description="Total tool invocations for this function")

    # Optional expanded fields
    active_version_details: FunctionVersionResponse | None = None
    execution_count: int = Field(
        default=0,
        description="Total number of executions",
    )


class FunctionList(BaseModel):
    """Schema for function list."""

    functions: list[FunctionResponse]
    total: int
    page: int = 1
    page_size: int = 50
    has_more: bool

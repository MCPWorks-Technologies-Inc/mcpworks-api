"""Pydantic schemas for procedure endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ProcedureStepSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    function_ref: str = Field(..., min_length=3, max_length=255, description="service.function format")
    instructions: str = Field(..., min_length=1, max_length=4000)
    failure_policy: str = Field("required", description="required, allowed, or skip")
    max_retries: int = Field(1, ge=0, le=5)
    validation: dict[str, Any] | None = Field(None, description='e.g. {"required_fields": ["token"]}')

    @field_validator("failure_policy")
    @classmethod
    def validate_failure_policy(cls, v: str) -> str:
        if v not in ("required", "allowed", "skip"):
            raise ValueError("failure_policy must be 'required', 'allowed', or 'skip'")
        return v

    @field_validator("function_ref")
    @classmethod
    def validate_function_ref(cls, v: str) -> str:
        if "." not in v:
            raise ValueError("function_ref must be in 'service.function' format")
        return v


class CreateProcedureRequest(BaseModel):
    service: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    steps: list[ProcedureStepSchema] = Field(..., min_length=1, max_length=20)


class UpdateProcedureRequest(BaseModel):
    description: str | None = None
    steps: list[ProcedureStepSchema] | None = Field(None, min_length=1, max_length=20)


class ProcedureStepResponse(BaseModel):
    step_number: int
    name: str
    function_ref: str
    instructions: str
    failure_policy: str = "required"
    max_retries: int = 1
    validation: dict[str, Any] | None = None


class ProcedureResponse(BaseModel):
    id: uuid.UUID
    name: str
    service_name: str
    description: str | None = None
    active_version: int
    steps: list[ProcedureStepResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProcedureListResponse(BaseModel):
    procedures: list[ProcedureResponse]
    total: int


class StepAttemptResponse(BaseModel):
    attempt: int
    started_at: str | None = None
    completed_at: str | None = None
    success: bool = False
    error: str | None = None


class ProcedureStepResultResponse(BaseModel):
    step_number: int
    name: str
    status: str
    function_called: str | None = None
    result: Any = None
    error: str | None = None
    attempt_count: int = 0
    attempts: list[StepAttemptResponse] = []


class ProcedureExecutionResponse(BaseModel):
    id: uuid.UUID
    procedure_id: uuid.UUID
    procedure_version: int
    trigger_type: str
    status: str
    current_step: int
    step_results: list[ProcedureStepResultResponse] = []
    input_context: dict[str, Any] | None = None
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None

    model_config = {"from_attributes": True}


class ProcedureExecutionListResponse(BaseModel):
    executions: list[ProcedureExecutionResponse]
    total: int

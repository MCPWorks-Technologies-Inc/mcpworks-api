"""Pydantic schemas for service endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ServiceInfo(BaseModel):
    """Service information for catalog listing."""

    name: str = Field(
        ...,
        description="Service identifier",
        examples=["math", "agent"],
    )
    display_name: str | None = Field(
        default=None,
        description="Human-readable service name",
        examples=["Math MCP"],
    )
    description: str | None = Field(
        default=None,
        description="Service description",
    )
    credit_cost: Decimal = Field(
        ...,
        description="Credits charged per request (0 = free)",
        examples=["0.00", "1.00"],
    )
    tier_required: str = Field(
        ...,
        description="Minimum tier required to access",
        examples=["free", "starter", "pro"],
    )
    status: str = Field(
        ...,
        description="Service health status: active, degraded, inactive",
        examples=["active"],
    )
    is_available: bool = Field(
        ...,
        description="Whether service is currently available for requests",
    )

    model_config = ConfigDict(from_attributes=True)


class ServiceCatalog(BaseModel):
    """Response for GET /v1/services."""

    services: list[ServiceInfo] = Field(
        ...,
        description="List of available services",
    )


class MathVerifyRequest(BaseModel):
    """Request body for POST /v1/services/math/verify."""

    problem: str = Field(
        ...,
        description="The mathematical problem, equation, or calculation to verify",
        examples=["2 + 2 = 4", "The derivative of x^2 is 2x"],
    )
    expected_answer: str | None = Field(
        default=None,
        description="Optional expected answer to verify against",
    )
    show_work: bool = Field(
        default=True,
        description="Whether to include step-by-step solution",
    )
    verification_mode: str = Field(
        default="smart",
        description="Verification strategy: 'fast', 'smart', or 'thorough'",
        pattern="^(fast|smart|thorough)$",
    )
    context: str | None = Field(
        default=None,
        description="Optional additional context about the problem domain",
    )


class MathVerifyResponse(BaseModel):
    """Response body for POST /v1/services/math/verify."""

    is_correct: bool = Field(
        ...,
        description="Whether the mathematical statement/answer is correct",
    )
    confidence: float = Field(
        ...,
        description="Confidence score (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )
    solution: str | None = Field(
        default=None,
        description="Step-by-step solution (if show_work=true)",
    )
    correct_answer: str | None = Field(
        default=None,
        description="The correct answer (if different from provided)",
    )
    model_used: str = Field(
        ...,
        description="Model used for verification",
        examples=["qwen2.5-math-1.5b", "qwen2.5-math-7b"],
    )


class MathHelpRequest(BaseModel):
    """Request body for POST /v1/services/math/help."""

    question: str = Field(
        ...,
        description="Your math question or the problem you need help with",
    )
    guidance_type: str = Field(
        default="general",
        description="Type of help: 'strategy', 'explanation', 'solve', or 'general'",
        pattern="^(strategy|explanation|solve|general)$",
    )
    detail_level: str = Field(
        default="detailed",
        description="Level of detail: 'brief', 'detailed', or 'comprehensive'",
        pattern="^(brief|detailed|comprehensive)$",
    )
    context: str | None = Field(
        default=None,
        description="Optional context about your level or what you already know",
    )


class MathHelpResponse(BaseModel):
    """Response body for POST /v1/services/math/help."""

    answer: str = Field(
        ...,
        description="The tutoring response",
    )
    guidance_type: str = Field(
        ...,
        description="Type of guidance provided",
    )
    related_topics: list[str] = Field(
        default_factory=list,
        description="Related mathematical topics for further study",
    )


class ServiceProxyResponse(BaseModel):
    """Generic response wrapper for proxied service calls."""

    status_code: int = Field(
        ...,
        description="HTTP status code from backend service",
    )
    data: Any = Field(
        ...,
        description="Response data from backend service",
    )
    service: str = Field(
        ...,
        description="Name of the service that handled the request",
    )
    credits_charged: Decimal = Field(
        default=Decimal("0.00"),
        description="Credits charged for this request",
    )


# Agent execution schemas


class AgentExecuteRequest(BaseModel):
    """Request body for POST /v1/services/agent/execute/{workflow_id}."""

    input_data: dict[str, Any] | None = Field(
        default=None,
        description="Input parameters for the workflow",
    )


class ExecutionInfo(BaseModel):
    """Execution information."""

    execution_id: str = Field(
        ...,
        description="Unique execution identifier",
    )
    workflow_id: str = Field(
        ...,
        description="Workflow being executed",
    )
    status: str = Field(
        ...,
        description="Execution status: pending, running, completed, failed, cancelled, timed_out",
    )
    started_at: datetime | None = Field(
        default=None,
        description="When execution started",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="When execution completed",
    )
    duration_seconds: float | None = Field(
        default=None,
        description="Execution duration in seconds",
    )
    result_data: dict[str, Any] | None = Field(
        default=None,
        description="Execution result (on completion)",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message (on failure)",
    )
    error_code: str | None = Field(
        default=None,
        description="Error code (on failure)",
    )

    model_config = ConfigDict(from_attributes=True)


class AgentExecuteResponse(BaseModel):
    """Response body for POST /v1/services/agent/execute/{workflow_id}."""

    execution_id: str = Field(
        ...,
        description="Unique execution identifier",
    )
    workflow_id: str = Field(
        ...,
        description="Workflow being executed",
    )
    status: str = Field(
        ...,
        description="Execution status: pending, running",
    )
    credits_held: Decimal = Field(
        ...,
        description="Credits held for this execution",
    )
    message: str = Field(
        default="Execution started",
        description="Status message",
    )


class AgentCallbackRequest(BaseModel):
    """Callback request from mcpworks-agent on execution completion."""

    status: str = Field(
        ...,
        description="Execution status: completed, failed",
        pattern="^(completed|failed)$",
    )
    result_data: dict[str, Any] | None = Field(
        default=None,
        description="Execution result (on success)",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message (on failure)",
    )
    error_code: str | None = Field(
        default=None,
        description="Error code (on failure)",
    )


class AgentCallbackResponse(BaseModel):
    """Response to callback from mcpworks-agent."""

    execution_id: str = Field(
        ...,
        description="Execution identifier",
    )
    credits_action: str = Field(
        ...,
        description="Action taken on credits: committed, released",
    )
    credits_amount: Decimal = Field(
        ...,
        description="Credits committed or released",
    )


class ExecutionList(BaseModel):
    """List of executions for GET /v1/services/agent/executions."""

    executions: list[ExecutionInfo] = Field(
        ...,
        description="List of executions",
    )
    total: int = Field(
        ...,
        description="Total number of executions",
    )

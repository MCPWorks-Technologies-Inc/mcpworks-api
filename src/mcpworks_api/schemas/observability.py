"""Pydantic schemas for orchestration observability endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OrchestrationStepDetail(BaseModel):
    sequence_number: int
    decision_type: str
    tool_name: str | None = None
    reason_category: str | None = None
    duration_ms: int | None = None
    status: str | None = None


class ExecutionRef(BaseModel):
    execution_id: str
    function_name: str | None = None
    status: str | None = None
    duration_ms: int | None = None


class LimitsSnapshot(BaseModel):
    iterations: int | None = None
    ai_tokens: int | None = None
    functions_called: int | None = None
    execution_seconds: float | None = None


class OrchestrationRunSummary(BaseModel):
    id: str
    agent_id: str
    trigger_type: str
    trigger_detail: str | None = None
    orchestration_mode: str | None = None
    schedule_id: str | None = None
    outcome: str | None = None
    status: str
    functions_called_count: int | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None


class OrchestrationRunDetail(OrchestrationRunSummary):
    limits_consumed: LimitsSnapshot | None = None
    limits_configured: LimitsSnapshot | None = None
    result_summary: str | None = None
    steps: list[OrchestrationStepDetail] = Field(default_factory=list)
    executions: list[ExecutionRef] = Field(default_factory=list)


class OrchestrationRunListResponse(BaseModel):
    runs: list[OrchestrationRunSummary]
    total: int
    limit: int = Field(default=20)
    offset: int = Field(default=0)


class ScheduleFireSummary(BaseModel):
    id: str
    schedule_id: str
    agent_id: str
    fired_at: str
    status: str
    agent_run_id: str | None = None
    error_detail: str | None = None


class ScheduleFireListResponse(BaseModel):
    fires: list[ScheduleFireSummary]
    total: int
    limit: int = Field(default=20)
    offset: int = Field(default=0)

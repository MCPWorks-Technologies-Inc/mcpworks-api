"""Pydantic schemas for execution debugging endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExecutionSummary(BaseModel):
    id: str
    namespace_id: str | None = None
    service: str | None = None
    function: str | None = None
    version: int | None = None
    status: str
    error_message: str | None = None
    execution_time_ms: int | None = None
    started_at: str | None = None
    completed_at: str | None = None


class ExecutionDetail(ExecutionSummary):
    backend: str | None = None
    input_data: dict[str, Any] | None = None
    result_data: dict[str, Any] | None = None
    error_code: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    created_at: str | None = None


class ExecutionListResponse(BaseModel):
    executions: list[ExecutionSummary]
    total: int
    limit: int = Field(default=20)
    offset: int = Field(default=0)

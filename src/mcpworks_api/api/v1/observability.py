"""Orchestration observability endpoints — run history and schedule fire history."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.dependencies import require_active_status
from mcpworks_api.models.user import User
from mcpworks_api.schemas.observability import (
    ExecutionRef,
    OrchestrationRunDetail,
    OrchestrationRunListResponse,
    OrchestrationRunSummary,
    OrchestrationStepDetail,
    ScheduleFireListResponse,
    ScheduleFireSummary,
)
from mcpworks_api.services.observability_service import ObservabilityService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["observability"])


async def _get_current_user(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_active_status),
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/agents/{agent_id}/runs", response_model=OrchestrationRunListResponse)
async def list_orchestration_runs(
    agent_id: uuid.UUID,
    trigger_type: str | None = Query(None),
    outcome: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(_get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> OrchestrationRunListResponse:
    svc = ObservabilityService(db)
    runs, total = await svc.list_runs(
        agent_id=agent_id,
        trigger_type=trigger_type,
        outcome=outcome,
        limit=limit,
        offset=offset,
    )
    items = [
        OrchestrationRunSummary(
            id=str(r.id),
            agent_id=str(r.agent_id),
            trigger_type=r.trigger_type,
            trigger_detail=r.trigger_detail,
            orchestration_mode=r.orchestration_mode,
            schedule_id=str(r.schedule_id) if r.schedule_id else None,
            outcome=r.outcome,
            status=r.status,
            functions_called_count=r.functions_called_count,
            started_at=r.started_at.isoformat() if r.started_at else None,
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            duration_ms=r.duration_ms,
            error=r.error,
        )
        for r in runs
    ]
    return OrchestrationRunListResponse(runs=items, total=total, limit=limit, offset=offset)


@router.get("/agents/{agent_id}/runs/{run_id}", response_model=OrchestrationRunDetail)
async def describe_orchestration_run(
    agent_id: uuid.UUID,
    run_id: uuid.UUID,
    user: User = Depends(_get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> OrchestrationRunDetail:
    svc = ObservabilityService(db)
    run = await svc.get_run(run_id)
    if not run or run.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Orchestration run not found")
    execs = await svc.get_run_executions(run_id)
    exec_refs = [
        ExecutionRef(
            execution_id=str(e.id),
            function_name=e.function_name,
            status=e.status,
            duration_ms=e.execution_time_ms,
        )
        for e in execs
    ]
    steps = [
        OrchestrationStepDetail(
            sequence_number=tc.sequence_number,
            decision_type=tc.decision_type,
            tool_name=tc.tool_name,
            reason_category=tc.reason_category,
            duration_ms=tc.duration_ms,
            status=tc.status,
        )
        for tc in run.tool_calls
    ]
    return OrchestrationRunDetail(
        id=str(run.id),
        agent_id=str(run.agent_id),
        trigger_type=run.trigger_type,
        trigger_detail=run.trigger_detail,
        orchestration_mode=run.orchestration_mode,
        schedule_id=str(run.schedule_id) if run.schedule_id else None,
        outcome=run.outcome,
        status=run.status,
        functions_called_count=run.functions_called_count,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        duration_ms=run.duration_ms,
        limits_consumed=run.limits_consumed,
        limits_configured=run.limits_configured,
        result_summary=run.result_summary,
        error=run.error,
        steps=steps,
        executions=exec_refs,
    )


@router.get("/schedules/{schedule_id}/fires", response_model=ScheduleFireListResponse)
async def list_schedule_fires(
    schedule_id: uuid.UUID,
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(_get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> ScheduleFireListResponse:
    svc = ObservabilityService(db)
    fires, total = await svc.list_fires(
        schedule_id=schedule_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    items = [
        ScheduleFireSummary(
            id=str(f.id),
            schedule_id=str(f.schedule_id),
            agent_id=str(f.agent_id),
            fired_at=f.fired_at.isoformat() if f.fired_at else None,
            status=f.status,
            agent_run_id=str(f.agent_run_id) if f.agent_run_id else None,
            error_detail=f.error_detail,
        )
        for f in fires
    ]
    return ScheduleFireListResponse(fires=items, total=total, limit=limit, offset=offset)

"""Execution query service for debugging and history."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.models.execution import Execution


class ExecutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_executions(
        self,
        namespace_id: uuid.UUID,
        service: str | None = None,
        function: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        base = select(Execution).where(Execution.namespace_id == namespace_id)

        if service:
            base = base.where(Execution.service_name == service)
        if function:
            base = base.where(Execution.function_name == function)
        if status:
            base = base.where(Execution.status == status)
        if since:
            base = base.where(Execution.created_at >= since)
        if until:
            base = base.where(Execution.created_at <= until)

        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        query = base.order_by(Execution.created_at.desc()).limit(min(limit, 100)).offset(offset)
        result = await self.db.execute(query)
        executions = result.scalars().all()

        return {
            "executions": [_to_summary(e) for e in executions],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def get_execution(
        self,
        namespace_id: uuid.UUID,
        execution_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(Execution).where(
                Execution.id == execution_id,
                Execution.namespace_id == namespace_id,
            )
        )
        execution = result.scalar_one_or_none()
        if not execution:
            return None
        return _to_detail(execution)


def _to_summary(e: Execution) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "namespace_id": str(e.namespace_id) if e.namespace_id else None,
        "service": e.service_name,
        "function": e.function_name,
        "version": e.function_version_num,
        "status": e.status,
        "error_message": e.error_message,
        "execution_time_ms": e.execution_time_ms,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
    }


def _to_detail(e: Execution) -> dict[str, Any]:
    meta = e.backend_metadata or {}
    detail = _to_summary(e)
    detail.update(
        {
            "backend": e.backend,
            "input_data": e.input_data,
            "result_data": e.result_data,
            "error_code": e.error_code,
            "stdout": meta.get("stdout"),
            "stderr": meta.get("stderr"),
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
    )
    return detail

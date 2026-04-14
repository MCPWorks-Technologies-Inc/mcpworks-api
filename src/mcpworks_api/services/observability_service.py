"""Service for querying orchestration run history and schedule fire history."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mcpworks_api.models.agent import AgentRun
from mcpworks_api.models.execution import Execution
from mcpworks_api.models.schedule_fire import ScheduleFire


class ObservabilityService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_runs(
        self,
        agent_id: uuid.UUID,
        trigger_type: str | None = None,
        outcome: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[AgentRun], int]:
        filters = [AgentRun.agent_id == agent_id]
        if trigger_type:
            filters.append(AgentRun.trigger_type == trigger_type)
        if outcome:
            filters.append(AgentRun.outcome == outcome)
        if since:
            filters.append(AgentRun.created_at >= since)
        if until:
            filters.append(AgentRun.created_at <= until)

        count_stmt = select(func.count()).select_from(AgentRun).where(*filters)
        total = (await self._db.execute(count_stmt)).scalar_one()

        stmt = (
            select(AgentRun)
            .where(*filters)
            .order_by(AgentRun.created_at.desc())
            .limit(min(limit, 100))
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_run(self, run_id: uuid.UUID) -> AgentRun | None:
        stmt = (
            select(AgentRun).options(selectinload(AgentRun.tool_calls)).where(AgentRun.id == run_id)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_run_executions(self, run_id: uuid.UUID) -> list[Execution]:
        stmt = (
            select(Execution).where(Execution.agent_run_id == run_id).order_by(Execution.created_at)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_fires(
        self,
        schedule_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        status: str | None = None,
        since: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ScheduleFire], int]:
        filters = []
        if schedule_id:
            filters.append(ScheduleFire.schedule_id == schedule_id)
        if agent_id:
            filters.append(ScheduleFire.agent_id == agent_id)
        if status:
            filters.append(ScheduleFire.status == status)
        if since:
            filters.append(ScheduleFire.fired_at >= since)

        count_stmt = select(func.count()).select_from(ScheduleFire).where(*filters)
        total = (await self._db.execute(count_stmt)).scalar_one()

        stmt = (
            select(ScheduleFire)
            .where(*filters)
            .order_by(ScheduleFire.fired_at.desc())
            .limit(min(limit, 100))
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

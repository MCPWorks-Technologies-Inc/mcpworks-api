"""Execution history and debugging endpoints."""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.api.deps import get_current_user, get_db
from mcpworks_api.core.exceptions import NotFoundError
from mcpworks_api.models.user import User
from mcpworks_api.schemas.execution import ExecutionDetail, ExecutionListResponse
from mcpworks_api.services.execution import ExecutionService
from mcpworks_api.services.namespace import NamespaceServiceManager

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/executions", tags=["executions"])


@router.get("", response_model=ExecutionListResponse)
async def list_executions(
    namespace: str = Query(..., description="Namespace name"),
    service: str | None = Query(None, description="Filter by service name"),
    function: str | None = Query(None, description="Filter by function name"),
    status: str | None = Query(None, description="Filter by status"),
    since: datetime | None = Query(None, description="Only executions after this time"),
    until: datetime | None = Query(None, description="Only executions before this time"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExecutionListResponse:
    ns_service = NamespaceServiceManager(db)
    ns = await ns_service.get_by_name(namespace, user.account_id, user_id=user.id)

    exec_service = ExecutionService(db)
    result = await exec_service.list_executions(
        namespace_id=ns.id,
        service=service,
        function=function,
        status=status,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return ExecutionListResponse(**result)


@router.get("/{execution_id}", response_model=ExecutionDetail)
async def get_execution(
    execution_id: str,
    namespace: str = Query(..., description="Namespace name"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExecutionDetail:
    ns_service = NamespaceServiceManager(db)
    ns = await ns_service.get_by_name(namespace, user.account_id, user_id=user.id)

    exec_service = ExecutionService(db)
    from uuid import UUID

    result = await exec_service.get_execution(ns.id, UUID(execution_id))
    if not result:
        raise NotFoundError(f"Execution '{execution_id}' not found")
    return ExecutionDetail(**result)

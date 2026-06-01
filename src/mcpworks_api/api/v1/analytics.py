"""Analytics REST API endpoints — token savings, server stats, optimization suggestions."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.dependencies import require_active_status
from mcpworks_api.models.user import User
from mcpworks_api.schemas.analytics import (
    FunctionMcpStatsResponse,
    ServerStatsResponse,
    SuggestionResponse,
    TokenSavingsResponse,
)
from mcpworks_api.services import analytics
from mcpworks_api.services.namespace import NamespaceServiceManager

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _get_current_user(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_active_status),
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def _resolve_namespace(namespace: str, user: User, db: AsyncSession):
    ns_service = NamespaceServiceManager(db)
    return await ns_service.get_by_name(namespace, user.account_id, user_id=user.id)


@router.get("/token-savings", response_model=TokenSavingsResponse)
async def get_token_savings(
    namespace: str = Query(..., description="Namespace name"),
    period: str = Query("24h", description="Time period", enum=["1h", "24h", "7d", "30d"]),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenSavingsResponse:
    ns = await _resolve_namespace(namespace, user, db)
    result = await analytics.get_token_savings(db, ns.id, period)
    return TokenSavingsResponse(**result)


@router.get("/server-stats/{server_name}", response_model=ServerStatsResponse)
async def get_server_stats(
    server_name: str,
    namespace: str = Query(..., description="Namespace name"),
    period: str = Query("24h", description="Time period", enum=["1h", "24h", "7d", "30d"]),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ServerStatsResponse:
    ns = await _resolve_namespace(namespace, user, db)
    result = await analytics.get_server_stats(db, ns.id, server_name, period)
    return ServerStatsResponse(**result)


@router.get("/function-stats", response_model=FunctionMcpStatsResponse)
async def get_function_stats(
    namespace: str = Query(..., description="Namespace name"),
    period: str = Query("24h", description="Time period", enum=["1h", "24h", "7d", "30d"]),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FunctionMcpStatsResponse:
    ns = await _resolve_namespace(namespace, user, db)
    result = await analytics.get_function_stats(db, ns.id, period)
    return FunctionMcpStatsResponse(**result)


@router.get("/suggestions", response_model=SuggestionResponse)
async def get_suggestions(
    namespace: str = Query(..., description="Namespace name"),
    server: str | None = Query(None, description="MCP server name (omit for all)"),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuggestionResponse:
    ns = await _resolve_namespace(namespace, user, db)
    result = await analytics.suggest_optimizations(db, ns.id, server)
    return SuggestionResponse(suggestions=result)

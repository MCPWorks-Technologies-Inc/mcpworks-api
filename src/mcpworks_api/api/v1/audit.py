"""ORDER-022: Audit log endpoint — read-only, account-scoped."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.dependencies import ActiveUserId as CurrentUserId
from mcpworks_api.services.security_event import SecurityEventService

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventResponse(BaseModel):
    id: str
    timestamp: str
    event_type: str
    severity: str
    actor_ip_hash: str | None = None
    actor_id: str | None = None
    details: dict | None = None


class AuditLogsResponse(BaseModel):
    events: list[AuditEventResponse]
    total: int = Field(description="Total matching events")
    limit: int
    offset: int


@router.get("/logs", response_model=AuditLogsResponse)
async def get_audit_logs(
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
    event_type: str | None = Query(None, description="Filter by event type"),
    severity: str | None = Query(None, description="Filter by severity"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AuditLogsResponse:
    """List security audit events for the current account."""
    svc = SecurityEventService(db)
    events, total = await svc.get_events(
        actor_id=str(user_id),
        event_type=event_type,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    return AuditLogsResponse(
        events=[
            AuditEventResponse(
                id=str(e.id),
                timestamp=e.timestamp.isoformat(),
                event_type=e.event_type,
                severity=e.severity,
                actor_ip_hash=e.actor_ip_hash,
                actor_id=e.actor_id,
                details=e.details,
            )
            for e in events
        ],
        total=total,
        limit=limit,
        offset=offset,
    )

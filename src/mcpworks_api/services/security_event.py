"""ORDER-022: Security event service for audit logging."""

from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.models.security_event import SecurityEvent, hash_ip

logger = structlog.get_logger(__name__)


class SecurityEventService:
    """Creates and queries security events for SOC 2 audit trail."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log_event(
        self,
        event_type: str,
        severity: str,
        actor_ip: str | None = None,
        actor_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> SecurityEvent:
        """Persist a security event with hashed IP."""
        event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            actor_ip_hash=hash_ip(actor_ip),
            actor_id=actor_id,
            details=details,
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def get_events(
        self,
        actor_id: str | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SecurityEvent], int]:
        """Query security events with optional filters."""
        query = select(SecurityEvent)
        count_query = select(func.count()).select_from(SecurityEvent)

        if actor_id:
            query = query.where(SecurityEvent.actor_id == actor_id)
            count_query = count_query.where(SecurityEvent.actor_id == actor_id)
        if event_type:
            query = query.where(SecurityEvent.event_type == event_type)
            count_query = count_query.where(SecurityEvent.event_type == event_type)
        if severity:
            query = query.where(SecurityEvent.severity == severity)
            count_query = count_query.where(SecurityEvent.severity == severity)

        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.order_by(SecurityEvent.timestamp.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        events = list(result.scalars().all())

        return events, total


async def fire_security_event(
    db: AsyncSession,
    event_type: str,
    severity: str,
    actor_ip: str | None = None,
    actor_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Fire-and-forget helper for logging security events from middleware.

    Catches all exceptions so it never disrupts request processing.
    """
    try:
        svc = SecurityEventService(db)
        await svc.log_event(
            event_type=event_type,
            severity=severity,
            actor_ip=actor_ip,
            actor_id=actor_id,
            details=details,
        )
    except Exception as e:
        logger.warning("security_event_logging_failed", error=str(e), event_type=event_type)

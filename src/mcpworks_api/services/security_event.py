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
    db: AsyncSession | None,
    event_type: str,
    severity: str,
    actor_ip: str | None = None,
    actor_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Fire-and-forget helper for logging security events from middleware.

    Catches all exceptions so it never disrupts request processing.
    Also degrades trust score for agents associated with the event.
    When db is None (e.g. called from orchestrator), creates a fresh session.
    """
    from mcpworks_api.middleware.observability import record_security_event

    record_security_event(event_type=event_type, severity=severity)
    try:
        if db is None:
            from mcpworks_api.core.database import get_db_context

            async with get_db_context() as fresh_db:
                svc = SecurityEventService(fresh_db)
                await svc.log_event(
                    event_type=event_type,
                    severity=severity,
                    actor_ip=actor_ip,
                    actor_id=actor_id,
                    details=details,
                )
                await _degrade_agent_trust(fresh_db, event_type, details)
        else:
            svc = SecurityEventService(db)
            await svc.log_event(
                event_type=event_type,
                severity=severity,
                actor_ip=actor_ip,
                actor_id=actor_id,
                details=details,
            )
            await _degrade_agent_trust(db, event_type, details)
    except Exception as e:
        logger.warning("security_event_logging_failed", error=str(e), event_type=event_type)


async def _degrade_agent_trust(
    db: AsyncSession,
    event_type: str,
    details: dict[str, Any] | None,
) -> None:
    """Degrade agent trust score if event is associated with an agent."""
    if not details:
        return
    agent_id = details.get("agent_id")
    if not agent_id:
        return

    try:
        import uuid

        from mcpworks_api.services.trust_score import adjust_trust_score, get_delta_for_event

        agent_uuid = uuid.UUID(str(agent_id))
        delta = get_delta_for_event(event_type)
        await adjust_trust_score(db, agent_uuid, delta, reason=event_type)
    except Exception as e:
        logger.warning("trust_score_degradation_failed", error=str(e), agent_id=str(agent_id))

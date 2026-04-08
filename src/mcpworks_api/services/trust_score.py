"""Agent trust score management — degradation on security events, recovery on success."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.models.agent import Agent

logger = structlog.get_logger(__name__)

TRUST_DEFAULT = 500
TRUST_MIN = 0
TRUST_MAX = 1000
TRUST_RECOVERY_CAP = 500
TRUST_RECOVERY_DELTA = 1

EVENT_DELTAS: dict[str, int] = {
    "scanner.prompt_injection": -50,
    "scanner.secret_leak": -100,
    "scanner.output_blocked": -25,
    "agent.unauthorized_access": -50,
}
DEFAULT_DELTA = -25


async def adjust_trust_score(
    db: AsyncSession,
    agent_id: uuid.UUID,
    delta: int,
    reason: str,
) -> None:
    stmt = (
        update(Agent)
        .where(Agent.id == agent_id)
        .values(
            trust_score=text(f"GREATEST({TRUST_MIN}, LEAST({TRUST_MAX}, trust_score + :delta))"),
            trust_score_updated_at=text("NOW()"),
        )
        .execution_options(synchronize_session=False)
    )
    await db.execute(stmt, {"delta": delta})
    await db.commit()

    logger.info(
        "trust_score_adjusted",
        agent_id=str(agent_id),
        delta=delta,
        reason=reason,
    )


async def recover_trust_score(
    db: AsyncSession,
    agent_id: uuid.UUID,
) -> None:
    stmt = (
        update(Agent)
        .where(Agent.id == agent_id)
        .where(Agent.trust_score < TRUST_RECOVERY_CAP)
        .values(
            trust_score=text(f"LEAST({TRUST_RECOVERY_CAP}, trust_score + {TRUST_RECOVERY_DELTA})"),
            trust_score_updated_at=text("NOW()"),
        )
        .execution_options(synchronize_session=False)
    )
    await db.execute(stmt)
    await db.commit()


def get_delta_for_event(event_type: str) -> int:
    return EVENT_DELTAS.get(event_type, DEFAULT_DELTA)

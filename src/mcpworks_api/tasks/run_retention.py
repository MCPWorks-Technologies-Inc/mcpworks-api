"""Daily AgentRun retention purge task.

Deletes agent runs older than the tier-based retention period.
Registered as an APScheduler job in the API server lifespan.
"""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_async_session
from mcpworks_api.models.agent import Agent, AgentRun
from mcpworks_api.models.subscription import AGENT_TIER_CONFIG
from mcpworks_api.models.user import User

logger = structlog.get_logger(__name__)


async def purge_expired_runs() -> int:
    async with get_async_session() as db:
        return await _purge_runs(db)


async def _purge_runs(db: AsyncSession) -> int:
    total_deleted = 0
    now = datetime.now(tz=UTC)

    for tier_value, config in AGENT_TIER_CONFIG.items():
        retention_days = config["run_retention_days"]
        cutoff = now - timedelta(days=retention_days)

        result = await db.execute(
            select(Agent.id)
            .join(User, Agent.account_id == User.account_id)
            .where(User.effective_tier == tier_value)
        )
        agent_ids = [row[0] for row in result.all()]

        if not agent_ids:
            continue

        delete_result = await db.execute(
            delete(AgentRun).where(
                AgentRun.agent_id.in_(agent_ids),
                AgentRun.created_at < cutoff,
            )
        )
        count = delete_result.rowcount
        total_deleted += count

        if count > 0:
            logger.info(
                "agent_runs_purged",
                tier=tier_value,
                retention_days=retention_days,
                deleted=count,
            )

    await db.commit()
    logger.info("agent_run_retention_complete", total_deleted=total_deleted)
    return total_deleted

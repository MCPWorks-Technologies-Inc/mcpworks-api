"""Background retention pruning for orchestration observability data."""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete

from mcpworks_api.core.database import get_db_context
from mcpworks_api.models.agent import AgentRun
from mcpworks_api.models.schedule_fire import ScheduleFire

logger = structlog.get_logger(__name__)

AGENT_RUN_RETENTION_DAYS = 30
SCHEDULE_FIRE_RETENTION_DAYS = 90


async def prune_observability_data() -> None:
    try:
        async with get_db_context() as db:
            run_cutoff = datetime.now(UTC) - timedelta(days=AGENT_RUN_RETENTION_DAYS)
            result = await db.execute(delete(AgentRun).where(AgentRun.created_at < run_cutoff))
            runs_deleted = result.rowcount

            fire_cutoff = datetime.now(UTC) - timedelta(days=SCHEDULE_FIRE_RETENTION_DAYS)
            result = await db.execute(
                delete(ScheduleFire).where(ScheduleFire.created_at < fire_cutoff)
            )
            fires_deleted = result.rowcount

        if runs_deleted or fires_deleted:
            logger.info(
                "observability_retention_pruned",
                runs_deleted=runs_deleted,
                fires_deleted=fires_deleted,
                run_cutoff_days=AGENT_RUN_RETENTION_DAYS,
                fire_cutoff_days=SCHEDULE_FIRE_RETENTION_DAYS,
            )
    except Exception:
        logger.exception("observability_retention_failed")

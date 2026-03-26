"""Analytics data cleanup — 30-day retention for proxy call and execution stats."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete

from mcpworks_api.core.database import get_db_context
from mcpworks_api.models.mcp_execution_stat import McpExecutionStat
from mcpworks_api.models.mcp_proxy_call import McpProxyCall

logger = structlog.get_logger(__name__)

RETENTION_DAYS = 30
BATCH_SIZE = 10000


async def cleanup_analytics_data() -> None:
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)

    for model, table_name in [
        (McpProxyCall, "mcp_proxy_calls"),
        (McpExecutionStat, "mcp_execution_stats"),
    ]:
        total_deleted = 0
        while True:
            async with get_db_context() as db:
                time_col = (
                    McpProxyCall.called_at
                    if model is McpProxyCall
                    else McpExecutionStat.executed_at
                )
                stmt = (
                    delete(model)
                    .where(time_col < cutoff)
                    .execution_options(synchronize_session=False)
                )
                result = await db.execute(stmt)
                deleted = result.rowcount
                await db.commit()

            total_deleted += deleted
            if deleted < BATCH_SIZE:
                break

        if total_deleted > 0:
            logger.info(
                "analytics_cleanup",
                table=table_name,
                deleted=total_deleted,
                cutoff=cutoff.isoformat(),
            )

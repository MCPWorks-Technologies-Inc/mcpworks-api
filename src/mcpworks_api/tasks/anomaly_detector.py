"""Periodic anomaly detection — OWASP LLM10 defense.

Runs every 5 minutes to flag accounts with unusual execution patterns:
- Execution spikes (>50 in 5 minutes)
- Error storms (>50% failure rate in 5 minutes)
"""

import structlog
from sqlalchemy import text

from mcpworks_api.core.database import get_db_context
from mcpworks_api.services.security_event import fire_security_event

logger = structlog.get_logger(__name__)


async def detect_anomalies() -> None:
    async with get_db_context() as db:
        results = await db.execute(
            text("""
            SELECT e.user_id,
                   COUNT(*) as exec_count,
                   AVG(EXTRACT(EPOCH FROM (e.completed_at - e.started_at))) as avg_duration,
                   COUNT(*) FILTER (WHERE e.status = 'failed') as failures
            FROM executions e
            WHERE e.started_at > NOW() - INTERVAL '5 minutes'
            GROUP BY e.user_id
            HAVING COUNT(*) > 50
                OR COUNT(*) FILTER (WHERE e.status = 'failed')::float
                   / GREATEST(COUNT(*), 1) > 0.5
        """)
        )

        for row in results:
            if row.exec_count > 50:
                await fire_security_event(
                    db,
                    event_type="anomaly_spike",
                    severity="warning",
                    actor_id=str(row.user_id),
                    details={
                        "exec_count_5min": row.exec_count,
                        "avg_duration_sec": round(float(row.avg_duration or 0), 2),
                    },
                )
                logger.warning(
                    "anomaly_spike_detected",
                    user_id=str(row.user_id),
                    exec_count=row.exec_count,
                )

            failure_rate = row.failures / max(row.exec_count, 1)
            if failure_rate > 0.5:
                await fire_security_event(
                    db,
                    event_type="anomaly_error_storm",
                    severity="warning",
                    actor_id=str(row.user_id),
                    details={
                        "total": row.exec_count,
                        "failures": row.failures,
                        "failure_rate_pct": round(failure_rate * 100),
                    },
                )
                logger.warning(
                    "anomaly_error_storm_detected",
                    user_id=str(row.user_id),
                    total=row.exec_count,
                    failures=row.failures,
                )

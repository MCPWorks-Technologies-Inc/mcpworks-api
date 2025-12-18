"""Health check endpoints."""

from typing import Any

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.redis import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Basic health check endpoint.

    Returns:
        Simple status object indicating the service is running.
    """
    return {"status": "healthy"}


@router.get("/health/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Readiness check - verifies database and Redis connections.

    Returns:
        Status object with component health details.
    """
    components = {}

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        components["database"] = "healthy"
    except Exception as e:
        components["database"] = f"unhealthy: {str(e)}"

    # Check Redis
    try:
        await redis.ping()
        components["redis"] = "healthy"
    except Exception as e:
        components["redis"] = f"unhealthy: {str(e)}"

    # Overall status
    all_healthy = all(v == "healthy" for v in components.values())

    return {
        "status": "ready" if all_healthy else "not_ready",
        "components": components,
    }


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """Liveness check - indicates if the service is alive.

    Used by Kubernetes/load balancers to determine if the
    service should be restarted.

    Returns:
        Simple status object.
    """
    return {"status": "alive"}

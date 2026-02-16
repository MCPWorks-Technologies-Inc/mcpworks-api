"""Health check endpoints.

ORDER-015: Readiness check verifies DB, Redis, and sandbox binary.
"""

from pathlib import Path
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

    # ORDER-015: Check sandbox binary (production only)
    nsjail_path = Path("/usr/local/bin/nsjail")
    spawn_script = Path("/opt/mcpworks/bin/spawn-sandbox.sh")
    sandbox_packages = Path("/opt/mcpworks/sandbox-root/site-packages")

    if nsjail_path.exists() or spawn_script.exists():
        # We're in a production-like environment, check sandbox
        sandbox_ok = nsjail_path.exists() and spawn_script.exists() and sandbox_packages.is_dir()
        components["sandbox"] = "healthy" if sandbox_ok else "unhealthy: missing binary or packages"

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


@router.get("/internal/verify-domain")
async def verify_domain(domain: str) -> dict[str, bool]:
    """Verify if a domain is valid for on-demand TLS certificate issuance.

    Called by Caddy before issuing certificates for wildcard subdomains.
    Only allows *.create.mcpworks.io and *.run.mcpworks.io patterns.

    Args:
        domain: The domain requesting a certificate.

    Returns:
        Empty response with 200 if valid, raises 403 if invalid.
    """
    from fastapi import HTTPException

    # Valid domain patterns for on-demand TLS
    valid_suffixes = [".create.mcpworks.io", ".run.mcpworks.io"]

    # Check if domain matches our namespace patterns
    is_valid = any(domain.endswith(suffix) for suffix in valid_suffixes)

    if not is_valid:
        raise HTTPException(
            status_code=403,
            detail=f"Domain {domain} is not allowed for certificate issuance",
        )

    return {"valid": True}

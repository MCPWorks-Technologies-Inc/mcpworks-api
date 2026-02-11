"""Service router - proxy requests to backend services.

Usage tracking is handled by BillingMiddleware via Redis, not this service.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.config import get_settings
from mcpworks_api.core.exceptions import (
    InsufficientTierError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from mcpworks_api.models import Service, ServiceStatus

# Tier hierarchy for access control - per A0-SYSTEM-SPECIFICATION.md
TIER_HIERARCHY = {
    "free": 0,
    "founder": 1,
    "founder_pro": 2,
    "enterprise": 3,
}


class ServiceRouter:
    """Routes requests to backend services with health checking and credit management."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service router with database session."""
        self.db = db
        self.settings = get_settings()

    async def get_service(self, service_name: str) -> Service | None:
        """Get a service by name.

        Args:
            service_name: Service identifier (e.g., 'math', 'agent')

        Returns:
            Service record or None if not found
        """
        result = await self.db.execute(select(Service).where(Service.name == service_name))
        return result.scalar_one_or_none()

    async def list_services(self, _user_tier: str = "free") -> list[Service]:
        """Get all available services.

        Args:
            _user_tier: User's subscription tier for filtering (reserved for future)

        Returns:
            List of services the user can access
        """
        result = await self.db.execute(
            select(Service).where(
                Service.status.in_(
                    [
                        ServiceStatus.ACTIVE.value,
                        ServiceStatus.DEGRADED.value,
                    ]
                )
            )
        )
        return list(result.scalars().all())

    def can_access_service(self, user_tier: str, service: Service) -> bool:
        """Check if user's tier allows access to service.

        Args:
            user_tier: User's subscription tier
            service: Service to check access for

        Returns:
            True if user can access the service
        """
        user_level = TIER_HIERARCHY.get(user_tier, 0)
        required_level = TIER_HIERARCHY.get(service.tier_required, 0)
        return user_level >= required_level

    async def route_request(
        self,
        service_name: str,
        method: str,
        path: str,
        user_id: uuid.UUID,
        user_tier: str,
        body: dict | None = None,
        headers: dict | None = None,
    ) -> tuple[int, dict[str, Any], Any]:
        """Route a request to a backend service.

        Handles:
        - Service availability check
        - Tier access control
        - Request proxying
        - Error handling

        Note: Usage tracking is handled by BillingMiddleware via Redis.

        Args:
            service_name: Target service name
            method: HTTP method
            path: Request path (appended to service URL)
            user_id: User making the request
            user_tier: User's subscription tier
            body: Request body (for POST/PUT/PATCH)
            headers: Additional headers to forward

        Returns:
            Tuple of (status_code, response_headers, response_body)

        Raises:
            ServiceUnavailableError: If service is not healthy
            InsufficientTierError: If user's tier doesn't permit access
            ServiceTimeoutError: If request times out
        """
        # Get service
        service = await self.get_service(service_name)
        if service is None:
            raise ServiceUnavailableError(
                service_name=service_name,
                message=f"Service '{service_name}' not found",
            )

        # Check service health
        if not service.is_available:
            raise ServiceUnavailableError(
                service_name=service_name,
                retry_after=30,
            )

        # Check tier access
        if not self.can_access_service(user_tier, service):
            raise InsufficientTierError(
                message=f"Service '{service_name}' requires tier '{service.tier_required}' or higher",
                details={
                    "required_tier": service.tier_required,
                    "user_tier": user_tier,
                },
            )

        # Make the request
        url = f"{service.url.rstrip('/')}/{path.lstrip('/')}"
        return await self._make_request(
            method=method,
            url=url,
            body=body,
            headers=headers,
        )

    async def _make_request(
        self,
        method: str,
        url: str,
        body: dict | None = None,
        headers: dict | None = None,
    ) -> tuple[int, dict[str, Any], Any]:
        """Make HTTP request to backend service.

        Args:
            method: HTTP method
            url: Full URL to request
            body: Request body
            headers: Request headers

        Returns:
            Tuple of (status_code, response_headers, response_body)

        Raises:
            ServiceTimeoutError: If request times out
            ServiceUnavailableError: If service is unreachable
        """
        # Build headers
        request_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Forwarded-By": "mcpworks-api",
        }
        if headers:
            request_headers.update(headers)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=body,
                    headers=request_headers,
                    timeout=self.settings.service_timeout_seconds,
                )

                # Parse response
                try:
                    response_body = response.json()
                except Exception:
                    response_body = {"raw": response.text}

                response_headers = dict(response.headers)

                return response.status_code, response_headers, response_body

        except httpx.TimeoutException:
            raise ServiceTimeoutError(
                message=f"Request to {url} timed out after {self.settings.service_timeout_seconds}s"
            )
        except httpx.ConnectError:
            raise ServiceUnavailableError(
                service_name=url.split("/")[2] if "/" in url else "unknown",
                message=f"Cannot connect to service at {url}",
            )

    async def check_service_health(self, service: Service) -> bool:
        """Check health of a single service.

        Args:
            service: Service to check

        Returns:
            True if service is healthy
        """
        health_url = service.health_check_url or f"{service.url}/health"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    health_url,
                    timeout=5.0,  # Short timeout for health checks
                )
                is_healthy = response.status_code == 200

                # Update service status
                new_status = (
                    ServiceStatus.ACTIVE.value if is_healthy else ServiceStatus.DEGRADED.value
                )
                await self.db.execute(
                    update(Service)
                    .where(Service.id == service.id)
                    .values(
                        status=new_status,
                        last_health_check=datetime.now(UTC),
                    )
                )
                await self.db.commit()

                return is_healthy

        except Exception:
            # Mark service as inactive on connection failure
            await self.db.execute(
                update(Service)
                .where(Service.id == service.id)
                .values(
                    status=ServiceStatus.INACTIVE.value,
                    last_health_check=datetime.now(UTC),
                )
            )
            await self.db.commit()
            return False

    async def check_all_services_health(self) -> dict[str, bool]:
        """Check health of all registered services.

        Returns:
            Dict mapping service name to health status
        """
        result = await self.db.execute(select(Service))
        services = result.scalars().all()

        health_status = {}
        for service in services:
            health_status[service.name] = await self.check_service_health(service)

        return health_status


async def seed_default_services(db: AsyncSession) -> None:
    """Seed default services (math, agent) if they don't exist.

    Called on application startup.
    """
    settings = get_settings()

    # Check if math service exists
    result = await db.execute(select(Service).where(Service.name == "math"))
    if result.scalar_one_or_none() is None:
        math_service = Service(
            name="math",
            display_name="Math MCP",
            description="Mathematical verification and tutoring service",
            url=settings.math_service_url,
            health_check_url=f"{settings.math_service_url}/health",
            credit_cost=Decimal("0.00"),  # Free service
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(math_service)

    # Check if agent service exists
    result = await db.execute(select(Service).where(Service.name == "agent"))
    if result.scalar_one_or_none() is None:
        agent_service = Service(
            name="agent",
            display_name="Workflow Agent",
            description="Workflow execution and management service",
            url=settings.agent_service_url,
            health_check_url=f"{settings.agent_service_url}/health",
            credit_cost=Decimal("1.00"),  # 1 credit per execution
            tier_required="free",
            status=ServiceStatus.ACTIVE.value,
        )
        db.add(agent_service)

    await db.commit()

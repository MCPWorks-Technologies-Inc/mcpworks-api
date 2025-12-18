"""Test factories for Service model."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import factory

from mcpworks_api.models import Service, ServiceStatus


class ServiceFactory(factory.Factory):
    """Factory for creating test Service instances."""

    class Meta:
        model = Service

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"service_{n}")
    display_name = factory.Sequence(lambda n: f"Service {n}")
    description = "Test service description"
    url = factory.Sequence(lambda n: f"http://service-{n}:8000")
    health_check_url = factory.Sequence(lambda n: f"http://service-{n}:8000/health")
    credit_cost = Decimal("1.00")
    tier_required = "free"
    status = ServiceStatus.ACTIVE.value
    last_health_check = None
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class MathServiceFactory(ServiceFactory):
    """Factory for creating Math MCP service."""

    name = "math"
    display_name = "Math MCP"
    description = "Mathematical verification and tutoring"
    url = "http://mcpworks-math:8000"
    health_check_url = "http://mcpworks-math:8000/health"
    credit_cost = Decimal("1.00")
    tier_required = "free"


class AgentServiceFactory(ServiceFactory):
    """Factory for creating Agent MCP service."""

    name = "agent"
    display_name = "Agent MCP"
    description = "Activepieces workflow execution"
    url = "http://mcpworks-agent:8000"
    health_check_url = "http://mcpworks-agent:8000/health"
    credit_cost = Decimal("5.00")
    tier_required = "starter"


class InactiveServiceFactory(ServiceFactory):
    """Factory for creating inactive services."""

    status = ServiceStatus.INACTIVE.value


class DegradedServiceFactory(ServiceFactory):
    """Factory for creating degraded services."""

    status = ServiceStatus.DEGRADED.value

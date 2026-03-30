"""Middleware components for request processing."""

from mcpworks_api.middleware.billing import (
    BillingMiddleware,
    get_account_usage,
    reset_account_usage,
)
from mcpworks_api.middleware.correlation import CorrelationIdMiddleware
from mcpworks_api.middleware.error_handler import register_exception_handlers
from mcpworks_api.middleware.request_logging import RequestLoggingMiddleware
from mcpworks_api.middleware.routing import PathRoutingMiddleware
from mcpworks_api.middleware.subdomain import (
    EndpointType,
    SubdomainMiddleware,
    get_endpoint_type,
    get_namespace,
    is_create_endpoint,
    is_run_endpoint,
)

__all__ = [
    "CorrelationIdMiddleware",
    "RequestLoggingMiddleware",
    "register_exception_handlers",
    # Path-based routing middleware (015)
    "PathRoutingMiddleware",
    # Subdomain middleware (A0, legacy)
    "SubdomainMiddleware",
    "EndpointType",
    "get_namespace",
    "get_endpoint_type",
    "is_create_endpoint",
    "is_run_endpoint",
    # Billing middleware (A0)
    "BillingMiddleware",
    "get_account_usage",
    "reset_account_usage",
]

"""Prometheus metrics middleware using prometheus-fastapi-instrumentator."""

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def setup_metrics(app: FastAPI) -> Instrumentator:
    """Configure and attach Prometheus metrics to the FastAPI app.

    Metrics exposed (per research.md decision 10):
    - http_requests_total: Counter by method, endpoint, status
    - http_request_duration_seconds: Histogram by method, endpoint
    - Additional custom metrics for business logic

    Args:
        app: FastAPI application instance

    Returns:
        Configured Instrumentator instance
    """
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/health", "/health/live", "/health/ready"],
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    )

    # Instrument and expose with default metrics
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    return instrumentator


# Custom metrics for business logic (can be expanded)
# These would be registered separately when needed

# from prometheus_client import Counter, Gauge
#
# credit_transactions_total = Counter(
#     "credit_transactions_total",
#     "Total credit transactions",
#     ["type", "status"]
# )
#
# credit_balance_available = Gauge(
#     "credit_balance_available",
#     "Total available credits by tier",
#     ["tier"]
# )
#
# auth_attempts_total = Counter(
#     "auth_attempts_total",
#     "Authentication attempts",
#     ["status", "method"]
# )
#
# service_health_status = Gauge(
#     "service_health_status",
#     "Backend service health (0=unhealthy, 1=healthy)",
#     ["service"]
# )

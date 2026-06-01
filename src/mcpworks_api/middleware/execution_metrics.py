"""Prometheus metrics for sandbox execution observability."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

function_cache_total = Counter(
    "mcpworks_function_cache_total",
    "Function result cache hits and misses",
    ["namespace", "function", "result"],
)

sandbox_executions_total = Counter(
    "sandbox_executions_total",
    "Total sandbox executions",
    ["tier", "status", "namespace"],
)

sandbox_execution_duration_seconds = Histogram(
    "sandbox_execution_duration_seconds",
    "Sandbox execution duration in seconds",
    ["tier", "status"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300],
)

sandbox_executions_in_progress = Gauge(
    "sandbox_executions_in_progress",
    "Sandbox executions currently in progress",
    ["tier"],
)

sandbox_execution_errors_total = Counter(
    "sandbox_execution_errors_total",
    "Total sandbox execution errors by type",
    ["tier", "error_type"],
)

sandbox_violations_total = Counter(
    "sandbox_violations_total",
    "Total sandbox seccomp/resource violations",
    ["tier"],
)


def record_execution(
    tier: str,
    status: str,
    duration_seconds: float,
    error_type: str | None = None,
    namespace: str = "unknown",
) -> None:
    sandbox_executions_total.labels(tier=tier, status=status, namespace=namespace).inc()
    sandbox_execution_duration_seconds.labels(tier=tier, status=status).observe(duration_seconds)
    if error_type:
        sandbox_execution_errors_total.labels(tier=tier, error_type=error_type).inc()


def record_violation(tier: str) -> None:
    sandbox_violations_total.labels(tier=tier).inc()


@asynccontextmanager
async def track_execution(tier: str, namespace: str = "unknown") -> AsyncGenerator[None, None]:  # noqa: ARG001
    sandbox_executions_in_progress.labels(tier=tier).inc()
    try:
        yield
    finally:
        sandbox_executions_in_progress.labels(tier=tier).dec()


def get_stats_snapshot() -> dict[str, Any]:
    """Build stats snapshot from Prometheus collectors.

    Reads directly from the prometheus_client registry so there is a single
    source of truth (no redundant in-memory dict).
    """
    by_tier: dict[str, dict[str, int]] = {}
    errors: dict[str, dict[str, int]] = {}
    violations: dict[str, int] = {}
    in_progress: dict[str, int] = {}
    total_count = 0

    for metric in sandbox_executions_total.collect():
        for sample in metric.samples:
            if sample.name == "sandbox_executions_total_total":
                tier = sample.labels.get("tier", "unknown")
                status = sample.labels.get("status", "unknown")
                count = int(sample.value)
                by_tier.setdefault(tier, {})[status] = by_tier.get(tier, {}).get(status, 0) + count
                total_count += count

    for metric in sandbox_execution_errors_total.collect():
        for sample in metric.samples:
            if sample.name == "sandbox_execution_errors_total_total":
                tier = sample.labels.get("tier", "unknown")
                error_type = sample.labels.get("error_type", "unknown")
                errors.setdefault(tier, {})[error_type] = int(sample.value)

    for metric in sandbox_violations_total.collect():
        for sample in metric.samples:
            if sample.name == "sandbox_violations_total_total":
                tier = sample.labels.get("tier", "unknown")
                violations[tier] = int(sample.value)

    for metric in sandbox_executions_in_progress.collect():
        for sample in metric.samples:
            if sample.name == "sandbox_executions_in_progress":
                tier = sample.labels.get("tier", "unknown")
                in_progress[tier] = int(sample.value)

    return {
        "executions_by_tier": by_tier,
        "in_progress": in_progress,
        "errors_by_tier": errors,
        "violations_by_tier": violations,
        "total_executions": total_count,
    }

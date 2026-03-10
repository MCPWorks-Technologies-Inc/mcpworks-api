"""Prometheus metrics for sandbox execution observability."""

import threading
from collections import defaultdict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

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

_stats_lock = threading.Lock()
_stats: dict[str, Any] = {
    "by_tier": defaultdict(lambda: defaultdict(int)),
    "errors": defaultdict(lambda: defaultdict(int)),
    "violations": defaultdict(int),
    "in_progress": defaultdict(int),
    "total_duration_s": defaultdict(float),
    "total_count": 0,
}


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

    with _stats_lock:
        _stats["by_tier"][tier][status] += 1
        _stats["total_duration_s"][tier] += duration_seconds
        _stats["total_count"] += 1
        if error_type:
            _stats["errors"][tier][error_type] += 1


def record_violation(tier: str) -> None:
    sandbox_violations_total.labels(tier=tier).inc()
    with _stats_lock:
        _stats["violations"][tier] += 1


@asynccontextmanager
async def track_execution(tier: str, namespace: str = "unknown") -> AsyncGenerator[None, None]:  # noqa: ARG001
    sandbox_executions_in_progress.labels(tier=tier).inc()
    with _stats_lock:
        _stats["in_progress"][tier] += 1
    try:
        yield
    finally:
        sandbox_executions_in_progress.labels(tier=tier).dec()
        with _stats_lock:
            _stats["in_progress"][tier] -= 1


def get_stats_snapshot() -> dict[str, Any]:
    with _stats_lock:
        by_tier = {t: dict(statuses) for t, statuses in _stats["by_tier"].items()}
        errors = {t: dict(errs) for t, errs in _stats["errors"].items()}
        in_progress = dict(_stats["in_progress"])
        violations = dict(_stats["violations"])
        total_duration = dict(_stats["total_duration_s"])
        total_count = _stats["total_count"]

    avg_duration: dict[str, float] = {}
    for tier, dur in total_duration.items():
        tier_count = sum(by_tier.get(tier, {}).values())
        if tier_count > 0:
            avg_duration[tier] = round(dur / tier_count, 3)

    return {
        "executions_by_tier": by_tier,
        "in_progress": in_progress,
        "errors_by_tier": errors,
        "violations_by_tier": violations,
        "avg_duration_seconds": avg_duration,
        "total_executions": total_count,
    }

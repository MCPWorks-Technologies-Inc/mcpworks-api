"""Centralized Prometheus metrics for all mcpworks subsystems.

Provides one-line record_*() helpers that mirror the fire-and-forget
pattern used in analytics and security events. All metrics are
automatically scraped by the /metrics endpoint.
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Agent orchestration
# ---------------------------------------------------------------------------
agent_runs_total = Counter(
    "mcpworks_agent_runs_total",
    "Total agent orchestration runs",
    ["namespace", "trigger_type", "status"],
)
agent_run_duration_seconds = Histogram(
    "mcpworks_agent_run_duration_seconds",
    "Agent orchestration run duration",
    ["namespace", "trigger_type"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120, 300],
)
agent_run_iterations_total = Counter(
    "mcpworks_agent_run_iterations_total",
    "Total AI loop iterations across agent runs",
    ["namespace"],
)
agent_tool_calls_total = Counter(
    "mcpworks_agent_tool_calls_total",
    "Total tool calls made during agent orchestration",
    ["namespace", "tool_name", "source", "status"],
)
agent_tool_call_duration_seconds = Histogram(
    "mcpworks_agent_tool_call_duration_seconds",
    "Duration of individual tool calls during orchestration",
    ["namespace", "source"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30],
)
agents_running = Gauge(
    "mcpworks_agents_running",
    "Number of agent orchestrations currently in progress",
    ["namespace"],
)

# ---------------------------------------------------------------------------
# MCP proxy
# ---------------------------------------------------------------------------
mcp_proxy_calls_total = Counter(
    "mcpworks_mcp_proxy_calls_total",
    "Total MCP proxy calls to external servers",
    ["namespace", "server_name", "tool_name", "status"],
)
mcp_proxy_latency_seconds = Histogram(
    "mcpworks_mcp_proxy_latency_seconds",
    "MCP proxy call latency",
    ["namespace", "server_name"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30],
)
mcp_proxy_response_bytes = Histogram(
    "mcpworks_mcp_proxy_response_bytes",
    "MCP proxy response size in bytes",
    ["namespace", "server_name"],
    buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, 500000],
)
mcp_proxy_injections_total = Counter(
    "mcpworks_mcp_proxy_injections_total",
    "Prompt injection attempts detected in MCP proxy responses",
    ["namespace", "server_name"],
)
mcp_proxy_truncations_total = Counter(
    "mcpworks_mcp_proxy_truncations_total",
    "MCP proxy responses that were truncated",
    ["namespace", "server_name"],
)

# ---------------------------------------------------------------------------
# Per-function execution
# ---------------------------------------------------------------------------
function_calls_total = Counter(
    "mcpworks_function_calls_total",
    "Total function executions by name",
    ["namespace", "service", "function", "status"],
)
function_duration_seconds = Histogram(
    "mcpworks_function_duration_seconds",
    "Function execution duration",
    ["namespace", "service", "function"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120],
)

# ---------------------------------------------------------------------------
# Auth & billing
# ---------------------------------------------------------------------------
auth_attempts_total = Counter(
    "mcpworks_auth_attempts_total",
    "Authentication attempts",
    ["method", "status"],
)
billing_quota_checks_total = Counter(
    "mcpworks_billing_quota_checks_total",
    "Billing quota check results",
    ["namespace", "result"],
)

# ---------------------------------------------------------------------------
# Security events
# ---------------------------------------------------------------------------
security_events_total = Counter(
    "mcpworks_security_events_total",
    "Security events by type and severity",
    ["event_type", "severity"],
)

# ---------------------------------------------------------------------------
# Webhook delivery
# ---------------------------------------------------------------------------
webhook_deliveries_total = Counter(
    "mcpworks_webhook_deliveries_total",
    "Telemetry webhook delivery attempts",
    ["namespace", "status"],
)
webhook_delivery_latency_seconds = Histogram(
    "mcpworks_webhook_delivery_latency_seconds",
    "Telemetry webhook delivery latency",
    ["namespace"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10],
)


# ---------------------------------------------------------------------------
# Schedule fires
# ---------------------------------------------------------------------------
schedule_fires_total = Counter(
    "mcpworks_schedule_fires_total",
    "Cron schedule fire events",
    ["namespace", "status"],
)

# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------
oauth_token_refreshes_total = Counter(
    "mcpworks_oauth_token_refreshes_total",
    "OAuth token refresh attempts",
    ["namespace", "server", "status"],
)
oauth_device_flows_total = Counter(
    "mcpworks_oauth_device_flows_total",
    "OAuth device flow initiations",
    ["namespace", "server", "status"],
)
oauth_auth_required_total = Counter(
    "mcpworks_oauth_auth_required_total",
    "AUTH_REQUIRED responses returned to callers",
    ["namespace", "server", "flow"],
)


# ---------------------------------------------------------------------------
# Helper functions — one-line calls from existing code paths
# ---------------------------------------------------------------------------
def record_agent_run(
    namespace: str,
    trigger_type: str,
    status: str,
    duration_seconds: float,
    iterations: int,
) -> None:
    agent_runs_total.labels(namespace=namespace, trigger_type=trigger_type, status=status).inc()
    agent_run_duration_seconds.labels(namespace=namespace, trigger_type=trigger_type).observe(
        duration_seconds
    )
    agent_run_iterations_total.labels(namespace=namespace).inc(iterations)


def record_agent_tool_call(
    namespace: str,
    tool_name: str,
    source: str,
    status: str,
    duration_seconds: float,
) -> None:
    agent_tool_calls_total.labels(
        namespace=namespace, tool_name=tool_name, source=source, status=status
    ).inc()
    agent_tool_call_duration_seconds.labels(namespace=namespace, source=source).observe(
        duration_seconds
    )


def record_mcp_proxy_call(
    namespace: str,
    server_name: str,
    tool_name: str,
    status: str,
    latency_seconds: float,
    response_bytes: int,
    truncated: bool = False,
    injections_found: int = 0,
) -> None:
    mcp_proxy_calls_total.labels(
        namespace=namespace, server_name=server_name, tool_name=tool_name, status=status
    ).inc()
    mcp_proxy_latency_seconds.labels(namespace=namespace, server_name=server_name).observe(
        latency_seconds
    )
    mcp_proxy_response_bytes.labels(namespace=namespace, server_name=server_name).observe(
        response_bytes
    )
    if truncated:
        mcp_proxy_truncations_total.labels(namespace=namespace, server_name=server_name).inc()
    if injections_found > 0:
        mcp_proxy_injections_total.labels(namespace=namespace, server_name=server_name).inc(
            injections_found
        )


def record_function_call(
    namespace: str,
    service: str,
    function: str,
    status: str,
    duration_seconds: float,
) -> None:
    function_calls_total.labels(
        namespace=namespace, service=service, function=function, status=status
    ).inc()
    function_duration_seconds.labels(
        namespace=namespace, service=service, function=function
    ).observe(duration_seconds)


def record_auth_attempt(method: str, status: str) -> None:
    auth_attempts_total.labels(method=method, status=status).inc()


def record_billing_check(namespace: str, result: str) -> None:
    billing_quota_checks_total.labels(namespace=namespace, result=result).inc()


def record_security_event(event_type: str, severity: str) -> None:
    security_events_total.labels(event_type=event_type, severity=severity).inc()


def record_webhook_delivery(
    namespace: str,
    status: str,
    latency_seconds: float,
) -> None:
    webhook_deliveries_total.labels(namespace=namespace, status=status).inc()
    webhook_delivery_latency_seconds.labels(namespace=namespace).observe(latency_seconds)


def record_oauth_token_refresh(namespace: str, server: str, status: str) -> None:
    oauth_token_refreshes_total.labels(namespace=namespace, server=server, status=status).inc()


def record_oauth_device_flow(namespace: str, server: str, status: str) -> None:
    oauth_device_flows_total.labels(namespace=namespace, server=server, status=status).inc()


def record_oauth_auth_required(namespace: str, server: str, flow: str) -> None:
    oauth_auth_required_total.labels(namespace=namespace, server=server, flow=flow).inc()


def record_schedule_fire(namespace: str, status: str) -> None:
    schedule_fires_total.labels(namespace=namespace, status=status).inc()

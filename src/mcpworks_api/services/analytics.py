"""MCP proxy analytics service — stats aggregation, telemetry capture, suggestions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.models.mcp_execution_stat import McpExecutionStat
from mcpworks_api.models.mcp_proxy_call import McpProxyCall

logger = structlog.get_logger(__name__)

PERIOD_MAP = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


async def record_proxy_call(
    namespace_id: uuid.UUID,
    server_name: str,
    tool_name: str,
    latency_ms: int,
    response_bytes: int,
    status: str,
    error_type: str | None = None,
    truncated: bool = False,
    injections_found: int = 0,
) -> None:
    from mcpworks_api.core.database import get_db_context

    try:
        async with get_db_context() as db:
            call = McpProxyCall(
                namespace_id=namespace_id,
                server_name=server_name,
                tool_name=tool_name,
                latency_ms=latency_ms,
                response_bytes=response_bytes,
                response_tokens_est=response_bytes // 4,
                status=status,
                error_type=error_type,
                truncated=truncated,
                injections_found=injections_found,
            )
            db.add(call)
            await db.commit()
    except Exception:
        logger.debug("analytics_record_failed", server=server_name, tool=tool_name)


async def record_execution_stats(
    namespace_id: uuid.UUID,
    execution_id: str,
    mcp_calls_count: int,
    mcp_bytes_total: int,
    result_bytes: int,
) -> None:
    from mcpworks_api.core.database import get_db_context

    if mcp_calls_count == 0:
        return

    try:
        async with get_db_context() as db:
            stat = McpExecutionStat(
                namespace_id=namespace_id,
                execution_id=execution_id,
                mcp_calls_count=mcp_calls_count,
                mcp_bytes_total=mcp_bytes_total,
                result_bytes=result_bytes,
                tokens_saved_est=max(0, (mcp_bytes_total - result_bytes)) // 4,
            )
            db.add(stat)
            await db.commit()
    except Exception:
        logger.debug("analytics_execution_record_failed", execution_id=execution_id)


async def get_server_stats(
    db: AsyncSession,
    namespace_id: uuid.UUID,
    server_name: str,
    period: str = "24h",
) -> dict[str, Any]:
    delta = PERIOD_MAP.get(period, PERIOD_MAP["24h"])
    since = datetime.now(UTC) - delta

    stmt = (
        select(
            McpProxyCall.tool_name,
            func.count().label("calls"),
            func.avg(McpProxyCall.latency_ms).label("avg_latency"),
            func.avg(McpProxyCall.response_bytes).label("avg_bytes"),
            func.avg(McpProxyCall.response_tokens_est).label("avg_tokens"),
            func.sum(func.cast(McpProxyCall.status == "error", sqlalchemy_integer())).label(
                "errors"
            ),
            func.sum(func.cast(McpProxyCall.status == "timeout", sqlalchemy_integer())).label(
                "timeouts"
            ),
            func.sum(func.cast(McpProxyCall.truncated, sqlalchemy_integer())).label("truncations"),
            func.sum(McpProxyCall.injections_found).label("total_injections"),
        )
        .where(
            McpProxyCall.namespace_id == namespace_id,
            McpProxyCall.server_name == server_name,
            McpProxyCall.called_at >= since,
        )
        .group_by(McpProxyCall.tool_name)
        .order_by(func.count().desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    total_calls = sum(r.calls for r in rows)
    total_errors = sum(r.errors or 0 for r in rows)

    tools = []
    for r in rows:
        tools.append(
            {
                "name": r.tool_name,
                "calls": r.calls,
                "avg_latency_ms": round(float(r.avg_latency or 0), 1),
                "avg_response_bytes": round(float(r.avg_bytes or 0), 0),
                "avg_response_tokens_est": round(float(r.avg_tokens or 0), 0),
                "error_count": r.errors or 0,
                "timeout_count": r.timeouts or 0,
                "truncation_count": r.truncations or 0,
                "injections_detected": r.total_injections or 0,
            }
        )

    return {
        "server": server_name,
        "period": period,
        "total_calls": total_calls,
        "total_errors": total_errors,
        "error_rate": round(total_errors / total_calls, 3) if total_calls > 0 else 0,
        "tools": tools,
    }


async def get_token_savings(
    db: AsyncSession,
    namespace_id: uuid.UUID,
    period: str = "24h",
) -> dict[str, Any]:
    delta = PERIOD_MAP.get(period, PERIOD_MAP["24h"])
    since = datetime.now(UTC) - delta

    exec_stmt = select(
        func.sum(McpExecutionStat.mcp_bytes_total).label("total_mcp_bytes"),
        func.sum(McpExecutionStat.result_bytes).label("total_result_bytes"),
    ).where(
        McpExecutionStat.namespace_id == namespace_id,
        McpExecutionStat.executed_at >= since,
    )
    exec_result = await db.execute(exec_stmt)
    exec_row = exec_result.one()

    mcp_bytes = exec_row.total_mcp_bytes or 0
    result_bytes = exec_row.total_result_bytes or 0
    savings = round((1 - result_bytes / mcp_bytes) * 100, 1) if mcp_bytes > 0 else 0

    top_stmt = (
        select(
            McpProxyCall.server_name,
            McpProxyCall.tool_name,
            func.sum(McpProxyCall.response_bytes).label("total_bytes"),
        )
        .where(
            McpProxyCall.namespace_id == namespace_id,
            McpProxyCall.called_at >= since,
        )
        .group_by(McpProxyCall.server_name, McpProxyCall.tool_name)
        .order_by(func.sum(McpProxyCall.response_bytes).desc())
        .limit(5)
    )
    top_result = await db.execute(top_stmt)
    top_consumers = [
        {"server": r.server_name, "tool": r.tool_name, "bytes": r.total_bytes or 0}
        for r in top_result.all()
    ]

    return {
        "period": period,
        "mcp_data_processed_bytes": mcp_bytes,
        "mcp_data_processed_tokens_est": mcp_bytes // 4,
        "result_returned_bytes": result_bytes,
        "result_returned_tokens_est": result_bytes // 4,
        "savings_percent": savings,
        "top_consumers": top_consumers,
    }


async def get_function_stats(
    db: AsyncSession,
    namespace_id: uuid.UUID,
    period: str = "24h",
) -> dict[str, Any]:
    delta = PERIOD_MAP.get(period, PERIOD_MAP["24h"])
    since = datetime.now(UTC) - delta

    stmt = select(
        func.count().label("executions"),
        func.avg(McpExecutionStat.mcp_calls_count).label("avg_calls"),
        func.avg(McpExecutionStat.mcp_bytes_total).label("avg_bytes"),
        func.avg(McpExecutionStat.result_bytes).label("avg_result"),
        func.avg(McpExecutionStat.tokens_saved_est).label("avg_saved"),
    ).where(
        McpExecutionStat.namespace_id == namespace_id,
        McpExecutionStat.executed_at >= since,
    )

    result = await db.execute(stmt)
    row = result.one()

    return {
        "period": period,
        "executions": row.executions or 0,
        "avg_mcp_calls_per_execution": round(float(row.avg_calls or 0), 1),
        "avg_mcp_bytes_per_execution": round(float(row.avg_bytes or 0), 0),
        "avg_result_bytes": round(float(row.avg_result or 0), 0),
        "avg_tokens_saved": round(float(row.avg_saved or 0), 0),
    }


async def suggest_optimizations(
    db: AsyncSession,
    namespace_id: uuid.UUID,
    server_name: str | None = None,
    probe_tools: list[str] | None = None,
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []

    if server_name:
        servers = [server_name]
    else:
        from mcpworks_api.models.namespace_mcp_server import NamespaceMcpServer

        stmt = select(NamespaceMcpServer.name).where(
            NamespaceMcpServer.namespace_id == namespace_id,
            NamespaceMcpServer.enabled.is_(True),
        )
        result = await db.execute(stmt)
        servers = [r[0] for r in result.all()]

    for srv in servers:
        stats = await get_server_stats(db, namespace_id, srv, "7d")

        for tool in stats.get("tools", []):
            avg_bytes = tool.get("avg_response_bytes", 0)
            calls = tool.get("calls", 0)
            errors = tool.get("error_count", 0)
            timeouts = tool.get("timeout_count", 0)
            truncations = tool.get("truncation_count", 0)

            if calls == 0:
                continue

            error_rate = errors / calls if calls > 0 else 0
            timeout_rate = timeouts / calls if calls > 0 else 0
            truncation_rate = truncations / calls if calls > 0 else 0

            if avg_bytes > 102400:
                reason = f"Avg response {int(avg_bytes / 1024)}KB."
                if probe_tools and tool["name"] in probe_tools:
                    reason += " (probe requested — run to get field-level analysis)"
                suggestions.append(
                    {
                        "type": "redact_fields",
                        "server": srv,
                        "tool": tool["name"],
                        "reason": reason,
                        "action": f"add_mcp_server_rule(name='{srv}', direction='response', "
                        f"rule={{'type': 'redact_fields', 'tools': ['{tool['name']}'], 'fields': ['...']}})  ",
                        "estimated_savings_percent": 50,
                    }
                )

            if timeout_rate > 0.10:
                suggestions.append(
                    {
                        "type": "increase_timeout",
                        "server": srv,
                        "tool": tool["name"],
                        "reason": f"{int(timeout_rate * 100)}% timeout rate. Avg latency {int(tool.get('avg_latency_ms', 0))}ms.",
                        "action": f"set_mcp_server_setting(name='{srv}', key='timeout_seconds', value=60)",
                        "estimated_impact": f"Reduce timeout errors by ~{int(min(90, timeout_rate * 500))}%",
                    }
                )

            if error_rate > 0.20:
                suggestions.append(
                    {
                        "type": "check_health",
                        "server": srv,
                        "tool": tool["name"],
                        "reason": f"{int(error_rate * 100)}% error rate.",
                        "action": f"Check credentials and server health for '{srv}'",
                        "estimated_impact": "Resolve persistent errors",
                    }
                )

            if truncation_rate > 0.05:
                suggestions.append(
                    {
                        "type": "reduce_response_size",
                        "server": srv,
                        "tool": tool["name"],
                        "reason": f"{int(truncation_rate * 100)}% of responses truncated.",
                        "action": f"set_mcp_server_setting(name='{srv}', key='response_limit_bytes', value=2097152) or add redact_fields rule",
                        "estimated_impact": "Eliminate truncation",
                    }
                )

        zero_call_tools = [t for t in stats.get("tools", []) if t.get("calls", 0) == 0]
        if not stats.get("tools") and stats.get("total_calls", 0) == 0:
            pass
        elif zero_call_tools:
            tool_names = [t["name"] for t in zero_call_tools[:5]]
            suggestions.append(
                {
                    "type": "unused_tools",
                    "server": srv,
                    "tool": None,
                    "reason": f"{len(zero_call_tools)} tools with 0 calls in 7 days: {', '.join(tool_names)}",
                    "action": "Review whether these tool wrappers are needed",
                    "estimated_impact": "Reduce functions package size",
                }
            )

    return suggestions


def sqlalchemy_integer():
    from sqlalchemy import Integer

    return Integer

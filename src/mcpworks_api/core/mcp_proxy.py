"""MCP proxy core — routes sandbox calls to external MCP servers.

Bridge key → execution context → namespace → decrypt credentials → call tool.
Enforces per-server settings (timeout, response limit, retries).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core import mcp_pool
from mcpworks_api.core.encryption import decrypt_value
from mcpworks_api.core.exec_token_registry import ExecutionContext
from mcpworks_api.models.namespace_mcp_server import DEFAULT_SETTINGS, NamespaceMcpServer

logger = structlog.get_logger(__name__)


@dataclass
class ProxyResult:
    result: str | dict | list | None = None
    truncated: bool = False
    error: str | None = None
    error_type: str | None = None


async def proxy_mcp_call(
    ctx: ExecutionContext,
    server_name: str,
    tool_name: str,
    arguments: dict,
    db: AsyncSession,
) -> ProxyResult:
    stmt = select(NamespaceMcpServer).where(
        NamespaceMcpServer.namespace_id == ctx.namespace_id,
        NamespaceMcpServer.name == server_name,
    )
    result = await db.execute(stmt)
    server = result.scalar_one_or_none()

    if not server:
        return ProxyResult(
            error=f"MCP server '{server_name}' not found in namespace '{ctx.namespace_name}'",
            error_type="NotFoundError",
        )

    if not server.enabled:
        return ProxyResult(
            error=f"MCP server '{server_name}' is disabled",
            error_type="DisabledError",
        )

    settings = dict(DEFAULT_SETTINGS)
    settings.update(server.settings or {})

    headers = None
    if server.headers_encrypted:
        try:
            headers = decrypt_value(server.headers_encrypted, server.headers_dek_encrypted)
        except Exception:
            return ProxyResult(
                error=f"Failed to decrypt credentials for MCP server '{server_name}'",
                error_type="DecryptionError",
            )

    try:
        session = await mcp_pool.get_or_connect(
            namespace_id=ctx.namespace_id,
            server_name=server_name,
            url=server.url,
            transport=server.transport,
            headers=headers,
            command=server.command,
            args=server.command_args,
        )
    except Exception as e:
        logger.error(
            "mcp_proxy_connect_failed",
            server=server_name,
            namespace=ctx.namespace_name,
            error=str(e)[:300],
        )
        return ProxyResult(
            error=f"MCP server '{server_name}' is unreachable: {str(e)[:200]}",
            error_type="ConnectionError",
        )

    timeout_sec = settings.get("timeout_seconds", 30)
    response_limit = settings.get("response_limit_bytes", 1048576)
    retry_on_failure = settings.get("retry_on_failure", True)
    retry_count = settings.get("retry_count", 2)

    last_error = None
    attempts = 1 + (retry_count if retry_on_failure else 0)

    for attempt in range(attempts):
        try:
            call_result = await asyncio.wait_for(
                session.call_tool(tool_name, arguments),
                timeout=timeout_sec,
            )

            text_parts = []
            for content in call_result.content:
                if hasattr(content, "text"):
                    text_parts.append(content.text)
                elif hasattr(content, "data"):
                    text_parts.append(f"[binary: {getattr(content, 'mimeType', 'unknown')}]")

            output = "\n".join(text_parts) if text_parts else ""

            truncated = False
            if len(output.encode("utf-8")) > response_limit:
                output = output[: response_limit // 4]
                truncated = True

            try:
                parsed = json.loads(output)
                result_value = parsed
            except (json.JSONDecodeError, ValueError):
                result_value = output

            logger.info(
                "mcp_proxy_call",
                server=server_name,
                tool=tool_name,
                namespace=ctx.namespace_name,
                attempt=attempt + 1,
                truncated=truncated,
            )

            return ProxyResult(result=result_value, truncated=truncated)

        except TimeoutError:
            return ProxyResult(
                error=f"MCP tool '{server_name}.{tool_name}' timed out after {timeout_sec}s",
                error_type="TimeoutError",
            )
        except Exception as e:
            last_error = e
            if attempt < attempts - 1:
                delay = 0.5 * (2**attempt)
                logger.warning(
                    "mcp_proxy_retry",
                    server=server_name,
                    tool=tool_name,
                    attempt=attempt + 1,
                    error=str(e)[:200],
                    retry_delay=delay,
                )
                await asyncio.sleep(delay)
                try:
                    await mcp_pool.evict(ctx.namespace_id, server_name)
                    session = await mcp_pool.get_or_connect(
                        namespace_id=ctx.namespace_id,
                        server_name=server_name,
                        url=server.url,
                        transport=server.transport,
                        headers=headers,
                        command=server.command,
                        args=server.command_args,
                    )
                except Exception:
                    pass

    logger.error(
        "mcp_proxy_error",
        server=server_name,
        tool=tool_name,
        namespace=ctx.namespace_name,
        error=str(last_error)[:300],
    )
    return ProxyResult(
        error=f"MCP tool '{server_name}.{tool_name}' failed: {str(last_error)[:200]}",
        error_type=type(last_error).__name__ if last_error else "UnknownError",
    )

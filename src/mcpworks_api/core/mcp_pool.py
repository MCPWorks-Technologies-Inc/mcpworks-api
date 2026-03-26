"""MCP connection pool — persistent sessions keyed by (namespace_id, server_name).

Connections held for TTL (default 5 minutes), evicted lazily on access.
"""

from __future__ import annotations

import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

logger = structlog.get_logger(__name__)

DEFAULT_TTL_SECONDS = 300


@dataclass
class PooledConnection:
    session: ClientSession
    stack: AsyncExitStack
    connected_at: datetime
    last_used_at: datetime
    server_name: str


_pool: dict[tuple[uuid.UUID, str], PooledConnection] = {}


async def get_or_connect(
    namespace_id: uuid.UUID,
    server_name: str,
    url: str | None,
    transport: str,
    headers: dict[str, str] | None,
    command: str | None = None,
    args: list[str] | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> ClientSession:
    key = (namespace_id, server_name)
    conn = _pool.get(key)

    if conn:
        age = (datetime.now(UTC) - conn.last_used_at).total_seconds()
        if age < ttl_seconds:
            conn.last_used_at = datetime.now(UTC)
            logger.debug("mcp_pool_hit", server=server_name)
            return conn.session
        else:
            await _evict(key)
            logger.debug("mcp_pool_expired", server=server_name, age_seconds=age)

    stack = AsyncExitStack()
    await stack.__aenter__()

    try:
        if transport == "sse":
            read_stream, write_stream = await stack.enter_async_context(
                sse_client(url=url, headers=headers)
            )
        elif transport == "streamable_http":
            read_stream, write_stream, _ = await stack.enter_async_context(
                streamablehttp_client(url=url, headers=headers)
            )
        elif transport == "stdio":
            from mcp.client.stdio import stdio_client

            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(command=command, args=args or [])
            )
        else:
            await stack.__aexit__(None, None, None)
            raise ValueError(f"Unsupported transport: {transport}")

        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()

        now = datetime.now(UTC)
        _pool[key] = PooledConnection(
            session=session,
            stack=stack,
            connected_at=now,
            last_used_at=now,
            server_name=server_name,
        )

        logger.info("mcp_pool_connect", server=server_name, transport=transport)
        return session

    except Exception:
        await stack.__aexit__(None, None, None)
        raise


async def evict(namespace_id: uuid.UUID, server_name: str) -> None:
    key = (namespace_id, server_name)
    await _evict(key)


async def evict_namespace(namespace_id: uuid.UUID) -> None:
    keys = [k for k in _pool if k[0] == namespace_id]
    for key in keys:
        await _evict(key)


async def close_all() -> None:
    keys = list(_pool.keys())
    for key in keys:
        await _evict(key)


async def _evict(key: tuple[uuid.UUID, str]) -> None:
    conn = _pool.pop(key, None)
    if conn:
        try:
            await conn.stack.__aexit__(None, None, None)
        except Exception:
            logger.debug("mcp_pool_evict_error", server=conn.server_name)


def pool_size() -> int:
    return len(_pool)

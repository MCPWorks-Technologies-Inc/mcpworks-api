"""Background poller for OAuth 2.0 Device Authorization Flow (RFC 8628).

Spawned as an asyncio task when a device code is issued. Polls the
provider's token endpoint at the specified interval until the user
approves, the code expires, or the task is cancelled.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import structlog

from mcpworks_api.core.database import get_db_context
from mcpworks_api.core.redis import get_redis_context
from mcpworks_api.services.mcp_oauth import (
    DEVICE_CODE_PREFIX,
    POLLING_PREFIX,
    _redis_key,
    exchange_device_code,
)

logger = structlog.get_logger(__name__)


async def poll_device_code(
    namespace_id: uuid.UUID,
    server_name: str,
) -> None:
    """Poll for device code approval. Runs as a background task.

    Exits when: user approves, code expires, or task is cancelled.
    """
    poll_key = _redis_key(POLLING_PREFIX, namespace_id, server_name)
    device_key = _redis_key(DEVICE_CODE_PREFIX, namespace_id, server_name)

    async with get_redis_context() as redis:
        already_polling = await redis.set(poll_key, "1", nx=True, ex=660)
    if not already_polling:
        logger.debug("device_poller_already_active", server=server_name)
        return

    logger.info("device_poller_started", server=server_name, namespace=str(namespace_id))

    try:
        interval = 5
        while True:
            await asyncio.sleep(interval)

            async with get_redis_context() as redis:
                raw = await redis.get(device_key)
            if not raw:
                logger.info("device_poller_code_expired", server=server_name)
                break

            state = json.loads(raw)
            device_code = state["device_code"]
            interval = state.get("interval", 5)

            from sqlalchemy import select

            from mcpworks_api.models.namespace_mcp_server import NamespaceMcpServer

            async with get_db_context() as db:
                stmt = select(NamespaceMcpServer).where(
                    NamespaceMcpServer.namespace_id == namespace_id,
                    NamespaceMcpServer.name == server_name,
                )
                result = await db.execute(stmt)
                server = result.scalar_one_or_none()
                if not server:
                    logger.warning("device_poller_server_gone", server=server_name)
                    break

                success = await exchange_device_code(server, device_code, db)
                if success:
                    logger.info("device_poller_authorized", server=server_name)
                    break

    except asyncio.CancelledError:
        logger.info("device_poller_cancelled", server=server_name)
    except Exception:
        logger.exception("device_poller_error", server=server_name)
    finally:
        async with get_redis_context() as redis:
            await redis.delete(poll_key)

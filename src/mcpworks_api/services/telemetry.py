"""Namespace telemetry webhook service — fire-and-forget event delivery with HMAC signing."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import re
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger(__name__)

_SIGNATURE_HEADER = "X-MCPWorks-Signature"
_USER_AGENT = "MCPWorks-Webhook/1.0"
_TIMEOUT_SECONDS = 10


def sign_payload(payload_bytes: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


def validate_webhook_url(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL format"

    if parsed.scheme not in ("http", "https"):
        return "URL must use http or https scheme"

    hostname = parsed.hostname or ""
    if not hostname:
        return "URL must have a hostname"

    is_localhost = hostname in ("localhost", "127.0.0.1", "::1")

    if parsed.scheme == "http" and not is_localhost:
        return "HTTP is only allowed for localhost; use HTTPS for remote endpoints"

    if not is_localhost:
        try:
            ip = ip_address(hostname)
            if ip.is_private:
                return f"Private IP addresses are not allowed: {hostname}"
        except ValueError:
            pass

        _private_patterns = [
            re.compile(r"^10\."),
            re.compile(r"^172\.(1[6-9]|2[0-9]|3[01])\."),
            re.compile(r"^192\.168\."),
        ]
        for pattern in _private_patterns:
            if pattern.match(hostname):
                return f"Private IP addresses are not allowed: {hostname}"

    return None


def _build_event_payload(
    namespace_name: str,
    function_name: str,
    execution_id: str,
    execution_time_ms: int,
    success: bool,
    backend: str | None = None,
    version: int | None = None,
) -> dict[str, Any]:
    return {
        "event": "tool_call",
        "namespace": namespace_name,
        "data": {
            "function": function_name,
            "execution_id": execution_id,
            "execution_time_ms": execution_time_ms,
            "success": success,
            "backend": backend or "unknown",
            "version": version or 0,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }


async def _deliver_webhook(
    url: str,
    payload_bytes: bytes,
    secret: str | None = None,
) -> None:
    import httpx

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    if secret:
        headers[_SIGNATURE_HEADER] = sign_payload(payload_bytes, secret)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, content=payload_bytes, headers=headers)
            logger.debug(
                "telemetry_webhook_delivered",
                url=url[:80],
                status=resp.status_code,
            )
    except Exception:
        logger.debug("telemetry_webhook_failed", url=url[:80], exc_info=True)


async def emit_telemetry_event(
    namespace_id,
    namespace_name: str,
    function_name: str,
    execution_id: str,
    execution_time_ms: int,
    success: bool,
    backend: str | None = None,
    version: int | None = None,
) -> None:
    from mcpworks_api.core.database import get_db_context
    from mcpworks_api.core.encryption import decrypt_value
    from mcpworks_api.models.namespace import Namespace

    try:
        async with get_db_context() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(
                    Namespace.telemetry_webhook_url,
                    Namespace.telemetry_webhook_secret_encrypted,
                    Namespace.telemetry_webhook_secret_dek,
                    Namespace.telemetry_config,
                ).where(Namespace.id == namespace_id)
            )
            row = result.first()

            if not row or not row.telemetry_webhook_url:
                return

            secret = None
            if row.telemetry_webhook_secret_encrypted and row.telemetry_webhook_secret_dek:
                try:
                    secret = decrypt_value(
                        row.telemetry_webhook_secret_encrypted,
                        row.telemetry_webhook_secret_dek,
                    )
                except Exception:
                    logger.warning("telemetry_secret_decrypt_failed", namespace=namespace_name)

            config = row.telemetry_config or {}
            batch_enabled = config.get("batch_enabled", False)

            payload = _build_event_payload(
                namespace_name=namespace_name,
                function_name=function_name,
                execution_id=execution_id,
                execution_time_ms=execution_time_ms,
                success=success,
                backend=backend,
                version=version,
            )
            payload_bytes = json.dumps(payload).encode()

            if batch_enabled:
                buffered = await _buffer_event(namespace_id, payload_bytes)
                if buffered:
                    return

            asyncio.create_task(_deliver_webhook(row.telemetry_webhook_url, payload_bytes, secret))

    except Exception:
        logger.debug("telemetry_emit_failed", namespace=namespace_name, exc_info=True)


async def _buffer_event(namespace_id, payload_bytes: bytes) -> bool:
    try:
        from mcpworks_api.core.redis import get_redis

        redis = await get_redis()
        if not redis:
            return False
        key = f"telemetry:batch:{namespace_id}"
        await redis.lpush(key, payload_bytes)
        await redis.expire(key, 120)
        return True
    except Exception:
        return False


async def flush_telemetry_batches() -> None:
    from mcpworks_api.core.database import get_db_context
    from mcpworks_api.core.encryption import decrypt_value
    from mcpworks_api.core.redis import get_redis
    from mcpworks_api.models.namespace import Namespace

    try:
        redis = await get_redis()
        if not redis:
            return

        keys = []
        async for key in redis.scan_iter(match="telemetry:batch:*"):
            keys.append(key)

        if not keys:
            return

        async with get_db_context() as db:
            from sqlalchemy import select

            for key in keys:
                ns_id_str = (
                    key.decode().split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1]
                )

                events_raw = await redis.lrange(key, 0, 999)
                if not events_raw:
                    continue
                await redis.ltrim(key, len(events_raw), -1)

                result = await db.execute(
                    select(
                        Namespace.telemetry_webhook_url,
                        Namespace.telemetry_webhook_secret_encrypted,
                        Namespace.telemetry_webhook_secret_dek,
                        Namespace.name,
                    ).where(Namespace.id == ns_id_str)
                )
                row = result.first()
                if not row or not row.telemetry_webhook_url:
                    continue

                secret = None
                if row.telemetry_webhook_secret_encrypted and row.telemetry_webhook_secret_dek:
                    with contextlib.suppress(Exception):
                        secret = decrypt_value(
                            row.telemetry_webhook_secret_encrypted,
                            row.telemetry_webhook_secret_dek,
                        )

                events = []
                for raw in events_raw:
                    with contextlib.suppress(Exception):
                        events.append(json.loads(raw))

                if not events:
                    continue

                batch_payload = {
                    "event": "tool_call_batch",
                    "namespace": row.name,
                    "data": [e.get("data", e) for e in events],
                }
                batch_bytes = json.dumps(batch_payload).encode()

                asyncio.create_task(
                    _deliver_webhook(row.telemetry_webhook_url, batch_bytes, secret)
                )

    except Exception:
        logger.debug("telemetry_batch_flush_failed", exc_info=True)

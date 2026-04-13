"""OAuth 2.0 token management for MCP server proxy.

Supports RFC 8628 Device Authorization Flow (primary) and
Authorization Code Flow (fallback). Tokens stored with AES-256-GCM
envelope encryption, per-namespace scoping.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.encryption import decrypt_value, encrypt_value
from mcpworks_api.core.redis import get_redis_context
from mcpworks_api.models.namespace_mcp_server import NamespaceMcpServer

logger = structlog.get_logger(__name__)

REFRESH_BUFFER_SECONDS = 300
DEVICE_CODE_PREFIX = "mcp_oauth_device"
POLLING_PREFIX = "mcp_oauth_polling"
REFRESH_LOCK_PREFIX = "mcp_oauth_refresh"
REFRESH_LOCK_TTL = 30
STATE_PREFIX = "oauth_state"
STATE_TTL = 600


def _redis_key(prefix: str, namespace_id: Any, server_name: str) -> str:
    return f"{prefix}:{namespace_id}:{server_name}"


def decrypt_oauth_config(server: NamespaceMcpServer) -> dict:
    if not server.oauth_config_encrypted or not server.oauth_config_dek:
        raise ValueError(f"No OAuth config for server '{server.name}'")
    return decrypt_value(server.oauth_config_encrypted, server.oauth_config_dek)


def decrypt_oauth_tokens(server: NamespaceMcpServer) -> dict | None:
    if not server.oauth_tokens_encrypted or not server.oauth_tokens_dek:
        return None
    return decrypt_value(server.oauth_tokens_encrypted, server.oauth_tokens_dek)


def encrypt_and_store_config(server: NamespaceMcpServer, config: dict) -> None:
    ct, dek = encrypt_value(config)
    server.oauth_config_encrypted = ct
    server.oauth_config_dek = dek


def encrypt_and_store_tokens(
    server: NamespaceMcpServer, tokens: dict, expires_in: int | None = None
) -> None:
    ct, dek = encrypt_value(tokens)
    server.oauth_tokens_encrypted = ct
    server.oauth_tokens_dek = dek
    if expires_in:
        server.oauth_tokens_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    elif "expires_in" in tokens:
        server.oauth_tokens_expires_at = datetime.now(UTC) + timedelta(
            seconds=int(tokens["expires_in"])
        )


def clear_tokens(server: NamespaceMcpServer) -> None:
    server.oauth_tokens_encrypted = None
    server.oauth_tokens_dek = None
    server.oauth_tokens_expires_at = None


def get_oauth_status(server: NamespaceMcpServer) -> str:
    if server.auth_type != "oauth2":
        return "not_configured"
    if not server.oauth_config_encrypted:
        return "not_configured"
    if not server.oauth_tokens_encrypted:
        return "pending_authorization"
    if server.oauth_tokens_expires_at and server.oauth_tokens_expires_at < datetime.now(UTC):
        tokens = decrypt_oauth_tokens(server)
        if tokens and tokens.get("refresh_token"):
            return "authorized"
        return "expired"
    return "authorized"


async def initiate_device_flow(
    server: NamespaceMcpServer,
) -> dict:
    active = await get_active_device_code(server)
    if active:
        return active

    config = decrypt_oauth_config(server)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            config["device_authorization_endpoint"],
            data={
                "client_id": config["client_id"],
                "scope": " ".join(config.get("scopes", [])),
            },
        )
        resp.raise_for_status()
        data = resp.json()

    device_state = {
        "device_code": data["device_code"],
        "user_code": data["user_code"],
        "verification_uri": data.get("verification_uri") or data.get("verification_url", ""),
        "interval": data.get("interval", 5),
        "expires_in": data.get("expires_in", 600),
    }

    ttl = device_state["expires_in"]
    key = _redis_key(DEVICE_CODE_PREFIX, server.namespace_id, server.name)
    async with get_redis_context() as redis:
        await redis.set(key, json.dumps(device_state), ex=ttl)

    logger.info(
        "oauth_device_flow_initiated",
        server=server.name,
        namespace=str(server.namespace_id),
        verification_uri=device_state["verification_uri"],
    )

    return {
        "auth_required": True,
        "provider": server.name,
        "verification_uri": device_state["verification_uri"],
        "user_code": device_state["user_code"],
        "message": (
            f"Authorization required for {server.name}. "
            f"Go to {device_state['verification_uri']} and enter code "
            f"{device_state['user_code']} to grant access. "
            "The system will detect authorization automatically — just retry after approving."
        ),
        "expires_in": ttl,
        "flow": "device",
    }


async def get_active_device_code(server: NamespaceMcpServer) -> dict | None:
    key = _redis_key(DEVICE_CODE_PREFIX, server.namespace_id, server.name)
    async with get_redis_context() as redis:
        raw = await redis.get(key)
    if not raw:
        return None
    state = json.loads(raw)

    poll_key = _redis_key(POLLING_PREFIX, server.namespace_id, server.name)
    async with get_redis_context() as redis:
        is_polling = await redis.get(poll_key)

    msg_suffix = (
        " Polling for approval is active — just retry after approving."
        if is_polling
        else " Enter the code and retry."
    )
    return {
        "auth_required": True,
        "provider": server.name,
        "verification_uri": state["verification_uri"],
        "user_code": state["user_code"],
        "message": (
            f"Authorization still pending for {server.name}. "
            f"Go to {state['verification_uri']} and enter code {state['user_code']}." + msg_suffix
        ),
        "expires_in": state.get("expires_in", 600),
        "flow": "device",
    }


async def exchange_device_code(
    server: NamespaceMcpServer,
    device_code: str,
    db: AsyncSession,
) -> bool:
    config = decrypt_oauth_config(server)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            config["token_endpoint"],
            data={
                "client_id": config["client_id"],
                "client_secret": config.get("client_secret", ""),
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )

    if resp.status_code != 200:
        data = resp.json()
        error = data.get("error", "")
        if error in ("authorization_pending", "slow_down"):
            return False
        if error == "expired_token":
            await _clear_device_state(server)
            return False
        logger.warning(
            "oauth_device_exchange_error",
            server=server.name,
            error=error,
            description=data.get("error_description", ""),
        )
        return False

    tokens = resp.json()
    encrypt_and_store_tokens(server, tokens)
    await db.flush()
    await _clear_device_state(server)

    logger.info(
        "oauth_tokens_stored",
        server=server.name,
        namespace=str(server.namespace_id),
    )
    return True


async def refresh_token_if_needed(
    server: NamespaceMcpServer,
    db: AsyncSession,
) -> dict | None:
    if not server.oauth_tokens_encrypted:
        return None

    if server.oauth_tokens_expires_at and server.oauth_tokens_expires_at > datetime.now(
        UTC
    ) + timedelta(seconds=REFRESH_BUFFER_SECONDS):
        tokens = decrypt_oauth_tokens(server)
        if tokens:
            return {"Authorization": f"Bearer {tokens['access_token']}"}
        return None

    lock_key = _redis_key(REFRESH_LOCK_PREFIX, server.namespace_id, server.name)
    async with get_redis_context() as redis:
        acquired = await redis.set(lock_key, "1", nx=True, ex=REFRESH_LOCK_TTL)

    if not acquired:
        for _ in range(6):
            await _async_sleep(0.5)
            async with get_redis_context() as redis:
                still_locked = await redis.get(lock_key)
            if not still_locked:
                break
        tokens = decrypt_oauth_tokens(server)
        if tokens:
            return {"Authorization": f"Bearer {tokens['access_token']}"}
        return None

    try:
        tokens = decrypt_oauth_tokens(server)
        if not tokens or not tokens.get("refresh_token"):
            return None

        config = decrypt_oauth_config(server)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                config["token_endpoint"],
                data={
                    "client_id": config["client_id"],
                    "client_secret": config.get("client_secret", ""),
                    "grant_type": "refresh_token",
                    "refresh_token": tokens["refresh_token"],
                },
            )

        if resp.status_code != 200:
            data = resp.json()
            error = data.get("error", "")
            if error == "invalid_grant":
                clear_tokens(server)
                await db.flush()
                logger.warning("oauth_refresh_token_revoked", server=server.name)
                return None
            logger.warning("oauth_refresh_failed", server=server.name, error=error)
            return None

        new_tokens = resp.json()
        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = tokens["refresh_token"]
        encrypt_and_store_tokens(server, new_tokens)
        await db.flush()

        logger.info("oauth_token_refreshed", server=server.name)
        return {"Authorization": f"Bearer {new_tokens['access_token']}"}
    finally:
        async with get_redis_context() as redis:
            await redis.delete(lock_key)


async def get_oauth_headers(
    server: NamespaceMcpServer,
    db: AsyncSession,
) -> dict | None:
    if server.auth_type != "oauth2":
        return None

    status = get_oauth_status(server)
    if status in ("not_configured", "pending_authorization"):
        return None

    headers = await refresh_token_if_needed(server, db)
    return headers


async def initiate_auth_code_flow(
    server: NamespaceMcpServer,
    redirect_uri: str,
) -> dict:
    import secrets

    config = decrypt_oauth_config(server)
    state_token = secrets.token_urlsafe(32)
    state_data = {
        "namespace_id": str(server.namespace_id),
        "server_name": server.name,
        "csrf": state_token,
    }

    async with get_redis_context() as redis:
        await redis.set(
            f"{STATE_PREFIX}:{state_token}",
            json.dumps(state_data),
            ex=STATE_TTL,
        )

    params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(config.get("scopes", [])),
        "state": state_token,
        "access_type": "offline",
        "prompt": "consent",
    }
    from urllib.parse import urlencode

    auth_url = f"{config['auth_endpoint']}?{urlencode(params)}"

    return {
        "auth_required": True,
        "provider": server.name,
        "auth_url": auth_url,
        "message": (
            f"Authorization required for {server.name}. "
            "Open the URL in a browser to grant access, then retry."
        ),
        "expires_in": STATE_TTL,
        "flow": "authorization_code",
    }


async def exchange_auth_code(
    server: NamespaceMcpServer,
    code: str,
    redirect_uri: str,
    db: AsyncSession,
) -> bool:
    config = decrypt_oauth_config(server)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            config["token_endpoint"],
            data={
                "client_id": config["client_id"],
                "client_secret": config.get("client_secret", ""),
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )

    if resp.status_code != 200:
        logger.warning(
            "oauth_auth_code_exchange_failed",
            server=server.name,
            status=resp.status_code,
        )
        return False

    tokens = resp.json()
    encrypt_and_store_tokens(server, tokens)
    await db.flush()

    logger.info(
        "oauth_tokens_stored_via_auth_code",
        server=server.name,
        namespace=str(server.namespace_id),
    )
    return True


async def _clear_device_state(server: NamespaceMcpServer) -> None:
    async with get_redis_context() as redis:
        await redis.delete(
            _redis_key(DEVICE_CODE_PREFIX, server.namespace_id, server.name),
            _redis_key(POLLING_PREFIX, server.namespace_id, server.name),
        )


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)

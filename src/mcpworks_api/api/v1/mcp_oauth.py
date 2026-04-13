"""OAuth callback endpoint for MCP server authorization code flow (fallback)."""

import json

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from mcpworks_api.core.database import get_db_context
from mcpworks_api.core.redis import get_redis_context
from mcpworks_api.models.namespace_mcp_server import NamespaceMcpServer
from mcpworks_api.services.mcp_oauth import STATE_PREFIX

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/oauth", tags=["oauth"])

_SUCCESS_HTML = """<!DOCTYPE html>
<html><head><title>Authorization Successful</title>
<style>body{{font-family:system-ui;max-width:480px;margin:60px auto;padding:20px;text-align:center}}
h1{{color:#22c55e}}p{{color:#666;line-height:1.6}}.note{{background:#fef3c7;padding:12px;border-radius:8px;margin-top:20px;font-size:0.9em}}</style>
</head><body>
<h1>Authorization Successful</h1>
<p>Access granted for <strong>{provider}</strong>.</p>
<div class="note">You are granting this namespace access to {provider}.
All users and agents with access to this namespace can use these credentials.</div>
<p>You can close this tab and return to your AI assistant.</p>
</body></html>"""

_ERROR_HTML = """<!DOCTYPE html>
<html><head><title>Authorization Failed</title>
<style>body{{font-family:system-ui;max-width:480px;margin:60px auto;padding:20px;text-align:center}}
h1{{color:#ef4444}}p{{color:#666}}</style>
</head><body>
<h1>Authorization Failed</h1>
<p>{message}</p>
</body></html>"""


@router.get("/mcp-callback")
async def mcp_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
) -> HTMLResponse:
    async with get_redis_context() as redis:
        raw = await redis.get(f"{STATE_PREFIX}:{state}")
        if raw:
            await redis.delete(f"{STATE_PREFIX}:{state}")

    if not raw:
        return HTMLResponse(
            _ERROR_HTML.format(message="Invalid or expired authorization state. Please retry."),
            status_code=400,
        )

    state_data = json.loads(raw)
    namespace_id = state_data["namespace_id"]
    server_name = state_data["server_name"]

    async with get_db_context() as db:
        stmt = select(NamespaceMcpServer).where(
            NamespaceMcpServer.namespace_id == namespace_id,
            NamespaceMcpServer.name == server_name,
        )
        result = await db.execute(stmt)
        server = result.scalar_one_or_none()

        if not server:
            return HTMLResponse(
                _ERROR_HTML.format(message=f"MCP server '{server_name}' not found."),
                status_code=404,
            )

        from mcpworks_api.config import get_settings
        from mcpworks_api.services.mcp_oauth import exchange_auth_code

        settings = get_settings()
        redirect_uri = f"{settings.base_scheme}://api.{settings.base_domain}/v1/oauth/mcp-callback"

        success = await exchange_auth_code(server, code, redirect_uri, db)
        if not success:
            return HTMLResponse(
                _ERROR_HTML.format(message="Token exchange failed. Please retry."),
                status_code=500,
            )

    logger.info(
        "oauth_mcp_callback_success",
        namespace_id=namespace_id,
        server=server_name,
    )
    return HTMLResponse(_SUCCESS_HTML.format(provider=server_name))

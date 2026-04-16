"""MCP Server Card discovery endpoints (.well-known/mcp.json)."""

import re

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from mcpworks_api.config import get_settings
from mcpworks_api.core.database import get_db_context
from mcpworks_api.services.discovery import DiscoveryService

logger = structlog.get_logger(__name__)

router = APIRouter()

_settings = get_settings()
_domain = _settings.base_domain
_escaped = re.escape(_domain)
_ns_pattern = re.compile(r"^(?P<namespace>[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)\.create\." + _escaped)

_CACHE_HEADERS = {"Cache-Control": "public, max-age=300"}
_CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}
_RESPONSE_HEADERS = {**_CACHE_HEADERS, **_CORS_HEADERS}


@router.get("/.well-known/mcp.json")
async def well_known_mcp(request: Request) -> JSONResponse:
    host = request.headers.get("host", "").lower().split(":")[0]

    if host == f"api.{_domain}":
        return await _platform_card()

    match = _ns_pattern.match(host)
    if match:
        return await _namespace_card(match.group("namespace"))

    return JSONResponse(
        {"error": "not_found", "message": "Server card not available for this host"},
        status_code=404,
        headers=_CORS_HEADERS,
    )


async def _namespace_card(namespace_name: str) -> JSONResponse:
    try:
        async with get_db_context() as db:
            svc = DiscoveryService(db)
            card = await svc.get_namespace_card(namespace_name)
    except Exception:
        logger.exception("discovery_namespace_card_error", namespace=namespace_name)
        return JSONResponse(
            {"error": "service_unavailable", "message": "Unable to generate server card"},
            status_code=503,
            headers=_CORS_HEADERS,
        )

    if card is None:
        return JSONResponse(
            {"error": "namespace_not_found", "message": "No namespace found for this host"},
            status_code=404,
            headers=_CORS_HEADERS,
        )

    return JSONResponse(card.model_dump(), headers=_RESPONSE_HEADERS)


async def _platform_card() -> JSONResponse:
    try:
        async with get_db_context() as db:
            svc = DiscoveryService(db)
            card = await svc.get_platform_card()
    except Exception:
        logger.exception("discovery_platform_card_error")
        return JSONResponse(
            {"error": "service_unavailable", "message": "Unable to generate server card"},
            status_code=503,
            headers=_CORS_HEADERS,
        )

    return JSONResponse(card.model_dump(), headers=_RESPONSE_HEADERS)

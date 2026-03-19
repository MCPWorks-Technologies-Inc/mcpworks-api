"""Public scratchpad view serving for *.agent.mcpworks.io/view/{token}/."""

from pathlib import PurePosixPath

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import Response

from mcpworks_api.core.database import get_db_context
from mcpworks_api.services.scratchpad import ScratchpadService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["scratchpad-view"])

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".map": "application/json; charset=utf-8",
}

SCRATCHPAD_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' "
        "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net "
        "https://cdnjs.cloudflare.com; "
        "connect-src 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-cache, must-revalidate",
}

NOT_FOUND = Response(status_code=404, content="Not Found")


def _get_mime_type(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    return MIME_TYPES.get(suffix, "application/octet-stream")


@router.get("/view/{token}/{path:path}")
@router.get("/view/{token}/")
async def serve_scratchpad(
    token: str,
    request: Request,
    path: str = "index.html",
) -> Response:
    """Serve scratchpad content. Public endpoint — token IS the auth."""
    endpoint_type = getattr(request.state, "endpoint_type", None)
    if endpoint_type is not None and getattr(endpoint_type, "value", str(endpoint_type)) != "agent":
        return NOT_FOUND

    if not token or len(token) < 20:
        return NOT_FOUND

    async with get_db_context() as db:
        service = ScratchpadService(db)
        agent = await service.resolve_agent_by_token(token)

        if not agent:
            return NOT_FOUND

        host = request.headers.get("host", "").lower()
        is_local = getattr(request.state, "is_local", False)
        if not is_local:
            expected_host = f"{agent.name}.agent.mcpworks.io"
            if not host.startswith(expected_host):
                return NOT_FOUND

        file_bytes = await service.read_file(agent.id, path)

    if file_bytes is None:
        return NOT_FOUND

    headers = dict(SCRATCHPAD_HEADERS)
    if agent.scratchpad_updated_at:
        headers["X-Scratchpad-Updated"] = agent.scratchpad_updated_at.isoformat()

    mime_type = _get_mime_type(path)

    logger.debug(
        "scratchpad_serve",
        agent_id=str(agent.id),
        path=path,
        size=len(file_bytes),
    )

    return Response(
        content=file_bytes,
        media_type=mime_type,
        headers=headers,
    )

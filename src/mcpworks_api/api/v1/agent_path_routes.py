"""Path-based agent sub-routes for 015-path-based-routing.

Mounts webhook, chat, and scratchpad view handlers under
/mcp/agent/{namespace}/... for path-based routing mode.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter(prefix="/mcp/agent/{namespace}", tags=["agent-path"])


@router.post("/webhook/{path:path}")
async def webhook_path(namespace: str, path: str, request: Request) -> JSONResponse:
    from mcpworks_api.api.v1.webhooks import handle_agent_webhook

    request.state.namespace = namespace
    return await handle_agent_webhook(path, request)


@router.options("/chat/{token}")
async def chat_preflight_path(namespace: str, token: str, request: Request) -> JSONResponse:
    from mcpworks_api.api.v1.public_chat import chat_preflight

    request.state.namespace = namespace
    return await chat_preflight(token, request)


@router.post("/chat/{token}")
async def chat_path(namespace: str, token: str, request: Request) -> JSONResponse:
    from mcpworks_api.api.v1.public_chat import public_chat

    request.state.namespace = namespace
    return await public_chat(token, request)


@router.get("/view/{token}/{path:path}")
@router.get("/view/{token}/")
async def view_path(
    namespace: str,
    token: str,
    request: Request,
    path: str = "index.html",
) -> Response:
    from mcpworks_api.api.v1.scratchpad_view import serve_scratchpad

    request.state.namespace = namespace
    return await serve_scratchpad(token, request, path)


@router.post("/view/{token}/chat")
async def view_chat_path(namespace: str, token: str, request: Request) -> Response:
    from mcpworks_api.api.v1.scratchpad_view import scratchpad_chat

    request.state.namespace = namespace
    return await scratchpad_chat(token, request)

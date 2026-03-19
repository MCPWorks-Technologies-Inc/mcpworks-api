"""Public chat endpoint for agents via obfuscated URL token.

URL: POST https://{agent}.agent.mcpworks.io/chat/{token}
The token in the URL IS the authentication.
"""

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from mcpworks_api.core.database import get_db_context
from mcpworks_api.middleware.subdomain import EndpointType
from mcpworks_api.services.agent_service import AgentService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["public-chat"])

CORS_HEADERS = {
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
}


def _cors(request: Request, extra: dict | None = None) -> dict:
    origin = request.headers.get("origin", "*")
    headers = {**CORS_HEADERS, "Access-Control-Allow-Origin": origin}
    if extra:
        headers.update(extra)
    return headers


@router.options("/chat/{token}")
async def chat_preflight(token: str, request: Request) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(content={}, status_code=204, headers=_cors(request))


@router.post("/chat/{token}")
async def public_chat(token: str, request: Request) -> JSONResponse:
    endpoint_type = getattr(request.state, "endpoint_type", None)
    if endpoint_type != EndpointType.AGENT:
        return JSONResponse(
            status_code=404,
            content={"error": "Not found"},
            headers=_cors(request),
        )

    if len(token) < 20:
        return JSONResponse(
            status_code=404,
            content={"error": "Not found"},
            headers=_cors(request),
        )

    namespace = getattr(request.state, "namespace", None)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body"},
            headers=_cors(request),
        )

    message = body.get("message", "").strip()
    if not message:
        return JSONResponse(
            status_code=400,
            content={"error": "message is required"},
            headers=_cors(request),
        )

    if len(message) > 10000:
        return JSONResponse(
            status_code=400,
            content={"error": "message too long (max 10000 chars)"},
            headers=_cors(request),
        )

    async with get_db_context() as db:
        service = AgentService(db)
        agent = await service.resolve_agent_by_chat_token(token)

        if not agent:
            return JSONResponse(
                status_code=404,
                content={"error": "Not found"},
                headers=_cors(request),
            )

        if namespace and agent.name != namespace:
            return JSONResponse(
                status_code=404,
                content={"error": "Not found"},
                headers=_cors(request),
            )

        if agent.status != "running":
            return JSONResponse(
                status_code=503,
                content={"error": "Agent is not running"},
                headers=_cors(request),
            )

        if not agent.ai_engine or not agent.ai_api_key_encrypted:
            return JSONResponse(
                status_code=503,
                content={"error": "Agent has no AI engine configured"},
                headers=_cors(request),
            )

        from sqlalchemy import select

        from mcpworks_api.models.account import Account

        account_result = await db.execute(select(Account).where(Account.id == agent.account_id))
        account = account_result.scalar_one_or_none()

        logger.info(
            "public_chat_request",
            agent_name=agent.name,
            message_length=len(message),
            origin=request.headers.get("origin"),
        )

        try:
            response = await service.chat_with_agent(
                account_id=agent.account_id,
                agent_name=agent.name,
                message=message,
                account=account,
            )
        except Exception:
            logger.exception("public_chat_error", agent_name=agent.name)
            return JSONResponse(
                status_code=500,
                content={"error": "Chat failed"},
                headers=_cors(request),
            )

    return JSONResponse(
        content={"response": response},
        headers=_cors(request),
    )

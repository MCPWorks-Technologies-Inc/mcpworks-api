"""Internal API proxy endpoint — routes sandbox calls to registered REST APIs (019)."""

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.api_proxy import proxy_api_call
from mcpworks_api.core.exec_token_registry import resolve_execution
from mcpworks_api.dependencies import get_db
from mcpworks_api.schemas.api_server import ApiProxyRequest

router = APIRouter(tags=["internal"])


@router.post("/v1/internal/api-proxy")
async def api_proxy(
    body: ApiProxyRequest,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    token = authorization.removeprefix("Bearer ").strip()
    ctx = resolve_execution(token)
    if not ctx:
        return JSONResponse(
            status_code=403,
            content={
                "error": "auth_error",
                "reason": "invalid or expired bridge key",
                "action": "",
            },
        )

    result = await proxy_api_call(
        ctx=ctx,
        server_name=body.server,
        operation_id=body.operation_id,
        path=body.path,
        query=body.query,
        body=body.body,
        headers=body.headers,
        db=db,
    )

    if result.error:
        return JSONResponse(
            status_code=502,
            content={"error": result.error, "reason": result.reason, "action": result.action},
        )

    payload: dict = {
        "status_code": result.status_code,
        "truncated": result.truncated,
        "content_type": result.content_type,
    }
    if result.json_body is not None:
        payload["json"] = result.json_body
    if result.text is not None:
        payload["text"] = result.text
    return JSONResponse(content=payload)

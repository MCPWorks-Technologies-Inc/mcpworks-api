"""Internal MCP proxy endpoint — routes sandbox calls to external MCP servers."""

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.exec_token_registry import resolve_execution
from mcpworks_api.core.mcp_proxy import proxy_mcp_call
from mcpworks_api.dependencies import get_db
from mcpworks_api.schemas.mcp_server import ProxyRequest

router = APIRouter(tags=["internal"])


@router.post("/v1/internal/mcp-proxy")
async def mcp_proxy(
    body: ProxyRequest,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    token = authorization.removeprefix("Bearer ").strip()
    ctx = resolve_execution(token)
    if not ctx:
        return JSONResponse(
            status_code=403,
            content={"error": "Invalid or expired bridge key", "error_type": "AuthError"},
        )

    result = await proxy_mcp_call(
        ctx=ctx,
        server_name=body.server,
        tool_name=body.tool,
        arguments=body.arguments,
        db=db,
    )

    if result.error:
        return JSONResponse(
            status_code=502,
            content={
                "error": result.error,
                "error_type": result.error_type,
            },
        )

    return JSONResponse(
        content={
            "result": result.result,
            "truncated": result.truncated,
        }
    )

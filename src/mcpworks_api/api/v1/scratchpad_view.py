"""Public scratchpad view serving for *.agent.{BASE_DOMAIN}/view/{token}/."""

from pathlib import PurePosixPath

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from mcpworks_api import url_builder
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
GONE = Response(status_code=410, content="Expired")


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

        if service.is_expired(agent):
            return GONE

        host = request.headers.get("host", "").lower()
        is_local = getattr(request.state, "is_local", False)
        if not is_local:
            expected_host = url_builder.agent_url(agent.name).split("://", 1)[1]
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

    if mime_type.startswith("text/html") and agent.chat_token:
        file_bytes = _inject_chat_widget(file_bytes)

    return Response(
        content=file_bytes,
        media_type=mime_type,
        headers=headers,
    )


@router.post("/view/{token}/chat")
async def scratchpad_chat(token: str, request: Request) -> Response:
    """Proxied chat endpoint — token is the scratchpad token, not the chat token.

    The chat_token is never exposed to the client. The server resolves the
    agent from the scratchpad_token, verifies chat is enabled, and calls
    chat_with_agent internally with public_only=True.
    """
    from sqlalchemy import select

    from mcpworks_api.models.account import Account
    from mcpworks_api.services.agent_service import AgentService

    endpoint_type = getattr(request.state, "endpoint_type", None)
    if endpoint_type is not None and getattr(endpoint_type, "value", str(endpoint_type)) != "agent":
        return JSONResponse(status_code=404, content={"error": "Not found"})

    if not token or len(token) < 20:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})

    message = body.get("message", "").strip()
    if not message:
        return JSONResponse(status_code=400, content={"error": "message is required"})
    if len(message) > 10000:
        return JSONResponse(
            status_code=400, content={"error": "message too long (max 10000 chars)"}
        )

    async with get_db_context() as db:
        scratchpad_service = ScratchpadService(db)
        agent = await scratchpad_service.resolve_agent_by_token(token)

        if not agent:
            return JSONResponse(status_code=404, content={"error": "Not found"})
        if not agent.chat_token:
            return JSONResponse(
                status_code=403, content={"error": "Chat not enabled for this agent"}
            )
        if agent.status != "running":
            return JSONResponse(status_code=503, content={"error": "Agent is not running"})
        if not agent.ai_engine or not agent.ai_api_key_encrypted:
            return JSONResponse(status_code=503, content={"error": "Agent has no AI configured"})

        account_id = agent.account_id
        agent_name = agent.name

    logger.info(
        "scratchpad_chat_request",
        agent_name=agent_name,
        message_length=len(message),
    )

    async with get_db_context() as db:
        from sqlalchemy.orm import selectinload

        account_result = await db.execute(
            select(Account).where(Account.id == account_id).options(selectinload(Account.user))
        )
        account = account_result.scalar_one_or_none()

        agent_service = AgentService(db)
        try:
            response = await agent_service.chat_with_agent(
                account_id=account_id,
                agent_name=agent_name,
                message=message,
                account=account,
                public_only=True,
            )
        except Exception:
            logger.exception("scratchpad_chat_error", agent_name=agent_name)
            return JSONResponse(status_code=500, content={"error": "Chat failed"})

    return JSONResponse(content={"response": response})


CHAT_WIDGET_JS = """
<div id="mcpw-chat" style="position:fixed;bottom:20px;right:20px;z-index:99999;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<button id="mcpw-toggle" style="width:48px;height:48px;border-radius:50%;background:#1a1a2e;color:#fff;border:none;cursor:pointer;font-size:20px;box-shadow:0 4px 12px rgba(0,0,0,0.3);display:flex;align-items:center;justify-content:center" title="Chat with agent">💬</button>
<div id="mcpw-panel" style="display:none;width:380px;max-height:500px;background:#1a1a2e;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,0.4);overflow:hidden;margin-bottom:8px;flex-direction:column">
<div style="padding:12px 16px;background:#16213e;color:#e2e8f0;font-weight:600;font-size:14px;display:flex;justify-content:space-between;align-items:center"><span>Agent Chat</span><button onclick="document.getElementById('mcpw-panel').style.display='none'" style="background:none;border:none;color:#94a3b8;cursor:pointer;font-size:18px">×</button></div>
<div id="mcpw-msgs" style="flex:1;overflow-y:auto;padding:12px;min-height:200px;max-height:350px"></div>
<div style="padding:8px 12px;border-top:1px solid #2d3748;display:flex;gap:8px">
<input id="mcpw-input" type="text" placeholder="Ask the agent..." style="flex:1;padding:8px 12px;border:1px solid #374151;border-radius:8px;background:#0f172a;color:#e2e8f0;font-size:14px;outline:none" />
<button id="mcpw-send" style="padding:8px 16px;background:#3b82f6;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:500">Send</button>
</div></div></div>
<script>
(function(){
var panel=document.getElementById('mcpw-panel'),msgs=document.getElementById('mcpw-msgs'),
input=document.getElementById('mcpw-input'),send=document.getElementById('mcpw-send'),
toggle=document.getElementById('mcpw-toggle');
toggle.onclick=function(){panel.style.display=panel.style.display==='none'?'flex':'none';if(panel.style.display==='flex')input.focus()};
function addMsg(text,isUser){
var d=document.createElement('div');
d.style.cssText='margin:6px 0;padding:8px 12px;border-radius:8px;font-size:13px;line-height:1.5;max-width:85%;word-wrap:break-word;white-space:pre-wrap;'
+(isUser?'background:#3b82f6;color:#fff;margin-left:auto;':'background:#1e293b;color:#e2e8f0;');
d.textContent=text;msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight}
async function doSend(){
var m=input.value.trim();if(!m)return;input.value='';addMsg(m,true);
send.disabled=true;send.textContent='...';
try{var r=await fetch('./chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:m})});
var j=await r.json();addMsg(j.response||j.error||'No response',!j.response)}
catch(e){addMsg('Error: '+e.message,false)}
send.disabled=false;send.textContent='Send';input.focus()}
send.onclick=doSend;input.onkeydown=function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();doSend()}}
})();
</script>
"""


def _inject_chat_widget(html_bytes: bytes) -> bytes:
    """Inject the chat widget into HTML content just before </body>."""
    html = html_bytes.decode("utf-8", errors="replace")
    lower = html.lower()
    idx = lower.rfind("</body>")
    if idx >= 0:
        html = html[:idx] + CHAT_WIDGET_JS + html[idx:]
    else:
        html += CHAT_WIDGET_JS
    return html.encode("utf-8")

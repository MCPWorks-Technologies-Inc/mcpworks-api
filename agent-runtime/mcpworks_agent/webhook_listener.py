"""FastAPI app for receiving forwarded webhooks within the agent container.

Receives webhook payloads forwarded from the MCPWorks API and dispatches
them to the configured handler function for the agent.
"""

import hashlib
import hmac
import json
import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

logger = logging.getLogger(__name__)

AGENT_ID = os.environ.get("AGENT_ID", "")
AGENT_NAME = os.environ.get("AGENT_NAME", "")
MCPWORKS_API_URL = os.environ.get("MCPWORKS_API_URL", "http://mcpworks-api:8000")
MCPWORKS_API_KEY = os.environ.get("MCPWORKS_AGENT_API_KEY", "")

app = FastAPI(title="MCPWorks Agent Webhook Listener", docs_url=None, redoc_url=None)


async def _call_handler_function(function_name: str, payload: Any) -> dict:
    """Execute a handler function via the MCPWorks run endpoint."""
    parts = function_name.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid function_name: {function_name}; expected service.function")
    service_name, fn_name = parts

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{MCPWORKS_API_URL}/v1/namespaces/{AGENT_NAME}/{service_name}/{fn_name}",
            headers={"Authorization": f"Bearer {MCPWORKS_API_KEY}"},
            json={"payload": payload},
        )
        response.raise_for_status()
        return response.json()


@app.post("/webhook/{path:path}")
async def receive_webhook(
    path: str,
    request: Request,
    x_mcpworks_webhook_secret: str | None = Header(None),
    x_mcpworks_handler: str | None = Header(None),
    x_mcpworks_signature: str | None = Header(None),
) -> dict:
    """Receive a forwarded webhook and dispatch to the handler function.

    Headers:
        X-MCPWorks-Webhook-Secret: The secret hash for HMAC verification (optional)
        X-MCPWorks-Handler: The handler function name (service.function)
        X-MCPWorks-Signature: HMAC-SHA256 signature of the body (optional)
    """
    body = await request.body()

    if x_mcpworks_webhook_secret and x_mcpworks_signature:
        expected = hmac.new(
            x_mcpworks_webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()  # type: ignore[attr-defined]
        if not hmac.compare_digest(expected, x_mcpworks_signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if not x_mcpworks_handler:
        raise HTTPException(status_code=400, detail="X-MCPWorks-Handler header required")

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = body.decode("utf-8", errors="replace")

    try:
        result = await _call_handler_function(x_mcpworks_handler, payload)
        logger.info(
            "webhook_dispatched",
            path=path,
            handler=x_mcpworks_handler,
        )
        return {"status": "ok", "path": path, "result": result}
    except Exception as e:
        logger.error("webhook_handler_failed", path=path, handler=x_mcpworks_handler, error=str(e))
        raise HTTPException(status_code=500, detail=f"Handler execution failed: {e}")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "agent_id": AGENT_ID, "agent_name": AGENT_NAME}

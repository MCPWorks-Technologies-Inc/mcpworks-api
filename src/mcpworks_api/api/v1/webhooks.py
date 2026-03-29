"""Webhook ingress handler for *.agent.{BASE_DOMAIN}/webhook/* requests."""

import hashlib
import hmac
import json
import uuid as uuid_mod
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from mcpworks_api.backends import get_backend
from mcpworks_api.core.database import get_db_context
from mcpworks_api.models.account import Account
from mcpworks_api.models.agent import Agent, AgentReplica, AgentRun
from mcpworks_api.services.agent_service import AgentService
from mcpworks_api.services.function import FunctionService
from mcpworks_api.tasks.orchestrator import run_orchestration

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/webhook/{path:path}")
async def handle_agent_webhook(path: str, request: Request) -> JSONResponse:
    """Handle incoming webhook for agent endpoints.

    URL: https://{agent-name}.agent.{BASE_DOMAIN}/webhook/{path}
    """
    namespace = getattr(request.state, "namespace", None)
    if not namespace:
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    try:
        body_bytes = await request.body()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Failed to read request body"})

    async with get_db_context() as db:
        service = AgentService(db)
        webhook = await service.resolve_webhook(namespace, path)

        if not webhook:
            return JSONResponse(
                status_code=404, content={"detail": f"Webhook path '/{path}' not found"}
            )

        agent_result = await db.execute(
            __import__("sqlalchemy").select(Agent).where(Agent.id == webhook.agent_id)
        )
        agent = agent_result.scalar_one_or_none()
        if not agent or agent.status not in ("running", "degraded"):
            return JSONResponse(status_code=503, content={"detail": "Agent is not running"})

        replicas_result = await db.execute(
            __import__("sqlalchemy")
            .select(AgentReplica)
            .where(
                AgentReplica.agent_id == agent.id,
                AgentReplica.status == "running",
            )
        )
        _ = list(replicas_result.scalars())

        if webhook.secret_hash:
            signature = request.headers.get("X-Webhook-Signature", "")
            expected = hashlib.sha256(body_bytes).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return JSONResponse(
                    status_code=401, content={"detail": "Invalid webhook signature"}
                )

        try:
            payload = json.loads(body_bytes) if body_bytes else {}
        except json.JSONDecodeError:
            payload = {"raw": body_bytes.decode("utf-8", errors="replace")[:4000]}

        account_result = await db.execute(
            __import__("sqlalchemy").select(Account).where(Account.id == agent.account_id)
        )
        account = account_result.scalar_one_or_none()
        if not account:
            return JSONResponse(status_code=500, content={"detail": "Account not found"})

        orch_mode = webhook.orchestration_mode or "direct"
        tier = account.user.effective_tier if account.user else "pro-agent"

    if orch_mode == "procedure":
        procedure_name = getattr(webhook, "procedure_name", None)
        if not procedure_name:
            return JSONResponse(
                status_code=422, content={"detail": "procedure_name required for procedure mode"}
            )
        if not agent.ai_engine:
            return JSONResponse(
                status_code=422, content={"detail": "Agent needs AI engine for procedure mode"}
            )

        svc_name = (
            webhook.handler_function_name.split(".")[0]
            if "." in webhook.handler_function_name
            else "default"
        )

        from mcpworks_api.tasks.orchestrator import run_procedure_orchestration

        proc_result = await run_procedure_orchestration(
            agent=agent,
            procedure_name=procedure_name,
            service_name=svc_name,
            trigger_type="webhook",
            account=account,
            tier=tier,
            input_context={"webhook_path": path, "payload": payload},
        )
        return JSONResponse(
            content={
                "status": "completed" if proc_result.success else "failed",
                "procedure": procedure_name,
                "steps_completed": len(proc_result.functions_called),
                "error": proc_result.error,
            }
        )

    if orch_mode != "direct" and not agent.ai_engine:
        logger.warning("webhook_ai_fallback_direct", agent_name=namespace, path=path)
        orch_mode = "direct"

    if orch_mode == "direct":
        result = await _execute_webhook_function_direct(webhook, agent, account, payload)
        return JSONResponse(content=result)

    if orch_mode == "run_then_reason":
        direct_result = await _execute_webhook_function_direct(webhook, agent, account, payload)
        trigger_context = (
            f"Webhook received on /{path}.\n"
            f"Handler function {webhook.handler_function_name} executed.\n"
            f"Output: {json.dumps(direct_result)[:2000]}"
        )
    else:
        trigger_context = (
            f"Webhook received on /{path}.\n"
            f"Payload: {json.dumps(payload)[:2000]}\n"
            f"Decide what actions to take."
        )

    orch_result = await run_orchestration(
        agent=agent,
        trigger_type="webhook",
        trigger_context=trigger_context,
        trigger_data={"path": path, "payload": payload},
        tier=tier,
        account=account,
    )

    return JSONResponse(
        content={
            "status": "completed" if orch_result.success else "failed",
            "response": orch_result.final_text[:1000] if orch_result.final_text else None,
            "functions_called": orch_result.functions_called,
            "iterations": orch_result.iterations,
        }
    )


async def _execute_webhook_function_direct(
    webhook: object,
    agent: Agent,
    account: Account,
    payload: dict,
) -> dict:
    """Execute a webhook's handler function directly."""
    function_name = webhook.handler_function_name
    if "." not in function_name:
        return {"error": f"Invalid function name format: {function_name}"}

    service_name, fn_name = function_name.split(".", 1)

    async with get_db_context() as db:
        run = AgentRun(
            agent_id=agent.id,
            trigger_type="webhook",
            trigger_detail=f"webhook:{webhook.path}",
            function_name=function_name,
            status="running",
            started_at=datetime.now(UTC),
        )
        db.add(run)
        await db.flush()
        function_service = FunctionService(db)
        try:
            _, version = await function_service.get_for_execution(
                namespace_id=agent.namespace_id,
                service_name=service_name,
                function_name=fn_name,
            )
        except Exception as e:
            run.status = "failed"
            run.error = str(e)[:1000]
            run.completed_at = datetime.now(UTC)
            return {"error": str(e)}

        backend = get_backend(version.backend)
        if not backend:
            run.status = "failed"
            run.error = f"Backend not available: {version.backend}"
            run.completed_at = datetime.now(UTC)
            return {"error": f"Backend not available: {version.backend}"}

        from mcpworks_api.services.agent_service import AgentService

        agent_service = AgentService(db)
        agent_state = await agent_service.get_all_state(agent.id)
        context = {"state": agent_state}

        execution_id = str(uuid_mod.uuid4())
        start_time = datetime.now(UTC)

        try:
            result = await backend.execute(
                code=version.code,
                config=version.config,
                input_data=payload,
                account=account,
                execution_id=execution_id,
                context=context,
                namespace=agent.name,
            )
        except Exception as e:
            run.status = "failed"
            run.error = str(e)[:1000]
            run.completed_at = datetime.now(UTC)
            return {"error": str(e)}

        duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        if result.success:
            run.status = "completed"
            run.duration_ms = duration_ms
            run.result_summary = str(result.output)[:1000] if result.output else None
            run.completed_at = datetime.now(UTC)
            return {"status": "ok", "output": result.output}
        else:
            run.status = "failed"
            run.duration_ms = duration_ms
            run.error = (result.error or "Unknown error")[:1000]
            run.completed_at = datetime.now(UTC)
            return {"error": result.error or "Unknown error"}

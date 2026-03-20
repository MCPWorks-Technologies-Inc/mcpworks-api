"""In-process agent schedule executor.

Runs as a background task in the API server lifespan. Polls the database
for enabled schedules whose next_run_at has passed, executes the target
function via the sandbox backend, records AgentRun results, and applies
failure policies.

This replaces the per-agent-container scheduler for Phase 1 — all agents
share a single scheduler loop in the API process.
"""

import asyncio
import uuid as uuid_mod
from datetime import UTC, datetime, timedelta

import structlog
from croniter import croniter
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mcpworks_api.backends import get_backend
from mcpworks_api.core.database import get_db_context
from mcpworks_api.models.account import Account
from mcpworks_api.models.agent import Agent, AgentRun, AgentSchedule
from mcpworks_api.models.namespace import Namespace
from mcpworks_api.services.agent_service import AgentService
from mcpworks_api.services.function import FunctionService

logger = structlog.get_logger(__name__)

POLL_INTERVAL_SECONDS = 30
MAX_CONCURRENT_EXECUTIONS = 5


def _compute_next_run(cron_expression: str, timezone: str = "UTC") -> datetime:
    """Compute the next run time from a cron expression in the given timezone."""
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(timezone)
    except (KeyError, Exception):
        tz = ZoneInfo("UTC")
    now_local = datetime.now(tz)
    cron = croniter(cron_expression, now_local)
    next_local = cron.get_next(datetime)
    if next_local.tzinfo is None:
        next_local = next_local.replace(tzinfo=tz)
    return next_local.astimezone(UTC).replace(tzinfo=UTC)


async def _get_schedule_account(agent: Agent, db: AsyncSession) -> Account | None:
    """Load the account for a scheduled agent execution."""
    result = await db.execute(
        select(Account).where(Account.id == agent.account_id).options(selectinload(Account.user))
    )
    return result.scalar_one_or_none()


async def _execute_function_direct(
    schedule: AgentSchedule,
    agent: Agent,
) -> str | None:
    """Execute a scheduled function directly. Returns output string or None."""
    function_name = schedule.function_name
    schedule_id = str(schedule.id)

    if "." not in function_name:
        logger.error(
            "schedule_invalid_function_name",
            schedule_id=schedule_id,
            function_name=function_name,
        )
        return None

    service_name, fn_name = function_name.split(".", 1)

    async with get_db_context() as db:
        run = AgentRun(
            agent_id=agent.id,
            trigger_type="cron",
            trigger_detail=f"schedule:{schedule_id}",
            function_name=function_name,
            status="running",
            started_at=datetime.now(UTC),
        )
        db.add(run)
        await db.flush()
        run_id = run.id

        account = await _get_schedule_account(agent, db)
        if not account:
            logger.error("schedule_account_not_found", agent_id=str(agent.id))
            return None

        namespace_result = await db.execute(
            select(Namespace).where(
                Namespace.name == agent.name,
                Namespace.account_id == account.id,
            )
        )
        namespace = namespace_result.scalar_one_or_none()
        if not namespace:
            logger.error(
                "schedule_namespace_not_found",
                agent_name=agent.name,
                account_id=str(account.id),
            )
            return None

        function_service = FunctionService(db)
        try:
            function, version = await function_service.get_for_execution(
                namespace_id=namespace.id,
                service_name=service_name,
                function_name=fn_name,
            )
        except Exception as e:
            logger.error(
                "schedule_function_not_found",
                schedule_id=schedule_id,
                function_name=function_name,
                error=str(e),
            )
            await _record_failure(db, run_id, schedule, str(e))
            return None

        backend = get_backend(version.backend)
        if not backend:
            await _record_failure(db, run_id, schedule, f"Backend not available: {version.backend}")
            return None

        agent_service = AgentService(db)
        agent_state = await agent_service.get_all_state(agent.id)
        context = {"state": agent_state}

        execution_id = str(uuid_mod.uuid4())
        start_time = datetime.now(UTC)

        try:
            result = await backend.execute(
                code=version.code,
                config=version.config,
                input_data={},
                account=account,
                execution_id=execution_id,
                context=context,
            )
        except Exception as e:
            await _record_failure(db, run_id, schedule, str(e))
            return None

        duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        if result.success:
            output_str = str(result.output)[:2000] if result.output else None
            await db.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id)
                .values(
                    status="completed",
                    completed_at=datetime.now(UTC),
                    duration_ms=duration_ms,
                    result_summary=output_str[:1000] if output_str else None,
                )
            )
            await db.execute(
                update(AgentSchedule)
                .where(AgentSchedule.id == schedule.id)
                .values(
                    consecutive_failures=0,
                    last_run_at=datetime.now(UTC),
                    next_run_at=_compute_next_run(schedule.cron_expression, schedule.timezone),
                )
            )
            logger.info(
                "schedule_executed",
                schedule_id=schedule_id,
                function=function_name,
                duration_ms=duration_ms,
            )
            return output_str
        else:
            await _record_failure(
                db, run_id, schedule, result.error or "Unknown error", duration_ms
            )
            return None


async def _execute_scheduled_function(
    schedule: AgentSchedule,
    agent: Agent,
) -> None:
    """Execute a single scheduled function, respecting orchestration_mode."""
    from mcpworks_api.tasks.orchestrator import run_orchestration

    orch_mode = getattr(schedule, "orchestration_mode", "direct") or "direct"

    if orch_mode != "direct" and not agent.ai_engine:
        logger.warning(
            "schedule_ai_fallback_direct",
            schedule_id=str(schedule.id),
            reason="no_ai_configured",
        )
        orch_mode = "direct"

    if orch_mode == "direct":
        await _execute_function_direct(schedule, agent)
        return

    async with get_db_context() as db:
        account = await _get_schedule_account(agent, db)
    if not account:
        logger.error("schedule_account_not_found", agent_id=str(agent.id))
        return

    tier = account.user.effective_tier if account.user else "pro-agent"

    if orch_mode == "run_then_reason":
        output = await _execute_function_direct(schedule, agent)
        trigger_context = (
            f"Scheduled execution of {schedule.function_name} completed.\n"
            f"Output: {output or '(no output)'}"
        )
    else:
        trigger_context = (
            f"Scheduled trigger for function {schedule.function_name}. Decide what actions to take."
        )

    orch_result = await run_orchestration(
        agent=agent,
        trigger_type="cron",
        trigger_context=trigger_context,
        trigger_data={"schedule_id": str(schedule.id), "function_name": schedule.function_name},
        tier=tier,
        account=account,
    )

    async with get_db_context() as db:
        await db.execute(
            update(AgentSchedule)
            .where(AgentSchedule.id == schedule.id)
            .values(
                consecutive_failures=0
                if orch_result.success
                else schedule.consecutive_failures + 1,
                last_run_at=datetime.now(UTC),
                next_run_at=_compute_next_run(schedule.cron_expression, schedule.timezone),
            )
        )

    logger.info(
        "schedule_orchestration_complete",
        schedule_id=str(schedule.id),
        mode=orch_mode,
        success=orch_result.success,
        iterations=orch_result.iterations,
        functions_called=len(orch_result.functions_called),
    )


async def _record_failure(
    db: AsyncSession,
    run_id: uuid_mod.UUID,
    schedule: AgentSchedule,
    error: str,
    duration_ms: int | None = None,
) -> None:
    """Record a failed execution and apply failure policy."""
    await db.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id)
        .values(
            status="failed",
            completed_at=datetime.now(UTC),
            duration_ms=duration_ms,
            error=error[:1000],
        )
    )

    new_failures = schedule.consecutive_failures + 1
    values: dict = {
        "consecutive_failures": new_failures,
        "last_run_at": datetime.now(UTC),
        "next_run_at": _compute_next_run(schedule.cron_expression, schedule.timezone),
    }

    policy = schedule.failure_policy or {"strategy": "continue"}
    if isinstance(policy, str):
        import json as json_mod

        try:
            policy = json_mod.loads(policy)
        except (json_mod.JSONDecodeError, TypeError):
            policy = {"strategy": "continue"}
    strategy = policy.get("strategy", "continue")

    if strategy == "auto_disable":
        max_failures = policy.get("max_failures", 3)
        if new_failures >= max_failures:
            values["enabled"] = False
            logger.warning(
                "schedule_auto_disabled",
                schedule_id=str(schedule.id),
                consecutive_failures=new_failures,
            )

    await db.execute(update(AgentSchedule).where(AgentSchedule.id == schedule.id).values(**values))

    logger.error(
        "schedule_execution_failed",
        schedule_id=str(schedule.id),
        function=schedule.function_name,
        error=error[:200],
        consecutive_failures=new_failures,
    )


async def _execute_heartbeat(agent: Agent) -> None:
    """Execute a heartbeat tick — AI autonomy loop with no specific function."""
    from mcpworks_api.tasks.orchestrator import run_orchestration

    if not agent.ai_engine:
        logger.warning("heartbeat_no_ai", agent_name=agent.name)
        return

    async with get_db_context() as db:
        account = await _get_schedule_account(agent, db)
    if not account:
        logger.error("heartbeat_account_not_found", agent_id=str(agent.id))
        return

    tier = account.user.effective_tier if account.user else "pro-agent"

    async with get_db_context() as db:
        agent_service = AgentService(db)
        agent_state = await agent_service.get_all_state(agent.id)

    from mcpworks_api.core.conversation_memory import load_history

    soul = agent_state.get("__soul__", "")
    goals = agent_state.get("__goals__", "")
    instructions = agent_state.get("__heartbeat_instructions__", "")
    summary, _ = load_history(agent_state)

    trigger_context = "Heartbeat tick. You are waking up on your configured interval.\n"
    if soul:
        trigger_context += f"\nYour identity:\n{soul}\n"
    if goals:
        trigger_context += f"\nYour current goals:\n{goals}\n"
    if instructions:
        trigger_context += f"\nYour instructions for this heartbeat:\n{instructions}\n"
    if summary:
        trigger_context += f"\nRecent conversation context:\n{summary}\n"
    trigger_context += (
        "\nReview your state and instructions, then decide what actions to take. "
        "You can update __heartbeat_instructions__ via set_state to change "
        "what you do on your next heartbeat. "
        "If nothing needs doing, respond briefly that all is well."
    )

    orch_result = await run_orchestration(
        agent=agent,
        trigger_type="heartbeat",
        trigger_context=trigger_context,
        trigger_data={"interval": agent.heartbeat_interval},
        tier=tier,
        account=account,
    )

    async with get_db_context() as db:
        next_at = datetime.now(UTC) + timedelta(seconds=agent.heartbeat_interval or 300)
        await db.execute(
            update(Agent).where(Agent.id == agent.id).values(heartbeat_next_at=next_at)
        )

    logger.info(
        "heartbeat_complete",
        agent_name=agent.name,
        success=orch_result.success,
        iterations=orch_result.iterations,
        functions_called=len(orch_result.functions_called),
    )


async def _poll_and_execute() -> int:
    """Poll for due schedules and heartbeats, execute them. Returns count dispatched."""
    now = datetime.now(UTC)
    executed = 0

    async with get_db_context() as db:
        result = await db.execute(
            select(AgentSchedule)
            .join(Agent, AgentSchedule.agent_id == Agent.id)
            .where(
                AgentSchedule.enabled.is_(True),
                Agent.status == "running",
                Agent.enabled.is_(True),
            )
            .options(selectinload(AgentSchedule.agent))
        )
        schedules = list(result.scalars().all())

        heartbeat_result = await db.execute(
            select(Agent).where(
                Agent.status == "running",
                Agent.enabled.is_(True),
                Agent.heartbeat_enabled.is_(True),
                Agent.heartbeat_interval.isnot(None),
                Agent.ai_engine.isnot(None),
            )
        )
        heartbeat_agents = list(heartbeat_result.scalars().all())

    due_schedules = []
    for schedule in schedules:
        if schedule.next_run_at is None or schedule.next_run_at <= now:
            due_schedules.append(schedule)

    due_heartbeats = []
    for agent in heartbeat_agents:
        if agent.heartbeat_next_at is None or agent.heartbeat_next_at <= now:
            due_heartbeats.append(agent)

    if not due_schedules and not due_heartbeats:
        return 0

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXECUTIONS)

    async def _run_schedule(sched: AgentSchedule) -> None:
        async with semaphore:
            try:
                await _execute_scheduled_function(sched, sched.agent)
            except Exception:
                logger.exception(
                    "schedule_execution_error",
                    schedule_id=str(sched.id),
                )

    async def _run_heartbeat(agent: Agent) -> None:
        async with semaphore:
            try:
                await _execute_heartbeat(agent)
            except Exception:
                logger.exception(
                    "heartbeat_execution_error",
                    agent_name=agent.name,
                )

    tasks = [asyncio.create_task(_run_schedule(s)) for s in due_schedules]
    tasks += [asyncio.create_task(_run_heartbeat(a)) for a in due_heartbeats]
    await asyncio.gather(*tasks, return_exceptions=True)
    executed = len(due_schedules) + len(due_heartbeats)

    return executed


async def _initialize_next_run_times() -> None:
    """Recalculate next_run_at for all enabled schedules on startup."""
    async with get_db_context() as db:
        result = await db.execute(select(AgentSchedule).where(AgentSchedule.enabled.is_(True)))
        schedules = list(result.scalars().all())

        for schedule in schedules:
            try:
                next_run = _compute_next_run(schedule.cron_expression, schedule.timezone)
                await db.execute(
                    update(AgentSchedule)
                    .where(AgentSchedule.id == schedule.id)
                    .values(next_run_at=next_run)
                )
            except Exception:
                logger.exception(
                    "schedule_init_failed",
                    schedule_id=str(schedule.id),
                    cron=schedule.cron_expression,
                )


ANOMALY_DETECTION_INTERVAL = 300
ANOMALY_DETECTION_COUNTER = {"ticks": 0}


async def run_scheduler_loop() -> None:
    """Main scheduler loop — runs until cancelled."""
    logger.info("scheduler_starting", poll_interval=POLL_INTERVAL_SECONDS)

    await _initialize_next_run_times()

    while True:
        try:
            count = await _poll_and_execute()
            if count > 0:
                logger.info("scheduler_poll_complete", executed=count)
        except Exception:
            logger.exception("scheduler_poll_error")

        ANOMALY_DETECTION_COUNTER["ticks"] += POLL_INTERVAL_SECONDS
        if ANOMALY_DETECTION_COUNTER["ticks"] >= ANOMALY_DETECTION_INTERVAL:
            ANOMALY_DETECTION_COUNTER["ticks"] = 0
            try:
                from mcpworks_api.tasks.anomaly_detector import detect_anomalies

                await detect_anomalies()
            except Exception:
                logger.exception("anomaly_detection_error")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

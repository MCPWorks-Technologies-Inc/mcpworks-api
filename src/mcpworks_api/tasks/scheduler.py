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
from datetime import UTC, datetime

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
from mcpworks_api.services.function import FunctionService

logger = structlog.get_logger(__name__)

POLL_INTERVAL_SECONDS = 30
MAX_CONCURRENT_EXECUTIONS = 5


def _compute_next_run(cron_expression: str, _timezone: str = "UTC") -> datetime:
    """Compute the next run time from a cron expression."""
    now = datetime.now(UTC)
    cron = croniter(cron_expression, now)
    return cron.get_next(datetime).replace(tzinfo=UTC)


async def _execute_scheduled_function(
    schedule: AgentSchedule,
    agent: Agent,
) -> None:
    """Execute a single scheduled function and record the result."""
    function_name = schedule.function_name
    schedule_id = str(schedule.id)

    if "." not in function_name:
        logger.error(
            "schedule_invalid_function_name",
            schedule_id=schedule_id,
            function_name=function_name,
        )
        return

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

        account_result = await db.execute(
            select(Account)
            .where(Account.id == agent.account_id)
            .options(selectinload(Account.user))
        )
        account = account_result.scalar_one_or_none()
        if not account:
            logger.error("schedule_account_not_found", agent_id=str(agent.id))
            return

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
            return

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
            return

        backend = get_backend(version.backend)
        if not backend:
            await _record_failure(db, run_id, schedule, f"Backend not available: {version.backend}")
            return

        execution_id = str(uuid_mod.uuid4())
        start_time = datetime.now(UTC)

        try:
            result = await backend.execute(
                code=version.code,
                config=version.config,
                input_data={},
                account=account,
                execution_id=execution_id,
            )
        except Exception as e:
            await _record_failure(db, run_id, schedule, str(e))
            return

        duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        if result.success:
            await db.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id)
                .values(
                    status="completed",
                    completed_at=datetime.now(UTC),
                    duration_ms=duration_ms,
                    result_summary=str(result.output)[:1000] if result.output else None,
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
        else:
            await _record_failure(
                db, run_id, schedule, result.error or "Unknown error", duration_ms
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


async def _poll_and_execute() -> int:
    """Poll for due schedules and execute them. Returns count of executions dispatched."""
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

    due_schedules = []
    for schedule in schedules:
        if schedule.next_run_at is None or schedule.next_run_at <= now:
            due_schedules.append(schedule)

    if not due_schedules:
        return 0

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXECUTIONS)

    async def _run_with_semaphore(sched: AgentSchedule) -> None:
        async with semaphore:
            try:
                await _execute_scheduled_function(sched, sched.agent)
            except Exception:
                logger.exception(
                    "schedule_execution_error",
                    schedule_id=str(sched.id),
                )

    tasks = [asyncio.create_task(_run_with_semaphore(s)) for s in due_schedules]
    await asyncio.gather(*tasks, return_exceptions=True)
    executed = len(due_schedules)

    return executed


async def _initialize_next_run_times() -> None:
    """Set next_run_at for any schedules that don't have one yet."""
    async with get_db_context() as db:
        result = await db.execute(
            select(AgentSchedule).where(
                AgentSchedule.enabled.is_(True),
                AgentSchedule.next_run_at.is_(None),
            )
        )
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

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

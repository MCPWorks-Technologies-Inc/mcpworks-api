"""APScheduler integration for agent cron schedules.

Loads schedules from the MCPWorks API at startup, applies CronTrigger for each,
polls for changes every 60 seconds, and applies the configured failure policy.
"""

import asyncio
import logging
import os

import httpx

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False

logger = logging.getLogger(__name__)

AGENT_ID = os.environ.get("AGENT_ID", "")
AGENT_NAME = os.environ.get("AGENT_NAME", "")
MCPWORKS_API_URL = os.environ.get("MCPWORKS_API_URL", "http://mcpworks-api:8000")
MCPWORKS_API_KEY = os.environ.get("MCPWORKS_AGENT_API_KEY", "")
POLL_INTERVAL_SECONDS = 60


class AgentScheduler:
    """Manages cron schedule execution for an agent container.

    Loads schedules from the MCPWorks API, executes the target function
    via the run endpoint, and tracks failures per the configured policy.
    """

    def __init__(self) -> None:
        if not HAS_APSCHEDULER:
            raise RuntimeError("apscheduler is required: pip install apscheduler")
        self._scheduler = AsyncIOScheduler()
        self._loaded_schedule_ids: set[str] = set()
        self._failure_counts: dict[str, int] = {}

    async def _fetch_schedules(self) -> list[dict]:
        """Fetch current schedules from the MCPWorks API."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{MCPWORKS_API_URL}/v1/agents/{AGENT_ID}/schedules",
                headers={"Authorization": f"Bearer {MCPWORKS_API_KEY}"},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("schedules", [])

    async def _execute_function(self, schedule: dict) -> None:
        """Execute the scheduled function and handle failures."""
        schedule_id = schedule["id"]
        function_name = schedule["function_name"]
        failure_policy = schedule.get("failure_policy", {"strategy": "continue"})

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                parts = function_name.split(".", 1)
                if len(parts) != 2:
                    raise ValueError(
                        f"Invalid function_name: {function_name}; expected service.function"
                    )
                service_name, fn_name = parts
                response = await client.post(
                    f"{MCPWORKS_API_URL}/v1/namespaces/{AGENT_NAME}/{service_name}/{fn_name}",
                    headers={"Authorization": f"Bearer {MCPWORKS_API_KEY}"},
                    json={},
                )
                response.raise_for_status()
                self._failure_counts[schedule_id] = 0
                logger.info("schedule_executed", schedule_id=schedule_id, function=function_name)
        except Exception as e:
            logger.error("schedule_execution_failed", schedule_id=schedule_id, error=str(e))
            self._failure_counts[schedule_id] = self._failure_counts.get(schedule_id, 0) + 1
            await self._apply_failure_policy(schedule_id, failure_policy)

    async def _apply_failure_policy(self, schedule_id: str, policy: dict) -> None:
        """Apply the configured failure policy after a failed execution."""
        strategy = policy.get("strategy", "continue")
        consecutive = self._failure_counts.get(schedule_id, 0)

        if strategy == "auto_disable":
            max_failures = policy.get("max_failures", 3)
            if consecutive >= max_failures:
                logger.warning(
                    "schedule_auto_disabled",
                    schedule_id=schedule_id,
                    consecutive_failures=consecutive,
                )
                self._disable_schedule_job(schedule_id)
        elif strategy == "backoff":
            backoff_factor = policy.get("backoff_factor", 2.0)
            delay = min(backoff_factor**consecutive, 3600)
            logger.info(
                "schedule_backoff",
                schedule_id=schedule_id,
                delay_seconds=delay,
            )

    def _disable_schedule_job(self, schedule_id: str) -> None:
        """Pause a job in the scheduler."""
        job_id = f"schedule_{schedule_id}"
        job = self._scheduler.get_job(job_id)
        if job:
            job.pause()

    def _add_schedule_job(self, schedule: dict) -> None:
        """Add or replace a schedule job."""
        schedule_id = schedule["id"]
        job_id = f"schedule_{schedule_id}"
        cron_expression = schedule["cron_expression"]
        tz = schedule.get("timezone", "UTC")
        enabled = schedule.get("enabled", True)

        parts = cron_expression.strip().split()
        if len(parts) == 5:
            minute, hour, day, month, day_of_week = parts
        else:
            logger.warning("invalid_cron", schedule_id=schedule_id, cron=cron_expression)
            return

        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=tz,
        )

        existing_job = self._scheduler.get_job(job_id)
        if existing_job:
            existing_job.reschedule(trigger)
        else:
            self._scheduler.add_job(
                self._execute_function,
                trigger=trigger,
                id=job_id,
                args=[schedule],
                replace_existing=True,
            )

        if not enabled:
            job = self._scheduler.get_job(job_id)
            if job:
                job.pause()

    async def _poll_and_sync(self) -> None:
        """Poll API for schedule changes and sync with the scheduler."""
        try:
            schedules = await self._fetch_schedules()
            current_ids = {s["id"] for s in schedules}

            for removed_id in self._loaded_schedule_ids - current_ids:
                job_id = f"schedule_{removed_id}"
                job = self._scheduler.get_job(job_id)
                if job:
                    job.remove()
                    logger.info("schedule_removed", schedule_id=removed_id)

            for schedule in schedules:
                self._add_schedule_job(schedule)

            self._loaded_schedule_ids = current_ids
        except Exception as e:
            logger.error("schedule_poll_failed", error=str(e))

    async def start(self) -> None:
        """Start the scheduler and begin polling."""
        if not AGENT_ID:
            logger.warning("AGENT_ID not set; scheduler disabled")
            return

        self._scheduler.start()
        logger.info("agent_scheduler_started", agent_id=AGENT_ID, agent_name=AGENT_NAME)

        await self._poll_and_sync()

        while True:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            await self._poll_and_sync()

    def stop(self) -> None:
        """Stop the scheduler."""
        self._scheduler.shutdown(wait=False)
        logger.info("agent_scheduler_stopped")

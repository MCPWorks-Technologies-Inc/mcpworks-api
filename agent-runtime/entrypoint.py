"""Agent runtime entrypoint.

Starts the webhook listener, loads schedules, connects channels,
and initializes the AI engine if configured.
"""

import asyncio
import os
import signal

import httpx
import structlog
import uvicorn
from mcpworks_agent.ai_engine import AIEngine
from mcpworks_agent.scheduler import AgentScheduler
from mcpworks_agent.webhook_listener import app as webhook_app

logger = structlog.get_logger(__name__)

AGENT_NAME = os.environ.get("AGENT_NAME", "unknown")
AGENT_ID = os.environ.get("AGENT_ID", "")
API_URL = os.environ.get("MCPWORKS_API_URL", "http://mcpworks-api:8000")
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "8080"))


async def load_agent_config() -> dict:
    async with httpx.AsyncClient(base_url=API_URL) as client:
        resp = await client.get(f"/v1/agents/{AGENT_ID}")
        if resp.status_code == 200:
            return resp.json()
    return {}


async def main() -> None:
    logger.info("agent_starting", agent_name=AGENT_NAME, agent_id=AGENT_ID)

    config = await load_agent_config()

    scheduler = AgentScheduler(api_url=API_URL, agent_id=AGENT_ID)
    await scheduler.load_schedules()
    scheduler.start()

    if config.get("ai_engine"):
        AIEngine(
            engine=config["ai_engine"],
            model=config.get("ai_model", ""),
            api_url=API_URL,
            agent_id=AGENT_ID,
        )
        logger.info("ai_engine_initialized", engine=config["ai_engine"])

    logger.info("agent_ready", agent_name=AGENT_NAME)

    server = uvicorn.Server(
        uvicorn.Config(
            webhook_app,
            host="0.0.0.0",
            port=WEBHOOK_PORT,
            log_level="info",
        )
    )

    stop_event = asyncio.Event()

    def handle_signal(sig: int, _frame) -> None:
        logger.info("agent_shutdown_signal", signal=sig)
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    server_task = asyncio.create_task(server.serve())

    await stop_event.wait()

    scheduler.shutdown()
    server.should_exit = True
    await server_task

    logger.info("agent_stopped", agent_name=AGENT_NAME)


if __name__ == "__main__":
    asyncio.run(main())

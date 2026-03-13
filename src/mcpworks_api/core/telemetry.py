"""Ephemeral telemetry bus for live agent orchestration streaming."""

import asyncio
import contextlib
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field


@dataclass
class TelemetryEvent:
    event_type: str
    timestamp: float
    run_id: str
    agent_id: str
    data: dict = field(default_factory=dict)


class TelemetryBus:
    """In-memory pub/sub for agent telemetry events.

    Subscribers get an async generator of events for a specific agent_id.
    Events are ephemeral — not persisted.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, dict[str, asyncio.Queue[TelemetryEvent | None]]] = defaultdict(
            dict
        )

    def emit(self, agent_id: str, event: TelemetryEvent) -> None:
        subs = self._subscribers.get(agent_id)
        if not subs:
            return
        for queue in subs.values():
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    async def subscribe(self, agent_id: str) -> AsyncGenerator[TelemetryEvent, None]:
        sub_id = str(uuid.uuid4())
        queue: asyncio.Queue[TelemetryEvent | None] = asyncio.Queue(maxsize=256)
        self._subscribers[agent_id][sub_id] = queue
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            self._subscribers[agent_id].pop(sub_id, None)
            if not self._subscribers[agent_id]:
                self._subscribers.pop(agent_id, None)

    def unsubscribe_all(self, agent_id: str) -> None:
        subs = self._subscribers.pop(agent_id, {})
        for queue in subs.values():
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)

    def has_subscribers(self, agent_id: str) -> bool:
        return bool(self._subscribers.get(agent_id))


telemetry_bus = TelemetryBus()


def make_event(
    event_type: str,
    agent_id: str,
    run_id: str,
    **data: object,
) -> TelemetryEvent:
    return TelemetryEvent(
        event_type=event_type,
        timestamp=time.time(),
        run_id=run_id,
        agent_id=agent_id,
        data=dict(data),
    )

"""Execution token registry — maps bridge keys to namespace context for MCP proxy auth.

In-memory per-worker. Tokens registered at sandbox creation, cleared at cleanup.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger(__name__)

_registry: dict[str, ExecutionContext] = {}


@dataclass(frozen=True)
class ExecutionContext:
    execution_id: str
    namespace_id: uuid.UUID
    namespace_name: str
    created_at: datetime


def register_execution(
    token: str,
    namespace_id: uuid.UUID,
    namespace_name: str,
    execution_id: str,
) -> None:
    _registry[token] = ExecutionContext(
        execution_id=execution_id,
        namespace_id=namespace_id,
        namespace_name=namespace_name,
        created_at=datetime.now(UTC),
    )


def resolve_execution(token: str) -> ExecutionContext | None:
    return _registry.get(token)


def unregister_execution(token: str) -> None:
    _registry.pop(token, None)


def active_count() -> int:
    return len(_registry)

"""Agent OS policy scanner — wraps Microsoft Agent Governance Toolkit.

Optional dependency: pip install agent-os-kernel[full]
"""

from __future__ import annotations

from typing import Any

import structlog

from mcpworks_api.core.scanners.base import BaseScanner, ScanContext, ScanVerdict

logger = structlog.get_logger(__name__)

_agent_os = None
_import_attempted = False


def _lazy_import():
    global _agent_os, _import_attempted
    if _import_attempted:
        return _agent_os
    _import_attempted = True
    try:
        import agent_os

        _agent_os = agent_os
    except ImportError:
        logger.warning(
            "agent_os_not_installed",
            hint="pip install agent-os-kernel[full]",
        )
        _agent_os = None
    return _agent_os


class AgentOSScanner(BaseScanner):
    name = "agent_os"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._policy_format = self._config.get("policy_format", "yaml")
        self._policy = self._config.get("policy", "")

    async def scan(self, content: str, context: ScanContext) -> ScanVerdict:
        sdk = _lazy_import()
        if sdk is None:
            return ScanVerdict(
                action="pass",
                score=0.0,
                reason="agent-os-kernel not installed — skipped",
                scanner_name=self.name,
            )

        try:
            kernel = sdk.StatelessKernel()

            if self._policy_format == "yaml" and self._policy:
                kernel.load_policy_yaml(self._policy)

            ctx = sdk.ExecutionContext(
                agent_id=f"{context.namespace}:{context.service}",
                policies=[],
            )
            result = await kernel.execute(
                action=f"{context.service}.{context.function}",
                params={"content": content, "direction": context.direction},
                context=ctx,
            )

            allowed = getattr(result, "allowed", True)
            if not allowed:
                return ScanVerdict(
                    action="block",
                    score=1.0,
                    reason=f"policy violation ({self._policy_format})",
                    scanner_name=self.name,
                )

            return ScanVerdict(
                action="pass",
                score=0.0,
                reason="policy check passed",
                scanner_name=self.name,
            )

        except Exception as e:
            logger.warning(
                "agent_os_scanner_error",
                error=str(e),
                policy_format=self._policy_format,
                namespace=context.namespace,
            )
            return ScanVerdict(
                action="pass",
                score=0.0,
                reason=f"agent_os error: {str(e)[:100]} — skipped",
                scanner_name=self.name,
            )

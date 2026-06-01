"""Python callable scanner — import and call a user-provided module."""

from __future__ import annotations

import importlib
from typing import Any

import structlog

from mcpworks_api.core.scanners.base import BaseScanner, ScanContext, ScanVerdict

logger = structlog.get_logger(__name__)


class PythonScanner(BaseScanner):
    def __init__(
        self,
        module_path: str,
        function_name: str = "scan",
        init_kwargs: dict[str, Any] | None = None,
        scanner_name: str = "python",
    ) -> None:
        self.module_path = module_path
        self.function_name = function_name
        self.init_kwargs = init_kwargs or {}
        self.name = scanner_name
        self._func = None
        self._available = True

    def _load(self) -> None:
        if self._func is not None or not self._available:
            return
        try:
            module = importlib.import_module(self.module_path)
            self._func = getattr(module, self.function_name)
        except Exception:
            logger.warning(
                "python_scanner_import_failed",
                module=self.module_path,
                function=self.function_name,
                exc_info=True,
            )
            self._available = False

    async def scan(self, content: str, context: ScanContext) -> ScanVerdict:
        self._load()
        if not self._available or self._func is None:
            return ScanVerdict(
                action="pass",
                score=0.0,
                reason=f"scanner unavailable (import failed: {self.module_path})",
                scanner_name=self.name,
            )

        try:
            ctx = {
                "direction": context.direction,
                "namespace": context.namespace,
                "service": context.service,
                "function": context.function,
            }
            result = self._func(content, ctx, **self.init_kwargs)

            if hasattr(result, "__await__"):
                result = await result

            if not isinstance(result, dict):
                return ScanVerdict(
                    action="pass",
                    score=0.0,
                    reason=f"scanner returned non-dict: {type(result).__name__}",
                    scanner_name=self.name,
                )

            action = result.get("action", "pass")
            if action not in ("pass", "flag", "block"):
                action = "pass"

            return ScanVerdict(
                action=action,
                score=float(result.get("score", 0.0)),
                reason=result.get("reason", ""),
                scanner_name=self.name,
            )

        except Exception as e:
            logger.warning("python_scanner_error", module=self.module_path, error=str(e))
            return ScanVerdict(
                action="pass",
                score=0.0,
                reason=f"scanner error: {str(e)[:100]} — skipped",
                scanner_name=self.name,
            )

"""Webhook scanner — POST content to an external HTTP service for scanning."""

from __future__ import annotations

import httpx
import structlog

from mcpworks_api.core.scanners.base import BaseScanner, ScanContext, ScanVerdict

logger = structlog.get_logger(__name__)


class WebhookScanner(BaseScanner):
    def __init__(
        self,
        url: str,
        timeout_ms: int = 5000,
        headers: dict[str, str] | None = None,
        scanner_name: str = "webhook",
    ) -> None:
        self.url = url
        self.timeout_ms = timeout_ms
        self.headers = headers or {}
        self.name = scanner_name

    async def scan(self, content: str, context: ScanContext) -> ScanVerdict:
        payload = {
            "content": content,
            "direction": context.direction,
            "namespace": context.namespace,
            "service": context.service,
            "function": context.function,
            "metadata": {
                "execution_id": context.execution_id,
                "output_trust": context.output_trust,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
                resp = await client.post(
                    self.url,
                    json=payload,
                    headers={"Content-Type": "application/json", **self.headers},
                )
                resp.raise_for_status()
                data = resp.json()

                action = data.get("action", "pass")
                if action not in ("pass", "flag", "block"):
                    action = "pass"

                return ScanVerdict(
                    action=action,
                    score=float(data.get("score", 0.0)),
                    reason=data.get("reason", ""),
                    scanner_name=self.name,
                )

        except httpx.TimeoutException:
            logger.warning("webhook_scanner_timeout", url=self.url, timeout_ms=self.timeout_ms)
            return ScanVerdict(
                action="pass",
                score=0.0,
                reason=f"webhook timeout ({self.timeout_ms}ms) — skipped",
                scanner_name=self.name,
            )
        except Exception as e:
            logger.warning("webhook_scanner_error", url=self.url, error=str(e))
            return ScanVerdict(
                action="pass",
                score=0.0,
                reason=f"webhook error: {str(e)[:100]} — skipped",
                scanner_name=self.name,
            )

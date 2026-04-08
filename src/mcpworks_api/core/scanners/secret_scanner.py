"""Secret detection scanner — scrubs credentials from output.

Wraps the existing output_sanitizer.scrub_secrets() as a BaseScanner.
This scanner can transform content (redacting secrets in-place).
"""

from __future__ import annotations

from mcpworks_api.core.output_sanitizer import scrub_secrets
from mcpworks_api.core.scanners.base import BaseScanner, ScanContext, ScanVerdict


class SecretScanner(BaseScanner):
    name = "secret_scanner"

    async def scan(self, content: str, context: ScanContext) -> ScanVerdict:  # noqa: ARG002
        _, count = scrub_secrets(content)
        if count > 0:
            return ScanVerdict(
                action="flag",
                score=0.95,
                reason=f"{count} secret(s) detected and will be redacted",
                scanner_name=self.name,
            )
        return ScanVerdict(
            action="pass", score=0.0, reason="no secrets detected", scanner_name=self.name
        )

    async def scan_and_transform(
        self, content: str, context: ScanContext  # noqa: ARG002
    ) -> tuple[str, ScanVerdict]:
        cleaned, count = scrub_secrets(content)
        if count > 0:
            verdict = ScanVerdict(
                action="flag",
                score=0.95,
                reason=f"{count} secret(s) redacted",
                scanner_name=self.name,
            )
            return cleaned, verdict
        return content, ScanVerdict(
            action="pass", score=0.0, reason="no secrets detected", scanner_name=self.name
        )

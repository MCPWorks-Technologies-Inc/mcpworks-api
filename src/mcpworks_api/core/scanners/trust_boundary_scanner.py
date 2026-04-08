"""Trust boundary scanner — wraps untrusted output with markers.

Applies trust boundary markers when output_trust is "data".
Always returns "pass" — wrapping is the action, not blocking.
"""

from __future__ import annotations

from mcpworks_api.core.scanners.base import BaseScanner, ScanContext, ScanVerdict


class TrustBoundaryScanner(BaseScanner):
    name = "trust_boundary"

    async def scan(self, content: str, context: ScanContext) -> ScanVerdict:  # noqa: ARG002
        if context.output_trust == "data":
            return ScanVerdict(
                action="pass",
                score=0.0,
                reason="output_trust=data, trust boundary markers applied",
                scanner_name=self.name,
            )
        return ScanVerdict(
            action="pass",
            score=0.0,
            reason="output_trust=prompt, no wrapping",
            scanner_name=self.name,
        )

    async def scan_and_transform(
        self, content: str, context: ScanContext
    ) -> tuple[str, ScanVerdict]:
        if context.output_trust == "data":
            wrapped = (
                f'[UNTRUSTED_OUTPUT source="{context.service}.{context.function}" trust="data"]\n'
                f"{content}\n"
                f"[/UNTRUSTED_OUTPUT]"
            )
            verdict = ScanVerdict(
                action="pass",
                score=0.0,
                reason="trust boundary markers applied",
                scanner_name=self.name,
            )
            return wrapped, verdict
        return content, ScanVerdict(
            action="pass", score=0.0, reason="trusted output, no wrapping", scanner_name=self.name
        )

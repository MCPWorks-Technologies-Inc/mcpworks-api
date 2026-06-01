"""Scanner interface and data types for the security scanner pipeline."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ScanContext:
    direction: str  # "input" or "output"
    namespace: str
    service: str
    function: str
    execution_id: str = ""
    output_trust: str = "prompt"


@dataclass
class ScanVerdict:
    action: str  # "pass", "flag", "block"
    score: float  # 0.0 - 1.0
    reason: str
    scanner_name: str
    timing_ms: float = 0.0


@dataclass
class PipelineResult:
    final_action: str
    final_score: float
    verdicts: list[ScanVerdict] = field(default_factory=list)
    total_ms: float = 0.0
    content_hash: str = ""
    modified_content: str | None = None

    @staticmethod
    def compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


class BaseScanner(ABC):
    name: str = "base"

    @abstractmethod
    async def scan(self, content: str, context: ScanContext) -> ScanVerdict: ...

    async def scan_and_transform(
        self, content: str, context: ScanContext
    ) -> tuple[str, ScanVerdict]:
        verdict = await self.scan(content, context)
        return content, verdict

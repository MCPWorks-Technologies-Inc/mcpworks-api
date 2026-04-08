"""Security scanner pipeline evaluator.

Evaluates content through an ordered sequence of scanners.
Supports builtin, webhook, and python scanner types.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from mcpworks_api.core.scanners import BUILTIN_SCANNERS
from mcpworks_api.core.scanners.base import (
    BaseScanner,
    PipelineResult,
    ScanContext,
    ScanVerdict,
)

logger = structlog.get_logger(__name__)

DEFAULT_PIPELINE: dict[str, Any] = {
    "fallback_policy": "fail_open",
    "scanners": [
        {
            "id": "default-pattern",
            "type": "builtin",
            "name": "pattern_scanner",
            "direction": "output",
            "order": 1,
            "enabled": True,
            "config": {},
        },
        {
            "id": "default-secret",
            "type": "builtin",
            "name": "secret_scanner",
            "direction": "output",
            "order": 2,
            "enabled": True,
            "config": {},
        },
        {
            "id": "default-trust",
            "type": "builtin",
            "name": "trust_boundary",
            "direction": "output",
            "order": 3,
            "enabled": True,
            "config": {},
        },
    ],
}

_ACTION_SEVERITY = {"pass": 0, "flag": 1, "block": 2}


def _resolve_scanner(entry: dict[str, Any]) -> BaseScanner | None:
    scanner_type = entry.get("type")
    scanner_name = entry.get("name", "")

    if scanner_type == "builtin":
        cls = BUILTIN_SCANNERS.get(scanner_name)
        if not cls:
            logger.warning("scanner_unknown_builtin", name=scanner_name)
            return None
        return cls()

    if scanner_type == "webhook":
        from mcpworks_api.core.scanners.webhook_scanner import WebhookScanner

        config = entry.get("config", {})
        return WebhookScanner(
            url=config.get("url", ""),
            timeout_ms=config.get("timeout_ms", 5000),
            headers=config.get("headers"),
            scanner_name=scanner_name,
        )

    if scanner_type == "agent_os":
        try:
            from mcpworks_api.core.scanners.agent_os_scanner import AgentOSScanner
        except Exception:
            logger.warning(
                "scanner_unavailable",
                type="agent_os",
                hint="pip install agent-os-kernel[full]",
            )
            return None
        return AgentOSScanner(config=entry.get("config", {}))

    if scanner_type == "python":
        from mcpworks_api.core.scanners.python_scanner import PythonScanner

        config = entry.get("config", {})
        return PythonScanner(
            module_path=config.get("module", ""),
            function_name=config.get("function", "scan"),
            init_kwargs=config.get("init_kwargs"),
            scanner_name=scanner_name,
        )

    logger.warning("scanner_unknown_type", type=scanner_type)
    return None


async def evaluate_pipeline(
    content: str,
    context: ScanContext,
    pipeline_config: dict[str, Any] | None = None,
) -> PipelineResult:
    config = pipeline_config or DEFAULT_PIPELINE
    fallback_policy = config.get("fallback_policy", "fail_open")
    scanner_entries = sorted(config.get("scanners", []), key=lambda s: s.get("order", 999))

    pipeline_start = time.monotonic()
    verdicts: list[ScanVerdict] = []
    modified_content = content
    all_errored = True

    for entry in scanner_entries:
        if not entry.get("enabled", True):
            continue

        direction = entry.get("direction", "output")
        if direction != "both" and direction != context.direction:
            continue

        scanner = _resolve_scanner(entry)
        if scanner is None:
            continue

        scan_start = time.monotonic()
        try:
            modified_content, verdict = await scanner.scan_and_transform(modified_content, context)
            verdict.timing_ms = (time.monotonic() - scan_start) * 1000
            verdicts.append(verdict)
            all_errored = False

            logger.info(
                "scanner_completed",
                scanner=verdict.scanner_name,
                action=verdict.action,
                score=verdict.score,
                timing_ms=round(verdict.timing_ms, 1),
            )

            if verdict.action == "block":
                break

        except Exception:
            timing_ms = (time.monotonic() - scan_start) * 1000
            logger.warning(
                "scanner_error",
                scanner=entry.get("name", "unknown"),
                timing_ms=round(timing_ms, 1),
                exc_info=True,
            )
            verdicts.append(
                ScanVerdict(
                    action="pass",
                    score=0.0,
                    reason="scanner error — skipped",
                    scanner_name=entry.get("name", "unknown"),
                    timing_ms=timing_ms,
                )
            )

    total_ms = (time.monotonic() - pipeline_start) * 1000

    if all_errored and verdicts:
        final_action = "block" if fallback_policy == "fail_closed" else "pass"
        final_score = 1.0 if final_action == "block" else 0.0
    elif verdicts:
        deciding = max(verdicts, key=lambda v: _ACTION_SEVERITY.get(v.action, 0))
        final_action = deciding.action
        final_score = deciding.score
    else:
        final_action = "pass"
        final_score = 0.0

    result = PipelineResult(
        final_action=final_action,
        final_score=final_score,
        verdicts=verdicts,
        total_ms=total_ms,
        content_hash=PipelineResult.compute_hash(content),
        modified_content=modified_content if modified_content != content else None,
    )

    logger.info(
        "pipeline_completed",
        final_action=final_action,
        final_score=final_score,
        scanners_run=len(verdicts),
        total_ms=round(total_ms, 1),
    )

    return result

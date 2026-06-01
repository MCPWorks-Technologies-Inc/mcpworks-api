"""Pattern-based prompt injection scanner.

Detects known injection patterns via regex with Unicode normalization
and base64 decoding. Refactored from sandbox/injection_scan.py.
"""

from __future__ import annotations

import base64
import re
import unicodedata

from mcpworks_api.core.scanners.base import BaseScanner, ScanContext, ScanVerdict

_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "instruction_override",
        re.compile(
            r"(?:ignore|disregard|forget|override|bypass|skip)\s+"
            r"(?:all\s+)?(?:previous|prior|above|earlier|preceding|original)\s+"
            r"(?:instructions?|prompts?|rules?|guidelines?|directions?|context)",
            re.IGNORECASE,
        ),
        "high",
    ),
    (
        "role_reassignment",
        re.compile(
            r"(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you(?:'re|\s+are))|"
            r"assume\s+the\s+role|from\s+now\s+on\s+you\s+are|"
            r"switch\s+to\s+(?:being|acting\s+as))",
            re.IGNORECASE,
        ),
        "high",
    ),
    (
        "system_prompt_injection",
        re.compile(
            r"(?:^|\n)\s*(?:SYSTEM\s*:|"
            r"\[SYSTEM\]|"
            r"###\s*System|"
            r"<\|system\|>|"
            r"<system>|"
            r"System\s+prompt\s*:)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "high",
    ),
    (
        "delimiter_injection",
        re.compile(
            r"(?:^|\n)(?:---+|===+|```)\s*\n\s*"
            r"(?:you\s+(?:are|must|should|will|need)|"
            r"ignore|override|new\s+instructions?|"
            r"(?:SYSTEM|ADMIN|ROOT)\s*:)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "medium",
    ),
    (
        "authority_claim",
        re.compile(
            r"(?:^|\n)\s*(?:IMPORTANT|URGENT|CRITICAL|ADMIN\s+NOTICE|"
            r"SECURITY\s+(?:ALERT|UPDATE|NOTICE)|"
            r"AUTHORIZED|OFFICIAL)\s*:\s*"
            r"(?:ignore|override|change|update|modify|forward|send|delete|execute)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "medium",
    ),
    (
        "output_manipulation",
        re.compile(
            r"(?:repeat\s+after\s+me|say\s+exactly|"
            r"respond\s+(?:only\s+)?with|"
            r"output\s+(?:only|exactly)|"
            r"your\s+(?:only\s+)?response\s+(?:should|must|will)\s+be)",
            re.IGNORECASE,
        ),
        "medium",
    ),
    (
        "base64_obfuscation",
        re.compile(
            r"(?:decode|base64|atob)\s*\(\s*['\"]"
            r"(?:[A-Za-z0-9+/]{20,}={0,2})"
            r"['\"]",
            re.IGNORECASE,
        ),
        "low",
    ),
    (
        "indirect_instruction",
        re.compile(
            r"(?:when\s+you\s+(?:see|read|encounter|process)\s+this|"
            r"if\s+(?:this|the\s+(?:previous|above))\s+(?:message|text|content)\s+"
            r"(?:contains?|includes?|mentions?)|"
            r"upon\s+reading\s+this\s*,?\s*(?:you\s+(?:must|should|will)))",
            re.IGNORECASE,
        ),
        "low",
    ),
]

_SEVERITY_SCORES = {"high": 0.9, "medium": 0.6, "low": 0.3}
_MAX_MATCHES = 50
_MAX_MATCH_TEXT = 200
_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\ufeff\u00ad\u2060]")
_BASE64_BLOCK = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")


def normalize_text(text: str) -> str:
    result = unicodedata.normalize("NFKC", text)
    result = _ZERO_WIDTH.sub("", result)
    result = re.sub(r"[ \t]+", " ", result)

    decoded_parts = []
    for m in _BASE64_BLOCK.finditer(result):
        try:
            decoded = base64.b64decode(m.group(0)).decode("utf-8", errors="ignore")
            if len(decoded) > 5 and decoded.isprintable():
                decoded_parts.append(decoded)
        except Exception:
            pass

    if decoded_parts:
        result = result + "\n" + "\n".join(decoded_parts)

    return result


def scan_text(text: str) -> list[dict]:
    if not text:
        return []

    normalized = normalize_text(text)
    matches: list[dict] = []
    for pattern_name, pattern, severity in _PATTERNS:
        for m in pattern.finditer(normalized):
            if len(matches) >= _MAX_MATCHES:
                return matches
            matches.append(
                {
                    "pattern": pattern_name,
                    "matched": m.group(0)[:_MAX_MATCH_TEXT],
                    "severity": severity,
                    "position": m.start(),
                }
            )
    return matches


class PatternScanner(BaseScanner):
    name = "pattern_scanner"

    async def scan(self, content: str, context: ScanContext) -> ScanVerdict:  # noqa: ARG002
        matches = scan_text(content)
        if not matches:
            return ScanVerdict(
                action="pass",
                score=0.0,
                reason="no injection patterns detected",
                scanner_name=self.name,
            )

        highest_severity = max(matches, key=lambda m: _SEVERITY_SCORES.get(m["severity"], 0))
        score = _SEVERITY_SCORES.get(highest_severity["severity"], 0.5)
        patterns = ", ".join({m["pattern"] for m in matches})
        return ScanVerdict(
            action="flag",
            score=score,
            reason=f"injection patterns detected: {patterns}",
            scanner_name=self.name,
        )


def suggest_trust_level(code: str | None, required_env: list[str] | None = None) -> tuple[str, str]:
    if code and re.search(r"\bmcp__\w+", code):
        return "data", "function imports mcp__ remote tools"
    if required_env:
        external_hints = {"url", "api", "token", "key", "secret", "endpoint", "webhook"}
        env_lower = {e.lower() for e in required_env}
        for hint in external_hints:
            if any(hint in e for e in env_lower):
                return "data", f"required_env contains '{hint}' keyword"
    if code and re.search(r"\b(?:httpx|requests|urllib|aiohttp)\b", code):
        return "data", "function uses HTTP client library"
    return "prompt", "no external dependencies detected"


def scan_for_injections(text: str) -> list[dict]:
    """Compatibility alias for scan_text."""
    return scan_text(text)

"""Prompt injection scanner — pattern-based detection of common injection attacks.

Same architecture as credential_scan.py. Scans text and JSON structures
for known prompt injection patterns. Returns structured matches with
severity levels.
"""

import re
from dataclasses import dataclass


@dataclass
class InjectionMatch:
    pattern_name: str
    matched_text: str
    severity: str
    position: int


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

MAX_MATCHES = 50
MAX_MATCH_TEXT = 200


def scan_for_injections(text: str) -> list[InjectionMatch]:
    if not text:
        return []

    matches: list[InjectionMatch] = []
    for pattern_name, pattern, severity in _PATTERNS:
        for m in pattern.finditer(text):
            if len(matches) >= MAX_MATCHES:
                return matches
            matched = m.group(0)[:MAX_MATCH_TEXT]
            matches.append(
                InjectionMatch(
                    pattern_name=pattern_name,
                    matched_text=matched,
                    severity=severity,
                    position=m.start(),
                )
            )
    return matches


def scan_json_for_injections(data: dict | list | str | None) -> list[InjectionMatch]:
    if data is None:
        return []
    if isinstance(data, str):
        return scan_for_injections(data)
    if isinstance(data, list):
        matches: list[InjectionMatch] = []
        for item in data:
            matches.extend(scan_json_for_injections(item))
            if len(matches) >= MAX_MATCHES:
                return matches[:MAX_MATCHES]
        return matches
    if isinstance(data, dict):
        matches = []
        for value in data.values():
            matches.extend(scan_json_for_injections(value))
            if len(matches) >= MAX_MATCHES:
                return matches[:MAX_MATCHES]
        return matches
    return []


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

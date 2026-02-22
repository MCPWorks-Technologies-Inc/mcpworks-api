"""Scan function code for hardcoded credentials before persistence."""

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "AWS secret key",
        re.compile(
            r"""(?:aws_secret|secret_access_key|AWS_SECRET)\s*[=:]\s*['"]([0-9a-zA-Z/+=]{40})['"]"""
        ),
    ),
    (
        "API key (sk-/rk- prefix)",
        re.compile(r"(?:sk-|sk_live_|sk_test_|rk_live_|rk_test_)\S{20,}"),
    ),
    (
        "GitHub token",
        re.compile(r"(?:ghp_|ghs_|gho_|github_pat_)[a-zA-Z0-9_]{20,}"),
    ),
    ("private key", re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----")),
    (
        "JWT token",
        re.compile(
            r"eyJ[a-zA-Z0-9_-]{20,}\.eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]+"
        ),
    ),
    (
        "connection string with password",
        re.compile(r"(?:postgresql|mysql|mongodb|redis)://[^:]+:[^@]+@"),
    ),
    (
        "hardcoded secret assignment",
        re.compile(
            r"""(?:password|secret|token|api_key|apikey|api_secret)\s*=\s*['"][^'"]{8,}['"]""",
            re.IGNORECASE,
        ),
    ),
    (
        "os.environ assignment",
        re.compile(r"""os\.environ\[.*\]\s*=\s*['"]"""),
    ),
]


def scan_code_for_credentials(code: str) -> list[str]:
    """Return warning messages for detected credential patterns in code.

    Performs line-by-line scanning so warnings include line numbers.
    """
    warnings: list[str] = []
    for line_num, line in enumerate(code.splitlines(), start=1):
        for label, pattern in _PATTERNS:
            if pattern.search(line):
                warnings.append(
                    f"Possible {label} detected (line {line_num}). "
                    "Use required_env instead of hardcoding credentials."
                )
    return warnings

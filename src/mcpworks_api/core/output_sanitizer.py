"""Output sanitization — OWASP LLM05 Improper Output Handling defense.

Scrubs secrets from sandbox execution output before returning to LLMs.
"""

import re

SECRET_PATTERNS: list[tuple[str, str]] = [
    (r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_API_KEY]"),
    (r"sk-proj-[a-zA-Z0-9_-]{50,}", "[REDACTED_API_KEY]"),
    (r"sk-ant-[a-zA-Z0-9_-]{50,}", "[REDACTED_API_KEY]"),
    (r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
    (r"ghp_[a-zA-Z0-9]{36}", "[REDACTED_GITHUB_TOKEN]"),
    (r"gho_[a-zA-Z0-9]{36}", "[REDACTED_GITHUB_TOKEN]"),
    (r"glpat-[a-zA-Z0-9_-]{20,}", "[REDACTED_GITLAB_TOKEN]"),
    (r"mcpw_[a-f0-9]{64}", "[REDACTED_MCPWORKS_KEY]"),
    (r"eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", "[REDACTED_JWT]"),
    (
        r"(postgres|postgresql|mysql|mongodb|redis|rediss)://[^\s\"']+",
        "[REDACTED_CONNECTION_URI]",
    ),
    (
        r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
    ),
]

_COMPILED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE), r) for p, r in SECRET_PATTERNS
]

OUTPUT_SIZE_LIMITS: dict[str, int] = {
    "trial": 1 * 1024 * 1024,
    "pro": 1 * 1024 * 1024,
    "enterprise": 5 * 1024 * 1024,
    "dedicated": 10 * 1024 * 1024,
}


def scrub_secrets(output: str) -> tuple[str, int]:
    """Scrub secret patterns from output.

    Returns:
        (scrubbed_output, redaction_count)
    """
    count = 0
    for pattern, replacement in _COMPILED_PATTERNS:
        output, n = pattern.subn(replacement, output)
        count += n
    return output, count


def enforce_output_size(output: str, tier: str) -> str:
    max_size = OUTPUT_SIZE_LIMITS.get(tier, OUTPUT_SIZE_LIMITS["trial"])
    encoded = output.encode("utf-8")
    if len(encoded) <= max_size:
        return output
    truncated = encoded[:max_size].decode("utf-8", errors="ignore")
    return (
        truncated + f"\n\n[OUTPUT TRUNCATED: exceeded {max_size // 1024}KB limit for {tier} tier]"
    )

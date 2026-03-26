"""Trust boundary markers — wrap untrusted content for AI context visibility.

Markers are string-wrapped around the result text so they are visible
in the AI's context window. Generated server-side only (after sandbox exit).
"""


def wrap_function_output(result_text: str, service: str, function: str) -> str:
    return (
        f'[UNTRUSTED_OUTPUT function="{service}.{function}" trust="data"]\n'
        f"{result_text}\n"
        f"[/UNTRUSTED_OUTPUT]"
    )


def wrap_mcp_response(
    response_text: str,
    server: str,
    tool: str,
    injections_found: int = 0,
) -> str:
    return (
        f'[EXTERNAL_DATA source="{server}" tool="{tool}" trust="untrusted" injections_found={injections_found}]\n'
        f"{response_text}\n"
        f"[/EXTERNAL_DATA]"
    )


def wrap_injection_warning(text: str, pattern: str, severity: str) -> str:
    return (
        f'[INJECTION_WARNING pattern="{pattern}" severity="{severity}"]\n'
        f"{text}\n"
        f"[/INJECTION_WARNING]"
    )


def apply_injection_flags(
    text: str,
    matches: list,
) -> str:
    if not matches:
        return text
    sorted_matches = sorted(matches, key=lambda m: m.position, reverse=True)
    result = text
    for match in sorted_matches:
        start = match.position
        end = start + len(match.matched_text)
        flagged = wrap_injection_warning(result[start:end], match.pattern_name, match.severity)
        result = result[:start] + flagged + result[end:]
    return result


def redact_injection(text: str, matches: list) -> str:
    if not matches:
        return text
    sorted_matches = sorted(matches, key=lambda m: m.position, reverse=True)
    result = text
    for match in sorted_matches:
        start = match.position
        end = start + len(match.matched_text)
        redaction = (
            f'[REDACTED: prompt injection detected — pattern: "{match.pattern_name}", '
            f'severity: {match.severity}. Change strictness to "flag" or "warn" to allow.]'
        )
        result = result[:start] + redaction + result[end:]
    return result

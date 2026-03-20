"""Context budget estimation and monitoring.

Tracks estimated token count of context sent to the LLM on each orchestration
call. Helps detect context bloat before it degrades agent performance.

Thresholds based on research showing 40-90% performance degradation at high
context sizes ("context rot").
"""

import json

# Thresholds (estimated tokens)
CONTEXT_GREEN = 4_000
CONTEXT_YELLOW = 8_000
CONTEXT_ORANGE = 16_000
CONTEXT_RED = 32_000


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English/code mix."""
    return len(text) // 4


def estimate_context_budget(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
) -> dict:
    """Estimate total context tokens and return budget report."""
    prompt_tokens = estimate_tokens(system_prompt)

    messages_text = json.dumps(messages, default=str)
    messages_tokens = estimate_tokens(messages_text)

    tools_text = json.dumps(tools, default=str)
    tools_tokens = estimate_tokens(tools_text)

    total = prompt_tokens + messages_tokens + tools_tokens

    if total < CONTEXT_GREEN:
        level = "green"
    elif total < CONTEXT_YELLOW:
        level = "yellow"
    elif total < CONTEXT_ORANGE:
        level = "orange"
    else:
        level = "red"

    return {
        "total_estimated_tokens": total,
        "breakdown": {
            "system_prompt": prompt_tokens,
            "messages": messages_tokens,
            "tools": tools_tokens,
        },
        "level": level,
    }

"""Conversation memory: persist, load, and compact conversation history.

Stores conversation turns in the __conversation_history__ agent state key.
Before each orchestration/chat, recent history is loaded and injected as
context. When turn count exceeds a threshold, older turns are summarized
by the LLM and replaced with a compact summary.
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

# Tunables
MAX_HISTORY_TURNS = 50
COMPACTION_TURN_THRESHOLD = 30
COMPACTION_KEEP_RECENT = 10
MAX_HISTORY_CHARS = 50_000
SUMMARY_MAX_CHARS = 2_000

STATE_KEY = "__conversation_history__"


def load_history(agent_state: dict[str, Any]) -> tuple[str | None, list[dict]]:
    """Load summary + recent turns from agent state.

    Returns (summary, recent_turns).
    """
    raw = agent_state.get(STATE_KEY)
    if not raw or not isinstance(raw, dict):
        return None, []

    summary = raw.get("summary")
    turns = raw.get("turns", [])
    if not isinstance(turns, list):
        return summary, []

    return summary, turns


def build_history_messages(
    summary: str | None,
    turns: list[dict],
) -> list[dict]:
    """Build message list from conversation history for injection into context.

    Returns a list of {role, content} dicts ready to prepend to messages.
    """
    messages: list[dict] = []

    if summary:
        messages.append(
            {
                "role": "user",
                "content": f"[Previous conversation summary]\n{summary}",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "Understood, I have context from our previous conversations.",
            }
        )

    for turn in turns:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    return messages


async def append_turn(
    agent_id: UUID,
    account_id: UUID,
    agent_name: str,
    role: str,
    content: str,
    tier: str,
    trigger: str = "chat",
) -> None:
    """Append a conversation turn to persistent state."""
    from mcpworks_api.core.database import get_db_context
    from mcpworks_api.services.agent_service import AgentService

    async with get_db_context() as db:
        service = AgentService(db)
        agent_state = await service.get_all_state(agent_id)

    raw = agent_state.get(STATE_KEY) if agent_state else None
    if not raw or not isinstance(raw, dict):
        raw = {"turns": [], "summary": None, "compacted_at": None}

    turns = raw.get("turns", [])
    if not isinstance(turns, list):
        turns = []

    turns.append(
        {
            "role": role,
            "content": content[:MAX_HISTORY_CHARS],
            "ts": datetime.now(UTC).isoformat(),
            "trigger": trigger,
        }
    )

    # Hard cap on turns
    if len(turns) > MAX_HISTORY_TURNS:
        turns = turns[-MAX_HISTORY_TURNS:]

    raw["turns"] = turns

    async with get_db_context() as db:
        service = AgentService(db)
        try:
            await service.set_state(account_id, agent_name, STATE_KEY, raw, tier)
        except Exception:
            logger.warning(
                "conversation_memory_append_failed",
                agent_name=agent_name,
                reason="state_size_limit",
            )


def needs_compaction(agent_state: dict[str, Any]) -> bool:
    """Check if conversation history needs compaction."""
    raw = agent_state.get(STATE_KEY)
    if not raw or not isinstance(raw, dict):
        return False
    turns = raw.get("turns", [])
    return isinstance(turns, list) and len(turns) >= COMPACTION_TURN_THRESHOLD


async def compact_history(
    agent_id: UUID,
    account_id: UUID,
    agent_name: str,
    ai_engine: str,
    ai_model: str,
    api_key: str,
    agent_state: dict[str, Any],
    tier: str,
) -> None:
    """Summarize older turns via LLM, keep recent turns verbatim."""
    from mcpworks_api.core.ai_client import chat
    from mcpworks_api.core.database import get_db_context
    from mcpworks_api.services.agent_service import AgentService

    raw = agent_state.get(STATE_KEY)
    if not raw or not isinstance(raw, dict):
        return

    turns = raw.get("turns", [])
    if not isinstance(turns, list) or len(turns) < COMPACTION_TURN_THRESHOLD:
        return

    old_turns = turns[:-COMPACTION_KEEP_RECENT]
    keep_turns = turns[-COMPACTION_KEEP_RECENT:]

    # Build text to summarize
    existing_summary = raw.get("summary", "")
    conversation_text = ""
    if existing_summary:
        conversation_text += f"Previous summary:\n{existing_summary}\n\n"
    conversation_text += "Recent conversation:\n"
    for turn in old_turns:
        role = turn.get("role", "unknown")
        content = turn.get("content", "")[:500]
        conversation_text += f"{role}: {content}\n"

    # Truncate to avoid sending too much to the LLM
    conversation_text = conversation_text[:MAX_HISTORY_CHARS]

    compaction_prompt = (
        "Summarize this conversation history in under 500 words. "
        "Focus on: decisions made, tasks completed, current state of work, "
        "important facts shared, and anything that should be remembered going forward. "
        "Be specific about names, dates, and outcomes.\n\n"
        f"{conversation_text}"
    )

    try:
        new_summary = await chat(
            engine=ai_engine,
            model=ai_model,
            api_key=api_key,
            messages=[{"role": "user", "content": compaction_prompt}],
            system_prompt="You are a concise conversation summarizer. Output only the summary.",
        )
    except Exception:
        logger.exception("conversation_memory_compaction_failed", agent_name=agent_name)
        return

    new_summary = new_summary[:SUMMARY_MAX_CHARS]

    compacted = {
        "turns": keep_turns,
        "summary": new_summary,
        "compacted_at": datetime.now(UTC).isoformat(),
    }

    async with get_db_context() as db:
        service = AgentService(db)
        try:
            await service.set_state(account_id, agent_name, STATE_KEY, compacted, tier)
            logger.info(
                "conversation_memory_compacted",
                agent_name=agent_name,
                old_turns=len(old_turns),
                kept_turns=len(keep_turns),
                summary_chars=len(new_summary),
            )
        except Exception:
            logger.warning(
                "conversation_memory_compaction_save_failed",
                agent_name=agent_name,
            )

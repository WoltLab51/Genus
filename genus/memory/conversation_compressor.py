"""
ConversationCompressor — Phase 14b

Compresses a list of conversation messages into an Episode summary.

Strategy:
1. If an LLM router is available, use it (TaskType.SUMMARIZE) to produce a
   JSON payload with ``summary`` and ``topics``.
2. On any error, or when no router is provided, fall back to a rule-based
   approach that never raises.

This function is intentionally infallible — it always returns an Episode.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from genus.memory.episode_store import Episode

logger = logging.getLogger(__name__)

_STOP_WORDS = frozenset({
    "ich", "du", "er", "sie", "es", "wir", "ihr", "sie",
    "der", "die", "das", "ein", "eine", "und", "oder", "aber",
    "in", "auf", "an", "für", "mit", "von", "zu", "ist", "sind",
    "hat", "haben", "war", "können", "kann", "bitte", "danke",
    "the", "a", "an", "is", "are", "was", "were", "have", "has",
    "and", "or", "but", "in", "on", "at", "for", "with", "of", "to",
})

_WORD_PATTERN = re.compile(r"[a-zA-ZäöüÄÖÜß]{4,}")

_LLM_SYSTEM_PROMPT = (
    "Du bist ein Gedächtnis-Assistent für GENUS. "
    "Fasse das folgende Gespräch in maximal 3 Sätzen auf Deutsch zusammen. "
    "Extrahiere die wichtigsten Themen als kurze Stichworte. "
    "Antworte ausschließlich als gültiges JSON-Objekt im Format: "
    '{"summary": "...", "topics": ["...", "..."]}'
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def compress_session(
    session_id: str,
    user_id: str,
    messages: List[Dict[str, Any]],
    *,
    llm_router: Optional[Any] = None,
) -> Episode:
    """Compress *messages* into an Episode.

    Args:
        session_id:  The conversation session identifier.
        user_id:     The user who owns this session.
        messages:    List of message dicts (typically ``{"role": ..., "content": ...}``).
        llm_router:  Optional :class:`~genus.llm.router.LLMRouter` instance.
                     When provided, the LLM is used for summarisation.

    Returns:
        An :class:`~genus.memory.episode_store.Episode` — always, never raises.
    """
    if not messages:
        return Episode.create(
            user_id=user_id,
            summary="",
            topics=[],
            session_ids=[session_id],
            message_count=0,
            source="fallback",
        )

    # Try LLM path first
    if llm_router is not None:
        episode = await _compress_with_llm(
            session_id=session_id,
            user_id=user_id,
            messages=messages,
            llm_router=llm_router,
        )
        if episode is not None:
            return episode

    # Rule-based fallback
    return _compress_fallback(
        session_id=session_id,
        user_id=user_id,
        messages=messages,
    )


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------

async def _compress_with_llm(
    *,
    session_id: str,
    user_id: str,
    messages: List[Dict[str, Any]],
    llm_router: Any,
) -> Optional[Episode]:
    """Try to compress via LLM. Returns ``None`` on any error."""
    try:
        from genus.llm.models import LLMMessage, LLMRole
        from genus.llm.router import TaskType

        conversation_text = _format_messages(messages)

        llm_messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=_LLM_SYSTEM_PROMPT),
            LLMMessage(role=LLMRole.USER, content=conversation_text),
        ]

        response = await llm_router.complete(
            llm_messages,
            task_type=TaskType.SUMMARIZE,
            max_tokens=300,
            temperature=0.1,
        )

        data = json.loads(response.content)
        summary = str(data.get("summary", "")).strip()
        topics = [str(t) for t in data.get("topics", []) if t]

        if not summary:
            logger.warning("LLM returned empty summary, falling back")
            return None

        return Episode.create(
            user_id=user_id,
            summary=summary,
            topics=topics,
            session_ids=[session_id],
            message_count=len(messages),
            source="llm",
        )

    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM compression failed (%s), falling back to rule-based", exc)
        return None


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------

def _compress_fallback(
    *,
    session_id: str,
    user_id: str,
    messages: List[Dict[str, Any]],
) -> Episode:
    """Produce a rule-based Episode without any external calls."""
    user_messages = [
        m for m in messages
        if str(m.get("role", "")).lower() in ("user", "human")
    ]

    # Build a simple summary from the first few user messages
    sample = user_messages[:3]
    if sample:
        parts = []
        for m in sample:
            content = str(m.get("content", "")).strip()
            if content:
                parts.append(content[:120])
        summary = "Gesprächszusammenfassung: " + " | ".join(parts)
    else:
        # All assistant messages or empty
        sample = messages[:2]
        parts = [str(m.get("content", ""))[:80] for m in sample if m.get("content")]
        summary = "Gesprächszusammenfassung: " + " | ".join(parts) if parts else "Kein Inhalt."

    topics = _extract_topics(user_messages or messages)

    return Episode.create(
        user_id=user_id,
        summary=summary,
        topics=topics,
        session_ids=[session_id],
        message_count=len(messages),
        source="fallback",
    )


def _format_messages(messages: List[Dict[str, Any]]) -> str:
    """Format messages into a readable conversation string."""
    lines = []
    for m in messages:
        role = str(m.get("role", "unknown")).capitalize()
        content = str(m.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _extract_topics(messages: List[Dict[str, Any]], max_topics: int = 5) -> List[str]:
    """Extract likely topic words from messages using simple frequency analysis."""
    word_freq: Dict[str, int] = {}
    for m in messages:
        content = str(m.get("content", ""))
        for word in _WORD_PATTERN.findall(content):
            lower = word.lower()
            if lower not in _STOP_WORDS:
                word_freq[lower] = word_freq.get(lower, 0) + 1

    sorted_words = sorted(word_freq, key=lambda w: word_freq[w], reverse=True)
    return sorted_words[:max_topics]

"""
DevContextExtractor — Phase 13c

Converts a natural-language dev request + conversation history + user
profile into a structured :class:`DevRunContext` that the DevLoop can
use directly for richer planning.

Purely functional — no IO, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# DevRunContext
# ---------------------------------------------------------------------------


@dataclass
class DevRunContext:
    """Structured context for a DevLoop run derived from a conversation.

    Args:
        goal:                  The original user request (unchanged).
        requirements:          Derived requirements (from profile / conversation).
        constraints:           Hard constraints (from profile decisions).
        conversation_summary:  Last 5 messages as plain text.
    """

    goal: str
    requirements: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    conversation_summary: str = ""


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


def extract_dev_context(
    text: str,
    profile: Optional[Any] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> DevRunContext:
    """Extract a :class:`DevRunContext` from the current request context.

    Args:
        text:                  The user's dev request text.
        profile:               Optional UserProfile (genus.identity.models).
        conversation_history:  List of role/content dicts (from ConversationMemory).

    Returns:
        A fully populated :class:`DevRunContext`.
    """
    requirements: List[str] = []
    constraints: List[str] = []

    # ── Requirements: active projects give useful context ───────────────────
    if profile is not None:
        projects = getattr(profile, "projects", [])
        if projects:
            requirements.append(
                f"Kontext: Nutzer arbeitet an: {', '.join(projects)}"
            )

    # ── Constraints: known decisions must not be violated ───────────────────
    if profile is not None:
        decisions = getattr(profile, "decisions", [])
        for d in decisions[-3:]:
            if isinstance(d, dict):
                entscheidung = d.get("entscheidung", "")
                grund = d.get("grund")
                if entscheidung:
                    if grund:
                        constraints.append(f"{entscheidung} (Grund: {grund})")
                    else:
                        constraints.append(entscheidung)
            elif d:
                constraints.append(str(d))

    # ── Conversation summary: last 5 messages ───────────────────────────────
    summary_lines: List[str] = []
    history = conversation_history or []
    for msg in history[-5:]:
        role = msg.get("role", "user")
        content = str(msg.get("content", ""))[:100]
        if role == "assistant":
            label = "GENUS"
        elif profile is not None:
            label = getattr(profile, "display_name", "User")
        else:
            label = "User"
        summary_lines.append(f"{label}: {content}")

    return DevRunContext(
        goal=text,
        requirements=requirements,
        constraints=constraints,
        conversation_summary="\n".join(summary_lines),
    )

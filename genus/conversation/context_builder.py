"""
ConversationContextBuilder — Phase 13c

Assembles a compact, LLM-ready context block from all available
information layers:

  Layer A — *who* is speaking  (UserProfile)
  Layer B — *where/who else*   (RoomContext, ResponsePolicy)
  Layer C — *what is happening* (SituationContext)

The result is a plain-text block inserted as a second SYSTEM message
before the conversation history, so the LLM always knows its audience.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from genus.conversation.situation import ActivityHint, SituationContext


# ---------------------------------------------------------------------------
# ConversationContext
# ---------------------------------------------------------------------------


@dataclass
class ConversationContext:
    """Aggregated context passed to :func:`build_llm_context_block`.

    All fields are optional so the builder degrades gracefully when
    only partial information is available.
    """

    profile: Optional[object] = None       # genus.identity.models.UserProfile
    room: Optional[object] = None          # genus.identity.models.RoomContext
    policy: Optional[object] = None        # genus.identity.models.ResponsePolicy
    situation: Optional[SituationContext] = None
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_llm_context_block(ctx: ConversationContext) -> str:
    """Build a compact, relevant context block for the LLM system prompt.

    Returns an empty string when there is nothing meaningful to add,
    so callers can skip the second SYSTEM message altogether.

    Layers injected (each only when data is present):
    - A: display_name, response_style, projects, decisions[-3:]
    - B: room guests, children, response policy restrictions
    - C: free_text situation, APPOINTMENT_SOON / COMMUTING / IN_MEETING
    - Time-of-day tone hint (morning 06–09, evening 21+)
    """
    parts: list[str] = []

    profile = ctx.profile
    room = ctx.room
    policy = ctx.policy
    situation = ctx.situation
    now = ctx.timestamp

    # ── Layer A: who is speaking ─────────────────────────────────────────────
    if profile is not None:
        display_name = getattr(profile, "display_name", None)
        if display_name:
            parts.append(f"Du sprichst mit: {display_name}")

        response_style = getattr(profile, "response_style", None)
        if response_style:
            parts.append(f"Antwortstil: {response_style}")

        interests = getattr(profile, "interests", [])
        if interests:
            parts.append(f"Interessen: {', '.join(interests)}")

        projects = getattr(profile, "projects", [])
        if projects:
            parts.append(f"Aktive Projekte: {', '.join(projects)}")

        decisions = getattr(profile, "decisions", [])
        if decisions:
            recent = decisions[-3:]
            decision_lines = []
            for d in recent:
                if isinstance(d, dict):
                    entscheidung = d.get("entscheidung", str(d))
                    grund = d.get("grund")
                    if grund:
                        decision_lines.append(f"  - {entscheidung} (Grund: {grund})")
                    else:
                        decision_lines.append(f"  - {entscheidung}")
                else:
                    decision_lines.append(f"  - {d}")
            if decision_lines:
                parts.append("Bekannte Entscheidungen:\n" + "\n".join(decision_lines))

    # ── Layer B: room / who else is present ─────────────────────────────────
    if room is not None:
        present = getattr(room, "present_user_ids", [])
        speaker = getattr(room, "speaker_user_id", None)
        speaker_id = getattr(profile, "user_id", None) if profile else None
        others = [uid for uid in present if uid != (speaker_id or speaker)]
        if others:
            parts.append(f"Anwesend: {', '.join(others)}")

        guest_count = getattr(room, "guest_count", 0)
        if guest_count:
            parts.append(f"Gäste im Raum: {guest_count}")

    if policy is not None:
        may_answer_aloud = getattr(policy, "may_answer_aloud", True)
        reason = getattr(policy, "reason", "")
        if not may_answer_aloud:
            suffix = f" (Grund: {reason})" if reason else ""
            parts.append(f"Antworte NUR schriftlich{suffix}")

    # ── Layer C: situational context ────────────────────────────────────────
    if situation is not None and not situation.is_stale():
        if situation.free_text:
            parts.append(f"Aktuelle Situation: {situation.free_text}")
        elif situation.location.value != "unknown":
            parts.append(f"Standort: {situation.location.value}")

        if situation.activity == ActivityHint.APPOINTMENT_SOON:
            appt = situation.next_appointment or "bald"
            parts.append(f"Termin: {appt}")
        elif situation.activity == ActivityHint.COMMUTING:
            parts.append("Nutzer ist unterwegs — kurze Antworten bevorzugen")
        elif situation.activity == ActivityHint.IN_MEETING:
            parts.append("Nutzer ist in einem Meeting — nur bei Wichtigem antworten")

    # ── Time-of-day hint ────────────────────────────────────────────────────
    hour = now.hour
    if 6 <= hour < 9:
        parts.append("Tageszeit: Morgen — strukturierter, prägnanter Ton")
    elif hour >= 21:
        parts.append("Tageszeit: Abend — ruhiger, entspannter Ton")

    return "\n".join(parts)

"""
SituationContext — Phase 13c

TTL-aware, in-memory situational context.
GENUS knows where the user is and what is currently happening —
without any persistence (situations go stale quickly).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LocationHint(str, Enum):
    """Where the user currently is."""

    HOME = "home"
    COMMUTING = "commuting"
    WORK = "work"
    AWAY = "away"
    UNKNOWN = "unknown"


class ActivityHint(str, Enum):
    """What the user is currently doing."""

    FREE = "free"
    APPOINTMENT_SOON = "appointment_soon"
    IN_MEETING = "in_meeting"
    COMMUTING = "commuting"
    BUSY = "busy"


# ---------------------------------------------------------------------------
# SituationContext
# ---------------------------------------------------------------------------


@dataclass
class SituationContext:
    """Snapshot of what is currently going on for a specific user.

    Args:
        user_id:           The user this situation belongs to.
        location:          Coarse location hint.
        activity:          What the user is doing right now.
        next_appointment:  Free-text description, e.g. "in 30 Minuten: Zahnarzt".
        free_text:         User's own words, e.g. "fahre gerade nach hause".
        captured_at:       When this context was captured (UTC).
        ttl_minutes:       How long until this context is considered stale.
    """

    user_id: str
    location: LocationHint = LocationHint.UNKNOWN
    activity: ActivityHint = ActivityHint.FREE
    next_appointment: Optional[str] = None
    free_text: Optional[str] = None
    captured_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    ttl_minutes: int = 60

    def is_stale(self) -> bool:
        """Return True if this context has exceeded its TTL."""
        age = (datetime.now(timezone.utc) - self.captured_at).total_seconds()
        return age > self.ttl_minutes * 60


# ---------------------------------------------------------------------------
# SituationStore
# ---------------------------------------------------------------------------


class SituationStore:
    """In-memory, TTL-aware store for SituationContext objects.

    Never persistent — situations go stale and must be refreshed.
    Thread-safety is not guaranteed; designed for single-threaded async use.
    """

    def __init__(self) -> None:
        self._store: Dict[str, SituationContext] = {}

    def update(self, ctx: SituationContext) -> None:
        """Store or replace the situation for *ctx.user_id*."""
        self._store[ctx.user_id] = ctx

    def get(self, user_id: str) -> Optional[SituationContext]:
        """Return the situation for *user_id*, or None if absent/stale."""
        ctx = self._store.get(user_id)
        if ctx is None:
            return None
        if ctx.is_stale():
            del self._store[user_id]
            return None
        return ctx

    def clear(self, user_id: str) -> None:
        """Remove the situation for *user_id* (no-op if not present)."""
        self._store.pop(user_id, None)

"""
Outcome payload – pure tool-layer module (no IO, no MessageBus dependency).

Provides:
- ``OutcomePayload`` – validated dataclass for ``outcome.recorded`` events.
- ``validate_outcome_payload(payload)`` – enforce contract and return
  an :class:`OutcomePayload`.

Contract (outcome.recorded payload):
    outcome      : "good" | "bad" | "unknown"  (required)
    score_delta  : float, clamped to [-10.0, 10.0]  (required)
    notes        : optional str; stripped; max 256 chars
    source       : optional str; stripped; max 64 chars; default "user"
    timestamp    : optional ISO-8601 str; validated but not parsed here
                   (the CLI sets it to now() when absent)

``run_id`` is carried exclusively in ``Message.metadata["run_id"]`` and
must NOT appear inside the payload dict.
"""

from dataclasses import dataclass
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTCOME_VALUES = frozenset({"good", "bad", "unknown"})
SCORE_DELTA_MIN = -10.0
SCORE_DELTA_MAX = 10.0
NOTES_MAX_LEN = 256
SOURCE_MAX_LEN = 64
SOURCE_DEFAULT = "user"


# ---------------------------------------------------------------------------
# OutcomePayload
# ---------------------------------------------------------------------------

@dataclass
class OutcomePayload:
    """Validated payload for an ``outcome.recorded`` message.

    All fields have already been validated/clamped/stripped by
    :func:`validate_outcome_payload` before this object is created.

    Attributes:
        outcome:     One of ``"good"``, ``"bad"``, ``"unknown"``.
        score_delta: Float in ``[-10.0, 10.0]``; clamped automatically.
        notes:       Optional free-text annotation; stripped; max 256 chars.
        source:      Who provided the outcome; stripped; max 64 chars;
                     defaults to ``"user"``.
        timestamp:   Optional ISO-8601 string (set by CLI if absent).
    """

    outcome: str
    score_delta: float
    notes: Optional[str]
    source: str
    timestamp: Optional[str]

    def to_message_payload(self) -> Dict[str, object]:
        """Return a plain dict suitable for ``Message.payload``.

        Only non-None optional fields are included so consumers can
        detect absence via normal ``dict.get()`` checks.
        """
        result: Dict[str, object] = {
            "outcome": self.outcome,
            "score_delta": self.score_delta,
            "source": self.source,
        }
        if self.notes is not None:
            result["notes"] = self.notes
        if self.timestamp is not None:
            result["timestamp"] = self.timestamp
        return result


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_outcome_payload(payload: dict) -> OutcomePayload:
    """Validate *payload* and return a :class:`OutcomePayload`.

    Raises:
        ValueError: If any required field is missing or has an invalid value.
        TypeError:  If *payload* is not a dict.
    """
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")

    # --- outcome -----------------------------------------------------------
    raw_outcome = payload.get("outcome")
    if raw_outcome is None:
        raise ValueError("'outcome' is required")
    if not isinstance(raw_outcome, str):
        raise ValueError("'outcome' must be a string")
    outcome = raw_outcome.strip().lower()
    if outcome not in OUTCOME_VALUES:
        raise ValueError(
            f"'outcome' must be one of {sorted(OUTCOME_VALUES)!r}, got {raw_outcome!r}"
        )

    # --- score_delta -------------------------------------------------------
    raw_delta = payload.get("score_delta")
    if raw_delta is None:
        raise ValueError("'score_delta' is required")
    try:
        score_delta = float(raw_delta)
    except (TypeError, ValueError):
        raise ValueError("'score_delta' must be a number")
    # Clamp to allowed range
    score_delta = max(SCORE_DELTA_MIN, min(SCORE_DELTA_MAX, score_delta))

    # --- notes (optional) --------------------------------------------------
    raw_notes = payload.get("notes")
    notes: Optional[str] = None
    if raw_notes is not None:
        if not isinstance(raw_notes, str):
            raise ValueError("'notes' must be a string")
        notes = raw_notes.strip()
        if len(notes) > NOTES_MAX_LEN:
            raise ValueError(
                f"'notes' exceeds maximum length of {NOTES_MAX_LEN} characters "
                f"(got {len(notes)})"
            )
        if not notes:
            notes = None  # treat empty-after-strip as absent

    # --- source (optional) -------------------------------------------------
    raw_source = payload.get("source", SOURCE_DEFAULT)
    if not isinstance(raw_source, str):
        raise ValueError("'source' must be a string")
    source = raw_source.strip()
    if not source:
        source = SOURCE_DEFAULT
    if len(source) > SOURCE_MAX_LEN:
        raise ValueError(
            f"'source' exceeds maximum length of {SOURCE_MAX_LEN} characters "
            f"(got {len(source)})"
        )

    # --- timestamp (optional) ----------------------------------------------
    raw_ts = payload.get("timestamp")
    timestamp: Optional[str] = None
    if raw_ts is not None:
        if not isinstance(raw_ts, str):
            raise ValueError("'timestamp' must be a string")
        timestamp = raw_ts.strip()
        if not timestamp:
            timestamp = None

    return OutcomePayload(
        outcome=outcome,
        score_delta=score_delta,
        notes=notes,
        source=source,
        timestamp=timestamp,
    )

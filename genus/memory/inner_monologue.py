"""
InnerMonologue — Phase 15a

GENUS hinterlässt sich selbst kurze Notizen nach jedem Gespräch.
Diese Notizen beeinflussen den Ton des nächsten Gesprächs.

Eigenschaften:
- Eine Notiz pro User, max 280 Zeichen (Twitter-Prinzip: kurz und klar)
- Lebt 24 Stunden, dann automatisch abgelaufen
- Wird beim NightScheduler in die Episode überführt oder verworfen
- JSONL-basiert: var/inner_monologue/<user_id>.jsonl
- Kein LLM nötig — ConversationAgent setzt die Note nach dem Gespräch

Beispiel-Notizen:
  "Emma wirkte heute gestresst wegen der Schule. Morgen sanfter sein."
  "Papa hat das Solar-Thema wieder angesprochen — er ist ernsthaft dran."
  "Gutes Gespräch heute abend. Die Familie plant einen Ausflug."
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_NOTE_CHARS = 280
_NOTE_TTL_HOURS = 24
_DEFAULT_DIR = Path("var/inner_monologue")


@dataclass
class MonologueNote:
    """Eine einzelne innere Notiz von GENUS über einen User."""

    user_id: str
    note: str
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def is_expired(self) -> bool:
        """True wenn die Notiz älter als 24h ist."""
        age = datetime.now(timezone.utc) - self.created_at
        return age > timedelta(hours=_NOTE_TTL_HOURS)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MonologueNote":
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return cls(
            user_id=data.get("user_id", ""),
            note=data.get("note", ""),
            created_at=created_at or datetime.now(timezone.utc),
        )


class InnerMonologue:
    """Verwaltet GENUS' innere Notizen pro User.

    Eine Notiz pro User gleichzeitig. Neue Notiz überschreibt die alte.
    Abgelaufene Notizen werden beim Lesen ignoriert.
    """

    def __init__(self, base_dir: Path = _DEFAULT_DIR) -> None:
        self._base_dir = Path(base_dir)

    def set(self, user_id: str, note: str) -> MonologueNote:
        """Setzt eine neue Notiz für einen User.

        Args:
            user_id: Der User.
            note:    Die Notiz (max 280 Zeichen, wird gekürzt wenn nötig).

        Returns:
            Die gespeicherte MonologueNote.
        """
        note = note.strip()[:_MAX_NOTE_CHARS]
        entry = MonologueNote(user_id=user_id, note=note)
        self._write(entry)
        logger.info("InnerMonologue: note set for user=%s: %r", user_id, note[:60])
        return entry

    def get_current(self, user_id: str) -> Optional[str]:
        """Gibt die aktuelle (nicht abgelaufene) Notiz zurück.

        Returns:
            Die Notiz als String, oder None wenn keine/abgelaufen.
        """
        note = self._read_latest(user_id)
        if note is None or note.is_expired():
            return None
        return note.note

    def clear(self, user_id: str) -> None:
        """Löscht alle Notizen eines Users (z.B. nach Nacht-Komprimierung)."""
        path = self._file_path(user_id)
        if path.exists():
            try:
                path.unlink()
            except Exception as exc:  # noqa: BLE001
                logger.warning("InnerMonologue: failed to clear %s: %s", path, exc)

    def get_all_active(self) -> list[MonologueNote]:
        """Gibt alle aktiven (nicht abgelaufenen) Notizen zurück.

        Nützlich für NightScheduler: alle Notizen in Episodes überführen.
        """
        result = []
        if not self._base_dir.exists():
            return result
        for path in self._base_dir.glob("*.jsonl"):
            user_id = path.stem
            note = self._read_latest(user_id)
            if note and not note.is_expired():
                result.append(note)
        return result

    # ------------------------------------------------------------------

    def _write(self, note: MonologueNote) -> None:
        path = self._file_path(note.user_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(note.to_dict(), ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning("InnerMonologue: failed to write: %s", exc)

    def _read_latest(self, user_id: str) -> Optional[MonologueNote]:
        """Liest die letzte (neueste) Notiz aus dem JSONL."""
        path = self._file_path(user_id)
        if not path.exists():
            return None
        latest = None
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        latest = MonologueNote.from_dict(json.loads(line))
        except Exception as exc:  # noqa: BLE001
            logger.warning("InnerMonologue: failed to read %s: %s", path, exc)
        return latest

    def _file_path(self, user_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
        return self._base_dir / f"{safe}.jsonl"

"""
SemanticFactStore — Phase 14b

Append-only JSONL store for semantic facts (user preferences, decisions, etc.).
One file per user: ``var/facts/<user_id>_facts.jsonl``.

Last-write-wins when reading; conflict detection on write prevents silent
overwrites — callers must resolve explicitly via ``force_update()``.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_BASE_DIR = "var/facts"
_SAFE_PATTERN = re.compile(r"[^a-zA-Z0-9._-]")
_TRAVERSAL_PATTERN = re.compile(r"\.{2,}")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConflictDetectedError(Exception):
    """Raised when a fact already exists with a different value.

    Attributes:
        key:            The conflicting fact key.
        existing_value: The value already stored.
        new_value:      The value that was attempted to be stored.
    """

    def __init__(self, key: str, existing_value: str, new_value: str) -> None:
        super().__init__(
            f"Conflict for key {key!r}: existing={existing_value!r}, new={new_value!r}"
        )
        self.key = key
        self.existing_value = existing_value
        self.new_value = new_value


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SemanticFact:
    """A persistent, structured fact about a user.

    Args:
        fact_id:    Unique identifier (UUID).
        user_id:    Owner of this fact.
        key:        Fact key (e.g. ``"llm_preference"``).
        value:      Fact value (e.g. ``"ollama_lokal"``).
        source:     Where the fact came from (e.g. ``"ConversationAgent"``).
        created_at: UTC timestamp when first created.
        updated_at: UTC timestamp of the last update.
        notes:      Optional free-text annotation.
    """

    fact_id: str
    user_id: str
    key: str
    value: str
    source: str
    scope: str
    created_by: str
    created_at: str
    updated_at: str
    notes: Optional[str] = None

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict."""
        return {
            "fact_id": self.fact_id,
            "user_id": self.user_id,
            "key": self.key,
            "value": self.value,
            "source": self.source,
            "scope": self.scope,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SemanticFact":
        """Reconstruct a SemanticFact from a dict."""
        return cls(
            fact_id=data["fact_id"],
            user_id=data["user_id"],
            key=data["key"],
            value=data["value"],
            source=data.get("source", ""),
            scope=data.get("scope", ""),
            created_by=data.get("created_by", ""),
            created_at=data["created_at"],
            updated_at=data.get("updated_at", data["created_at"]),
            notes=data.get("notes"),
        )

    @classmethod
    def create(
        cls,
        user_id: str,
        key: str,
        value: str,
        source: str = "",
        notes: Optional[str] = None,
        scope: str = "",
        created_by: str = "",
    ) -> "SemanticFact":
        """Factory: create a new SemanticFact with generated UUID and current timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            fact_id=str(uuid.uuid4()),
            user_id=user_id,
            key=key,
            value=value,
            source=source,
            scope=scope,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            notes=notes,
        )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class SemanticFactStore:
    """Append-only JSONL store for SemanticFacts.

    One file per user: ``<base_dir>/<sanitised_user_id>_facts.jsonl``.

    Reading uses last-write-wins semantics — the last entry for a given
    ``(user_id, key)`` pair is authoritative. Writing raises
    :class:`ConflictDetectedError` when the stored value differs.

    Args:
        base_dir: Directory for fact files. Defaults to ``var/facts``.
    """

    def __init__(self, base_dir: str = _DEFAULT_BASE_DIR) -> None:
        self._base_dir = Path(base_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert(self, fact: SemanticFact) -> SemanticFact:
        """Store *fact*, raising :class:`ConflictDetectedError` if a different value exists.

        If the key does not yet exist, or the existing value equals the new
        value, the fact is appended and returned unchanged.

        Raises:
            ConflictDetectedError: When an entry with the same key but a
                different value already exists.
        """
        existing = self.get(fact.user_id, fact.key, scope=fact.scope)
        if existing is not None and existing.value != fact.value:
            raise ConflictDetectedError(
                key=fact.key,
                existing_value=existing.value,
                new_value=fact.value,
            )
        return self._append(fact)

    def force_update(self, fact: SemanticFact) -> SemanticFact:
        """Overwrite *fact* unconditionally, without conflict checking."""
        now = datetime.now(timezone.utc).isoformat()
        updated = SemanticFact(
            fact_id=fact.fact_id,
            user_id=fact.user_id,
            key=fact.key,
            value=fact.value,
            source=fact.source,
            scope=fact.scope,
            created_by=fact.created_by,
            created_at=fact.created_at,
            updated_at=now,
            notes=fact.notes,
        )
        return self._append(updated)

    def get(self, user_id: str, key: str, scope: Optional[str] = None) -> Optional[SemanticFact]:
        """Return the most recent fact for *(user_id, key)*, or ``None``."""
        all_facts = self.get_all(user_id, scope=scope)
        return all_facts.get(key)

    def get_all(self, user_id: str, scope: Optional[str] = None) -> Dict[str, SemanticFact]:
        """Return all facts for *user_id* as ``{key: SemanticFact}``.

        Last-write-wins: later entries override earlier ones.
        Returns an empty dict when no file exists.
        """
        path = self._file_path(user_id)
        if not path.exists():
            return {}

        result: Dict[str, SemanticFact] = {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        fact = SemanticFact.from_dict(json.loads(line))
                        if scope is not None and fact.scope != scope:
                            continue
                        result[fact.key] = fact  # last-write-wins
                    except (json.JSONDecodeError, KeyError) as exc:
                        logger.warning("Skipping malformed fact line: %s", exc)
        except OSError as exc:
            logger.warning("Could not read fact file %s: %s", path, exc)

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append(self, fact: SemanticFact) -> SemanticFact:
        path = self._file_path(fact.user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(fact.to_dict(), ensure_ascii=False) + "\n")
        return fact

    def _file_path(self, user_id: str) -> Path:
        """Return the sanitised file path for *user_id*."""
        safe = _SAFE_PATTERN.sub("_", user_id)
        safe = _TRAVERSAL_PATTERN.sub("_", safe)
        return self._base_dir / f"{safe}_facts.jsonl"

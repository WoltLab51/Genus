"""
EpisodeStore — Phase 14b

Append-only JSONL store for episodic memory. One file per user under
``var/episodes/<user_id>.jsonl``. Each line is a serialised Episode.

Episodes are created by the NightScheduler which compresses conversation
sessions into compact summaries that GENUS can recall later.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_BASE_DIR = "var/episodes"
_SAFE_PATTERN = re.compile(r"[^a-zA-Z0-9._-]")
_TRAVERSAL_PATTERN = re.compile(r"\.{2,}")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Episode:
    """A compressed summary of one or more conversation sessions.

    Args:
        episode_id:    Unique identifier (UUID).
        user_id:       Owner of this episode.
        summary:       Human-readable summary of the conversation.
        topics:        List of topic tags extracted from the conversation.
        session_ids:   IDs of the sessions that were compressed into this episode.
        created_at:    UTC timestamp of creation.
        message_count: Total number of messages that were compressed.
        source:        ``"llm"`` when produced by an LLM call, ``"fallback"``
                       when produced by rule-based fallback logic.
    """

    episode_id: str
    user_id: str
    summary: str
    topics: List[str]
    session_ids: List[str]
    created_at: str
    message_count: int
    source: str  # "llm" | "fallback"

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict."""
        return {
            "episode_id": self.episode_id,
            "user_id": self.user_id,
            "summary": self.summary,
            "topics": list(self.topics),
            "session_ids": list(self.session_ids),
            "created_at": self.created_at,
            "message_count": self.message_count,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Episode":
        """Reconstruct an Episode from a dict (e.g. parsed from JSONL)."""
        return cls(
            episode_id=data["episode_id"],
            user_id=data["user_id"],
            summary=data["summary"],
            topics=list(data.get("topics", [])),
            session_ids=list(data.get("session_ids", [])),
            created_at=data["created_at"],
            message_count=int(data.get("message_count", 0)),
            source=data.get("source", "fallback"),
        )

    @classmethod
    def create(
        cls,
        user_id: str,
        summary: str,
        topics: List[str],
        session_ids: List[str],
        message_count: int,
        source: str = "fallback",
    ) -> "Episode":
        """Factory: create a new Episode with a generated UUID and current UTC timestamp."""
        return cls(
            episode_id=str(uuid.uuid4()),
            user_id=user_id,
            summary=summary,
            topics=topics,
            session_ids=session_ids,
            created_at=datetime.now(timezone.utc).isoformat(),
            message_count=message_count,
            source=source,
        )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class EpisodeStore:
    """Append-only JSONL store for Episodes.

    One file per user: ``<base_dir>/<sanitised_user_id>.jsonl``.

    Args:
        base_dir: Directory for episode files. Defaults to ``var/episodes``.
    """

    def __init__(self, base_dir: str = _DEFAULT_BASE_DIR) -> None:
        self._base_dir = Path(base_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, episode: Episode) -> None:
        """Persist *episode* by appending it to the user's JSONL file."""
        path = self._file_path(episode.user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(episode.to_dict(), ensure_ascii=False) + "\n")

    def get_recent(self, user_id: str, limit: int = 5) -> List[Episode]:
        """Return the *limit* most recent episodes for *user_id*.

        Returns an empty list when no file exists yet.
        """
        path = self._file_path(user_id)
        if not path.exists():
            return []

        episodes: List[Episode] = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        episodes.append(Episode.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, KeyError) as exc:
                        logger.warning("Skipping malformed episode line: %s", exc)
        except OSError as exc:
            logger.warning("Could not read episode file %s: %s", path, exc)
            return []

        return episodes[-limit:]

    def search(
        self,
        user_id: str,
        keywords: List[str],
        limit: int = 3,
    ) -> List[Episode]:
        """Return up to *limit* episodes whose summary or topics contain any keyword.

        Matching is case-insensitive substring search.
        Returns ``[]`` when there are no matches.
        """
        path = self._file_path(user_id)
        if not path.exists():
            return []

        lower_keywords = [kw.lower() for kw in keywords]
        matches: List[Episode] = []

        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        episode = Episode.from_dict(json.loads(line))
                    except (json.JSONDecodeError, KeyError) as exc:
                        logger.warning("Skipping malformed episode line: %s", exc)
                        continue

                    searchable = episode.summary.lower() + " " + " ".join(
                        t.lower() for t in episode.topics
                    )
                    if any(kw in searchable for kw in lower_keywords):
                        matches.append(episode)
        except OSError as exc:
            logger.warning("Could not read episode file %s: %s", path, exc)
            return []

        return matches[-limit:]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _file_path(self, user_id: str) -> Path:
        """Return the sanitised file path for *user_id*."""
        safe = _SAFE_PATTERN.sub("_", user_id)
        safe = _TRAVERSAL_PATTERN.sub("_", safe)
        return self._base_dir / f"{safe}.jsonl"

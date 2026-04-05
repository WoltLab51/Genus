"""
JSONL EventStore – append-only file-per-run implementation.

Storage layout::

    <base_dir>/<safe_run_id>.jsonl

``base_dir`` defaults to ``var/events/`` and can be overridden via the
``GENUS_EVENTSTORE_DIR`` environment variable.

Each line in the file is a UTF-8 encoded JSON object representing one
:class:`EventEnvelope`.

Thread / process safety:
    This implementation uses ``open(..., "a")`` which is atomic on POSIX
    for small writes.  For this milestone (single-process, single-thread
    async usage) this is sufficient.
"""

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from genus.memory.event_store import EventStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_BASE_DIR = "var/events"
_ENV_VAR = "GENUS_EVENTSTORE_DIR"

# Allowed characters after sanitisation – alphanumeric, hyphen, underscore, dot
_SAFE_PATTERN = re.compile(r"[^a-zA-Z0-9._-]")
# Reject filenames that would escape the directory
_TRAVERSAL_PATTERN = re.compile(r"\.\.")


# ---------------------------------------------------------------------------
# EventEnvelope
# ---------------------------------------------------------------------------

@dataclass
class EventEnvelope:
    """Immutable record of a single persisted event.

    Attributes:
        timestamp:  UTC datetime when the envelope was created.
        run_id:     GENUS run identifier (see :mod:`genus.core.run`).
        topic:      Message bus topic (e.g. ``"quality.scored"``).
        sender_id:  Agent / component that published the message.
        payload:    Arbitrary JSON-serialisable payload dict.
        metadata:   Arbitrary JSON-serialisable metadata dict.
    """

    timestamp: str  # ISO-8601 UTC string
    run_id: str
    topic: str
    sender_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_message(
        cls,
        message: Any,
        run_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> "EventEnvelope":
        """Build an :class:`EventEnvelope` from a
        :class:`~genus.communication.message_bus.Message`.

        Args:
            message:        The :class:`Message` to wrap.
            run_id:         Overrides the run_id; falls back to
                            ``message.metadata.get("run_id")``.
            extra_metadata: Additional key-value pairs merged into
                            ``metadata`` (e.g. diagnostic flags).

        Returns:
            A new :class:`EventEnvelope`.
        """
        meta = dict(message.metadata) if message.metadata else {}
        if extra_metadata:
            meta.update(extra_metadata)

        resolved_run_id: str
        if run_id is not None:
            resolved_run_id = run_id
        else:
            resolved_run_id = meta.get("run_id") or "unknown"

        payload = message.payload if isinstance(message.payload, dict) else {}

        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_id=resolved_run_id,
            topic=message.topic,
            sender_id=str(message.sender_id) if message.sender_id else "unknown",
            payload=payload,
            metadata=meta,
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict suitable for JSON serialisation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventEnvelope":
        """Reconstruct an :class:`EventEnvelope` from a plain dict.

        Unknown keys are silently ignored so that future envelope versions
        remain backwards-compatible with older readers.
        """
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Filename sanitisation
# ---------------------------------------------------------------------------

def sanitize_run_id(run_id: str) -> str:
    """Return a filesystem-safe filename stem for *run_id*.

    - Rejects / cleans path-traversal sequences (``..``).
    - Replaces any character outside ``[a-zA-Z0-9._-]`` with ``_``.
    - Ensures the result is non-empty (falls back to ``"unknown"``).

    Args:
        run_id: The raw run identifier.

    Returns:
        A sanitised string safe to use as a filename component.

    Raises:
        ValueError: If *run_id* contains path-traversal sequences
                    (``..``), to make the attack surface explicit.
    """
    if _TRAVERSAL_PATTERN.search(run_id):
        raise ValueError(
            f"run_id {run_id!r} contains path-traversal sequences and cannot be used as a filename"
        )
    safe = _SAFE_PATTERN.sub("_", run_id)
    return safe if safe else "unknown"


# ---------------------------------------------------------------------------
# JsonlEventStore
# ---------------------------------------------------------------------------

class JsonlEventStore(EventStore):
    """Append-only JSONL event store – one file per ``run_id``.

    The storage directory is resolved at construction time from:

    1. The explicit *base_dir* constructor argument (highest priority).
    2. The ``GENUS_EVENTSTORE_DIR`` environment variable.
    3. The hard-coded default ``var/events/``.

    Args:
        base_dir: Optional explicit path to the events directory.
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir: str = (
            base_dir
            or os.environ.get(_ENV_VAR)
            or _DEFAULT_BASE_DIR
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def base_dir(self) -> str:
        """The resolved base directory for event files."""
        return self._base_dir

    def append(self, envelope: EventEnvelope) -> None:
        """Append *envelope* as a single JSON line to the run's file.

        Creates the storage directory and file if they do not exist.

        Args:
            envelope: The :class:`EventEnvelope` to persist.
        """
        path = self._path_for(envelope.run_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        line = json.dumps(envelope.to_dict(), ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def iter(self, run_id: str) -> Iterator[EventEnvelope]:
        """Iterate over events for *run_id* in insertion order.

        If no file exists for *run_id*, the iterator yields nothing.

        Args:
            run_id: The run identifier to query.

        Yields:
            :class:`EventEnvelope` objects.
        """
        path = self._path_for(run_id)
        if not os.path.isfile(path):
            return
        with open(path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line)
                    yield EventEnvelope.from_dict(data)
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("Skipping malformed JSONL line in %s: %s", path, exc)

    def latest(
        self,
        run_id: str,
        topic: Optional[str] = None,
    ) -> Optional[EventEnvelope]:
        """Return the most-recently appended event for *run_id*.

        Args:
            run_id: The run identifier to query.
            topic:  If given, only consider events with this topic.

        Returns:
            The latest :class:`EventEnvelope`, or ``None``.
        """
        result: Optional[EventEnvelope] = None
        for envelope in self.iter(run_id):
            if topic is None or envelope.topic == topic:
                result = envelope
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path_for(self, run_id: str) -> str:
        """Return the full file path for the given *run_id*.

        Args:
            run_id: The run identifier (will be sanitised).

        Returns:
            Absolute-or-relative path string ending in ``.jsonl``.
        """
        safe = sanitize_run_id(run_id)
        return os.path.join(self._base_dir, f"{safe}.jsonl")

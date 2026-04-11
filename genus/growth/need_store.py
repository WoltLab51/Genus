"""
Need Store

Persistent storage for NeedRecords using an append-only JSONL log with
periodic JSON snapshots for fast restarts.

Storage layout::

    <base_dir>/needs.jsonl          — append-only log of all state changes
    <base_dir>/needs_snapshot.json  — last full state snapshot (for fast loading)

Loading strategy:
    1. If a snapshot exists: load it as base state and note the JSONL line count
       at the time the snapshot was written.
    2. Replay JSONL entries that were written *after* the snapshot (by skipping
       the first ``jsonl_line_count`` lines).
    3. If no snapshot exists: replay the entire JSONL from the beginning.

This ensures that ``load_all()`` always returns the correct, up-to-date state
without re-processing entries already captured by the snapshot.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from genus.growth.need_record import NeedRecord

logger = logging.getLogger(__name__)

_DEFAULT_BASE_DIR = "var/needs"
_JSONL_FILENAME = "needs.jsonl"
_SNAPSHOT_FILENAME = "needs_snapshot.json"


def _utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_from_dict(data: Dict[str, Any]) -> NeedRecord:
    """Reconstruct a :class:`~genus.growth.need_record.NeedRecord` from a stored dict.

    Args:
        data: A dict produced by :meth:`~genus.growth.need_record.NeedRecord.to_payload`
              or read from a JSONL/snapshot entry.

    Returns:
        A fully-populated :class:`~genus.growth.need_record.NeedRecord`.
    """
    return NeedRecord(
        need_id=data.get("need_id", ""),
        domain=data.get("domain", ""),
        need_description=data.get("need_description", ""),
        trigger_count=data.get("trigger_count", 0),
        first_seen_at=data.get("first_seen_at", ""),
        last_seen_at=data.get("last_seen_at", ""),
        status=data.get("status", "observed"),
        source_topics=list(data.get("source_topics", [])),
        metadata=dict(data.get("metadata", {})),
    )


class NeedStore:
    """Persistent storage for NeedRecords (JSONL append-only with snapshots).

    Storage layout::

        <base_dir>/needs.jsonl          — append-only log of all state changes
        <base_dir>/needs_snapshot.json  — last full state snapshot

    On load: snapshot is used as base state; JSONL entries written after the
    snapshot are replayed on top to reconstruct the current state.

    On save: records are appended to the JSONL log.  After every
    ``snapshot_interval`` writes a new snapshot is taken automatically.

    Args:
        base_dir: Directory for the storage files.  Default: ``var/needs/``.
        snapshot_interval: Number of writes between automatic snapshots.
            Default: ``50``.
    """

    def __init__(
        self,
        base_dir: "str | Path" = _DEFAULT_BASE_DIR,
        snapshot_interval: int = 50,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._jsonl_path = self._base_dir / _JSONL_FILENAME
        self._snapshot_path = self._base_dir / _SNAPSHOT_FILENAME
        self._snapshot_interval = snapshot_interval
        self._write_count: int = 0
        # In-memory state — populated by load_all() or incrementally by save().
        self._state: Dict[Tuple[str, str], NeedRecord] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, record: NeedRecord) -> None:
        """Save or update a NeedRecord (append-only upsert in JSONL).

        Also updates the in-memory state and triggers a snapshot after every
        ``snapshot_interval`` writes.

        Args:
            record: The :class:`~genus.growth.need_record.NeedRecord` to persist.
        """
        key = (record.domain, record.need_description)
        self._state[key] = record
        entry: Dict[str, Any] = {"event": "upsert", **record.to_payload()}
        self._append_jsonl(entry)
        self._write_count += 1
        if self._write_count >= self._snapshot_interval:
            self.snapshot()

    def load_all(self) -> Dict[Tuple[str, str], NeedRecord]:
        """Load all active NeedRecords.

        Combines the latest snapshot (if any) with JSONL entries written after
        the snapshot to produce the current state.

        Returns:
            A dict mapping ``(domain, need_description)`` tuples to
            :class:`~genus.growth.need_record.NeedRecord` instances.
            Returns an empty dict when no persisted data exists.
        """
        state: Dict[Tuple[str, str], NeedRecord] = {}
        skip_lines: int = 0

        # 1. Try loading the snapshot as base state.
        if self._snapshot_path.exists():
            try:
                raw = self._snapshot_path.read_text(encoding="utf-8")
                snap = json.loads(raw)
                skip_lines = int(snap.get("jsonl_line_count", 0))
                for record_data in snap.get("records", []):
                    record = _record_from_dict(record_data)
                    state[(record.domain, record.need_description)] = record
            except (json.JSONDecodeError, KeyError, ValueError):
                logger.warning(
                    "NeedStore: corrupted snapshot at %s — falling back to full JSONL replay",
                    self._snapshot_path,
                )
                state = {}
                skip_lines = 0

        # 2. Replay JSONL entries written after the snapshot.
        if self._jsonl_path.exists():
            try:
                with open(self._jsonl_path, encoding="utf-8") as fh:
                    for line_idx, raw_line in enumerate(fh):
                        if line_idx < skip_lines:
                            continue
                        raw_line = raw_line.strip()
                        if not raw_line:
                            continue
                        try:
                            entry = json.loads(raw_line)
                            self._apply_entry(state, entry)
                        except (json.JSONDecodeError, KeyError):
                            logger.warning(
                                "NeedStore: skipping malformed JSONL line %d", line_idx
                            )
            except OSError as exc:
                logger.error("NeedStore: could not read %s: %s", self._jsonl_path, exc)

        self._state = state
        return dict(state)

    def dismiss(self, domain: str, need_description: str) -> None:
        """Mark a need as dismissed (writes a dismiss event to JSONL).

        The need is removed from the in-memory state and a ``dismiss`` event is
        appended to the JSONL log so that subsequent :meth:`load_all` calls will
        not include this need.

        Args:
            domain: The domain of the need to dismiss.
            need_description: The need description of the need to dismiss.
        """
        key = (domain, need_description)
        self._state.pop(key, None)
        entry: Dict[str, Any] = {
            "event": "dismiss",
            "domain": domain,
            "need_description": need_description,
            "timestamp": _utc_now(),
        }
        self._append_jsonl(entry)
        self._write_count += 1
        if self._write_count >= self._snapshot_interval:
            self.snapshot()

    def snapshot(self) -> None:
        """Write the current state as a JSON snapshot for fast re-loading.

        The snapshot records the number of JSONL lines at the time it was
        written so that :meth:`load_all` can skip those lines and only replay
        entries written after the snapshot.
        """
        # Count actual lines in the JSONL to record the correct offset.
        line_count: int = 0
        if self._jsonl_path.exists():
            try:
                with open(self._jsonl_path, "rb") as fh:
                    line_count = sum(1 for _ in fh)
            except OSError as exc:
                logger.warning("NeedStore: could not count JSONL lines: %s", exc)

        records: List[Dict[str, Any]] = [
            record.to_payload() for record in self._state.values()
        ]
        snap_data: Dict[str, Any] = {
            "snapshot_at": _utc_now(),
            "jsonl_line_count": line_count,
            "records": records,
        }
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            self._snapshot_path.write_text(
                json.dumps(snap_data, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            logger.error("NeedStore: could not write snapshot: %s", exc)

        self._write_count = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append_jsonl(self, entry: Dict[str, Any]) -> None:
        """Append a single JSON entry to the JSONL log.

        Creates ``base_dir`` and the JSONL file if they do not yet exist.

        Args:
            entry: The dict to serialise and append.
        """
        self._base_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._jsonl_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.error("NeedStore: could not write to JSONL: %s", exc)

    @staticmethod
    def _apply_entry(
        state: Dict[Tuple[str, str], NeedRecord], entry: Dict[str, Any]
    ) -> None:
        """Apply a single JSONL entry to the given state dict (in-place).

        Args:
            state: The state dict to mutate.
            entry: A decoded JSONL entry with an ``event`` field.
        """
        event = entry.get("event")
        domain = entry.get("domain", "")
        need_desc = entry.get("need_description", "")
        key = (domain, need_desc)

        if event == "upsert":
            state[key] = _record_from_dict(entry)
        elif event == "dismiss":
            state.pop(key, None)

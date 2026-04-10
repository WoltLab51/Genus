"""
Quality History

Provides the ``QualityHistory`` class that persists ``GateResult`` entries
to a JSONL file and offers trend analysis helpers.

In the GENUS growth flow this module sits between the ``QualityGate``
(produces results) and the ``GrowthOrchestrator`` (consumes trend signals).
Storage is append-only (one JSON object per line) — the same convention used
by ``JsonlRunStore`` — so data is never overwritten.

Default storage path: ``~/.genus/quality_history.jsonl``
Override via the ``path`` constructor argument.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from genus.quality.gate import GateResult, GateVerdict


def _result_to_dict(result: GateResult) -> dict:
    """Serialize a GateResult to a plain dict for JSONL storage."""
    d = asdict(result)
    # Enum → string
    d["verdict"] = result.verdict.value
    return d


def _dict_to_result(d: dict) -> GateResult:
    """Deserialize a plain dict (from JSONL) back to a GateResult."""
    verdict = GateVerdict(d["verdict"])
    return GateResult(
        verdict=verdict,
        total_score=d["total_score"],
        dimension_scores=d["dimension_scores"],
        failed_dimensions=d["failed_dimensions"],
        reasons=d["reasons"],
        run_id=d.get("run_id"),
        evaluated_at=d.get("evaluated_at", ""),
    )


_DEFAULT_PATH = Path.home() / ".genus" / "quality_history.jsonl"


class QualityHistory:
    """Persistent, append-only store for QualityGate results.

    Each call to ``record()`` appends a single JSON line to the backing file.
    Reads iterate the file from the beginning, so the store is safe for
    concurrent readers (no locking is required for append-only writes on POSIX
    systems for lines shorter than PIPE_BUF).

    Args:
        path: Path to the JSONL file.  Defaults to
              ``~/.genus/quality_history.jsonl``.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path: Path = Path(path) if path is not None else _DEFAULT_PATH

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, result: GateResult) -> None:
        """Append a GateResult entry to the history file.

        The write is atomic in the append-only sense: a single ``write()``
        call of a complete JSON line is issued.  The file and any missing
        parent directories are created automatically.

        Args:
            result: The GateResult to persist.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(_result_to_dict(result)) + "\n"
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def _load_all(self) -> List[GateResult]:
        """Read and deserialize all entries from the JSONL file."""
        if not self._path.exists():
            return []
        results: List[GateResult] = []
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(_dict_to_result(json.loads(line)))
                except (KeyError, ValueError, json.JSONDecodeError):
                    # Skip malformed lines (defensive reading)
                    continue
        return results

    def get_trend(self, last_n: int = 10) -> List[GateResult]:
        """Return the most recent *last_n* GateResult entries.

        Args:
            last_n: Maximum number of results to return (most recent first).

        Returns:
            A list of GateResult objects, oldest entry first within the
            returned slice.
        """
        all_results = self._load_all()
        return all_results[-last_n:]

    def average_score(self, last_n: int = 10) -> Optional[float]:
        """Compute the arithmetic mean of total_score for the last *last_n* entries.

        Args:
            last_n: Number of recent results to consider.

        Returns:
            The average total_score, or None if there are no recorded results.
        """
        entries = self.get_trend(last_n)
        if not entries:
            return None
        return sum(e.total_score for e in entries) / len(entries)

    def is_improving(self, last_n: int = 5) -> Optional[bool]:
        """Return whether quality is trending upward over the last *last_n* entries.

        The comparison splits the window into a first half and a second half.
        If the average score of the second half is strictly greater than that
        of the first half, the trend is improving.

        Args:
            last_n: Number of recent results to analyse.  When fewer than
                    *last_n* entries exist, ``None`` is returned.

        Returns:
            ``True`` if improving, ``False`` if not improving or flat,
            ``None`` if there are not enough data points.
        """
        entries = self.get_trend(last_n)
        if len(entries) < last_n:
            return None
        mid = len(entries) // 2
        first_half = entries[:mid]
        second_half = entries[mid:]
        avg_first = sum(e.total_score for e in first_half) / len(first_half)
        avg_second = sum(e.total_score for e in second_half) / len(second_half)
        return avg_second > avg_first

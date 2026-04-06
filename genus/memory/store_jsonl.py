"""
JSONL Run Store - Storage backend for Run Journal v1

Provides persistent storage for run journals and artifacts using a simple
file-based layout with JSONL for the journal and individual JSON files
for artifacts.

Storage Layout
--------------
<base_dir>/
    <run_id>/
        header.json          - RunHeader metadata
        journal.jsonl        - Append-only journal events
        artifacts/
            <artifact_id>.json  - Individual artifact records

Thread Safety
-------------
This implementation uses append mode for JSONL writes, which is atomic
on POSIX for small writes. Safe for single-process, single-thread async
usage (this milestone's scope).

Environment Variables
---------------------
GENUS_RUNSTORE_DIR: Override the default base directory (var/runs/)
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

from genus.memory.models import ArtifactRecord, JournalEvent, RunHeader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_BASE_DIR = "var/runs"
_ENV_VAR = "GENUS_RUNSTORE_DIR"

# Filesystem safety patterns
_SAFE_PATTERN = re.compile(r"[^a-zA-Z0-9._-]")
_TRAVERSAL_PATTERN = re.compile(r"\.\.")


# ---------------------------------------------------------------------------
# Filesystem utilities
# ---------------------------------------------------------------------------

def sanitize_run_id(run_id: str) -> str:
    """Return a filesystem-safe directory name for *run_id*.

    Args:
        run_id: The raw run identifier.

    Returns:
        A sanitized string safe to use as a directory name.

    Raises:
        ValueError: If *run_id* contains path-traversal sequences (``..``).
    """
    if _TRAVERSAL_PATTERN.search(run_id):
        raise ValueError(
            f"run_id {run_id!r} contains path-traversal sequences"
        )
    safe = _SAFE_PATTERN.sub("_", run_id)
    return safe if safe else "unknown"


# ---------------------------------------------------------------------------
# JsonlRunStore
# ---------------------------------------------------------------------------

class JsonlRunStore:
    """JSONL-based storage backend for Run Journals.

    Manages per-run directories containing:
    - header.json: Run metadata (RunHeader)
    - journal.jsonl: Append-only journal events (JournalEvent)
    - artifacts/: Individual artifact JSON files (ArtifactRecord)

    Args:
        base_dir: Optional explicit path to the runs directory.
                  Defaults to GENUS_RUNSTORE_DIR env var or var/runs/.
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir = Path(
            base_dir
            or os.environ.get(_ENV_VAR)
            or _DEFAULT_BASE_DIR
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def base_dir(self) -> Path:
        """The resolved base directory for all run storage."""
        return self._base_dir

    # ------------------------------------------------------------------
    # Run Header operations
    # ------------------------------------------------------------------

    def save_header(self, header: RunHeader) -> None:
        """Save or update the run header metadata.

        Creates the run directory if it doesn't exist.

        Args:
            header: The RunHeader to persist.
        """
        run_dir = self._run_dir(header.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        header_path = run_dir / "header.json"
        header_data = {
            "run_id": header.run_id,
            "created_at": header.created_at,
            "goal": header.goal,
            "repo_id": header.repo_id,
            "workspace_root": header.workspace_root,
            "meta": header.meta,
        }

        with open(header_path, "w", encoding="utf-8") as f:
            json.dump(header_data, f, ensure_ascii=False, indent=2)

    def load_header(self, run_id: str) -> Optional[RunHeader]:
        """Load the run header metadata.

        Args:
            run_id: The run identifier.

        Returns:
            The RunHeader if it exists, otherwise None.
        """
        header_path = self._run_dir(run_id) / "header.json"
        if not header_path.exists():
            return None

        with open(header_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return RunHeader(
            run_id=data["run_id"],
            created_at=data["created_at"],
            goal=data["goal"],
            repo_id=data.get("repo_id"),
            workspace_root=data.get("workspace_root"),
            meta=data.get("meta", {}),
        )

    # ------------------------------------------------------------------
    # Journal operations
    # ------------------------------------------------------------------

    def append_event(self, event: JournalEvent) -> None:
        """Append a journal event to the run's journal.

        Creates the run directory and journal file if needed.

        Args:
            event: The JournalEvent to append.
        """
        run_dir = self._run_dir(event.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        journal_path = run_dir / "journal.jsonl"
        event_data = {
            "ts": event.ts,
            "run_id": event.run_id,
            "phase": event.phase,
            "event_type": event.event_type,
            "phase_id": event.phase_id,
            "summary": event.summary,
            "data": event.data,
            "evidence": event.evidence,
        }

        line = json.dumps(event_data, ensure_ascii=False)
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def iter_events(self, run_id: str) -> Iterator[JournalEvent]:
        """Iterate over all journal events for a run in order.

        Args:
            run_id: The run identifier.

        Yields:
            JournalEvent objects in insertion order.
        """
        journal_path = self._run_dir(run_id) / "journal.jsonl"
        if not journal_path.exists():
            return

        with open(journal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    yield JournalEvent(
                        ts=data["ts"],
                        run_id=data["run_id"],
                        phase=data["phase"],
                        event_type=data["event_type"],
                        summary=data["summary"],
                        phase_id=data.get("phase_id"),
                        data=data.get("data", {}),
                        evidence=data.get("evidence", []),
                    )
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    logger.warning(
                        "Skipping malformed journal line in %s: %s",
                        journal_path,
                        exc,
                    )

    def list_events(self, run_id: str) -> List[JournalEvent]:
        """Return all journal events for a run as a list.

        Convenience wrapper around iter_events().

        Args:
            run_id: The run identifier.

        Returns:
            List of JournalEvent objects.
        """
        return list(self.iter_events(run_id))

    # ------------------------------------------------------------------
    # Artifact operations
    # ------------------------------------------------------------------

    def save_artifact(self, artifact: ArtifactRecord) -> str:
        """Save an artifact to storage.

        Args:
            artifact: The ArtifactRecord to persist.

        Returns:
            The artifact ID (filename without extension).
        """
        artifacts_dir = self._artifacts_dir(artifact.run_id)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Generate artifact ID from timestamp and type
        artifact_id = self._generate_artifact_id(
            artifact.saved_at,
            artifact.artifact_type,
        )
        artifact_path = artifacts_dir / f"{artifact_id}.json"

        artifact_data = {
            "run_id": artifact.run_id,
            "phase": artifact.phase,
            "phase_id": artifact.phase_id,
            "artifact_type": artifact.artifact_type,
            "payload": artifact.payload,
            "evidence": artifact.evidence,
            "saved_at": artifact.saved_at,
        }

        with open(artifact_path, "w", encoding="utf-8") as f:
            json.dump(artifact_data, f, ensure_ascii=False, indent=2)

        return artifact_id

    def load_artifact(self, run_id: str, artifact_id: str) -> Optional[ArtifactRecord]:
        """Load an artifact by its ID.

        Args:
            run_id: The run identifier.
            artifact_id: The artifact identifier (without .json extension).

        Returns:
            The ArtifactRecord if it exists, otherwise None.
        """
        artifact_path = self._artifacts_dir(run_id) / f"{artifact_id}.json"
        if not artifact_path.exists():
            return None

        with open(artifact_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return ArtifactRecord(
            run_id=data["run_id"],
            phase=data["phase"],
            artifact_type=data["artifact_type"],
            payload=data["payload"],
            saved_at=data["saved_at"],
            phase_id=data.get("phase_id"),
            evidence=data.get("evidence", []),
        )

    def list_artifacts(
        self,
        run_id: str,
        artifact_type: Optional[str] = None,
    ) -> List[str]:
        """List artifact IDs for a run, optionally filtered by type.

        Args:
            run_id: The run identifier.
            artifact_type: Optional filter by artifact type.

        Returns:
            List of artifact IDs (filenames without .json extension).
        """
        artifacts_dir = self._artifacts_dir(run_id)
        if not artifacts_dir.exists():
            return []

        artifact_ids = []
        for path in artifacts_dir.glob("*.json"):
            artifact_id = path.stem

            # Filter by type if requested
            if artifact_type is not None:
                artifact = self.load_artifact(run_id, artifact_id)
                if artifact is None or artifact.artifact_type != artifact_type:
                    continue

            artifact_ids.append(artifact_id)

        return sorted(artifact_ids)

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def run_exists(self, run_id: str) -> bool:
        """Check if a run directory exists.

        Args:
            run_id: The run identifier.

        Returns:
            True if the run directory exists, False otherwise.
        """
        return self._run_dir(run_id).exists()

    def list_runs(self) -> List[str]:
        """List all run IDs in the store.

        Returns:
            List of run_id strings.
        """
        if not self._base_dir.exists():
            return []

        runs = []
        for path in self._base_dir.iterdir():
            if path.is_dir():
                # Directory name is the sanitized run_id
                runs.append(path.name)

        return sorted(runs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_dir(self, run_id: str) -> Path:
        """Return the directory path for a run.

        Args:
            run_id: The run identifier (will be sanitized).

        Returns:
            Path to the run directory.
        """
        safe = sanitize_run_id(run_id)
        return self._base_dir / safe

    def _artifacts_dir(self, run_id: str) -> Path:
        """Return the artifacts directory path for a run.

        Args:
            run_id: The run identifier.

        Returns:
            Path to the artifacts directory.
        """
        return self._run_dir(run_id) / "artifacts"

    def _generate_artifact_id(self, timestamp: str, artifact_type: str) -> str:
        """Generate a unique artifact ID.

        Args:
            timestamp: ISO-8601 UTC timestamp.
            artifact_type: Type of the artifact.

        Returns:
            A filesystem-safe artifact identifier.
        """
        # Use timestamp and type to create a readable ID
        # Convert ISO timestamp to filesystem-safe format
        safe_ts = timestamp.replace(":", "-").replace(".", "-")
        safe_type = _SAFE_PATTERN.sub("_", artifact_type)
        return f"{safe_ts}__{safe_type}"

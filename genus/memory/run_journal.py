"""
Run Journal - High-level interface for managing run journals

Provides a convenient API for working with run journals, combining
the underlying store operations with helper methods for common patterns.
"""

from datetime import datetime, timezone
from typing import List, Optional

from genus.memory.models import ArtifactRecord, JournalEvent, RunHeader
from genus.memory.store_jsonl import JsonlRunStore


class RunJournal:
    """High-level interface for managing a single run's journal.

    Wraps a JsonlRunStore and provides convenient methods for
    common journal operations.

    Args:
        run_id: The run identifier.
        store: The underlying JsonlRunStore backend.
    """

    def __init__(self, run_id: str, store: JsonlRunStore) -> None:
        self.run_id = run_id
        self._store = store

    # ------------------------------------------------------------------
    # Header operations
    # ------------------------------------------------------------------

    def initialize(
        self,
        goal: str,
        repo_id: Optional[str] = None,
        workspace_root: Optional[str] = None,
        **meta,
    ) -> RunHeader:
        """Initialize the run with header metadata.

        Creates the run directory and saves the header.

        Args:
            goal: High-level description of the run's objective.
            repo_id: Optional repository identifier (e.g., "WoltLab51/Genus").
            workspace_root: Optional path to workspace root.
            **meta: Additional metadata as keyword arguments.

        Returns:
            The created RunHeader.
        """
        header = RunHeader(
            run_id=self.run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            goal=goal,
            repo_id=repo_id,
            workspace_root=workspace_root,
            meta=meta,
        )
        self._store.save_header(header)
        return header

    def get_header(self) -> Optional[RunHeader]:
        """Load the run header.

        Returns:
            The RunHeader if it exists, otherwise None.
        """
        return self._store.load_header(self.run_id)

    # ------------------------------------------------------------------
    # Journal event operations
    # ------------------------------------------------------------------

    def log_event(
        self,
        phase: str,
        event_type: str,
        summary: str,
        phase_id: Optional[str] = None,
        data: Optional[dict] = None,
        evidence: Optional[List[dict]] = None,
    ) -> JournalEvent:
        """Log a journal event.

        Args:
            phase: Current phase (e.g., "plan", "implement", "test").
            event_type: Event type (e.g., "started", "tool_used", "decision").
            summary: Human-readable event summary.
            phase_id: Optional phase instance identifier.
            data: Optional event payload.
            evidence: Optional evidence references.

        Returns:
            The created JournalEvent.
        """
        event = JournalEvent(
            ts=datetime.now(timezone.utc).isoformat(),
            run_id=self.run_id,
            phase=phase,
            event_type=event_type,
            summary=summary,
            phase_id=phase_id,
            data=data or {},
            evidence=evidence or [],
        )
        self._store.append_event(event)
        return event

    def log_phase_start(
        self,
        phase: str,
        phase_id: Optional[str] = None,
        **data,
    ) -> JournalEvent:
        """Log the start of a phase.

        Convenience method for logging phase start events.

        Args:
            phase: Phase name.
            phase_id: Optional phase instance identifier.
            **data: Additional event data as keyword arguments.

        Returns:
            The created JournalEvent.
        """
        return self.log_event(
            phase=phase,
            event_type="started",
            summary=f"Phase '{phase}' started",
            phase_id=phase_id,
            data=data,
        )

    def log_decision(
        self,
        phase: str,
        decision: str,
        phase_id: Optional[str] = None,
        evidence: Optional[List[dict]] = None,
        **data,
    ) -> JournalEvent:
        """Log a decision made during a phase.

        Args:
            phase: Current phase.
            decision: Description of the decision.
            phase_id: Optional phase instance identifier.
            evidence: Optional evidence supporting the decision.
            **data: Additional decision data.

        Returns:
            The created JournalEvent.
        """
        return self.log_event(
            phase=phase,
            event_type="decision",
            summary=decision,
            phase_id=phase_id,
            data=data,
            evidence=evidence or [],
        )

    def log_tool_use(
        self,
        phase: str,
        tool_name: str,
        phase_id: Optional[str] = None,
        **data,
    ) -> JournalEvent:
        """Log tool usage during a phase.

        Args:
            phase: Current phase.
            tool_name: Name of the tool used.
            phase_id: Optional phase instance identifier.
            **data: Additional tool usage data (e.g., args, result).

        Returns:
            The created JournalEvent.
        """
        return self.log_event(
            phase=phase,
            event_type="tool_used",
            summary=f"Used tool: {tool_name}",
            phase_id=phase_id,
            data={"tool_name": tool_name, **data},
        )

    def log_error(
        self,
        phase: str,
        error: str,
        phase_id: Optional[str] = None,
        **data,
    ) -> JournalEvent:
        """Log an error that occurred during a phase.

        Args:
            phase: Current phase.
            error: Error description.
            phase_id: Optional phase instance identifier.
            **data: Additional error data (e.g., exception type, traceback).

        Returns:
            The created JournalEvent.
        """
        return self.log_event(
            phase=phase,
            event_type="error",
            summary=error,
            phase_id=phase_id,
            data=data,
        )

    def get_events(
        self,
        phase: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[JournalEvent]:
        """Get journal events, optionally filtered.

        Args:
            phase: Optional filter by phase.
            event_type: Optional filter by event type.

        Returns:
            List of matching JournalEvent objects.
        """
        events = self._store.list_events(self.run_id)

        if phase is not None:
            events = [e for e in events if e.phase == phase]

        if event_type is not None:
            events = [e for e in events if e.event_type == event_type]

        return events

    # ------------------------------------------------------------------
    # Artifact operations
    # ------------------------------------------------------------------

    def save_artifact(
        self,
        phase: str,
        artifact_type: str,
        payload: dict,
        phase_id: Optional[str] = None,
        evidence: Optional[List[dict]] = None,
    ) -> str:
        """Save an artifact and log the event.

        Args:
            phase: Current phase.
            artifact_type: Type of artifact (e.g., "plan", "test_report").
            payload: The artifact content.
            phase_id: Optional phase instance identifier.
            evidence: Optional evidence references.

        Returns:
            The artifact ID.
        """
        artifact = ArtifactRecord(
            run_id=self.run_id,
            phase=phase,
            artifact_type=artifact_type,
            payload=payload,
            saved_at=datetime.now(timezone.utc).isoformat(),
            phase_id=phase_id,
            evidence=evidence or [],
        )

        artifact_id = self._store.save_artifact(artifact)

        # Log the artifact save event
        self.log_event(
            phase=phase,
            event_type="artifact_saved",
            summary=f"Saved artifact: {artifact_type}",
            phase_id=phase_id,
            data={"artifact_id": artifact_id, "artifact_type": artifact_type},
        )

        return artifact_id

    def load_artifact(self, artifact_id: str) -> Optional[ArtifactRecord]:
        """Load an artifact by ID.

        Args:
            artifact_id: The artifact identifier.

        Returns:
            The ArtifactRecord if it exists, otherwise None.
        """
        return self._store.load_artifact(self.run_id, artifact_id)

    def list_artifacts(
        self,
        artifact_type: Optional[str] = None,
    ) -> List[str]:
        """List artifact IDs, optionally filtered by type.

        Args:
            artifact_type: Optional filter by artifact type.

        Returns:
            List of artifact IDs.
        """
        return self._store.list_artifacts(self.run_id, artifact_type)

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def exists(self) -> bool:
        """Check if this run exists in the store.

        Returns:
            True if the run directory exists, False otherwise.
        """
        return self._store.run_exists(self.run_id)

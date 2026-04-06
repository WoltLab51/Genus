"""
Run Journal Models

Defines small, stable dataclasses for the Run Journal Store v1.
These models are JSON-serializable and completely decoupled from
other GENUS modules (no import cycles).

All timestamp fields use ISO-8601 UTC strings for maximum
interoperability.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RunHeader:
    """Header metadata for a GENUS run.

    Attributes:
        run_id:         Unique run identifier (see genus.core.run.new_run_id).
        created_at:     ISO-8601 UTC timestamp when the run was created.
        goal:           High-level description of the run's objective.
        repo_id:        Optional repository identifier (e.g., "WoltLab51/Genus").
        workspace_root: Optional path to the workspace root directory.
        meta:           Arbitrary JSON-serializable metadata.
    """

    run_id: str
    created_at: str
    goal: str
    repo_id: Optional[str] = None
    workspace_root: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JournalEvent:
    """Single append-only event in the run journal.

    Attributes:
        ts:         ISO-8601 UTC timestamp when the event occurred.
        run_id:     The run this event belongs to.
        phase:      Current phase (e.g., "plan", "implement", "test", "review", "fix", "orchestrator").
        event_type: Event classification (e.g., "started", "artifact_saved", "tool_used", "decision", "error").
        phase_id:   Optional identifier for the specific phase instance.
        summary:    Human-readable summary of the event.
        data:       Arbitrary JSON-serializable event payload.
        evidence:   List of evidence references (stored as dicts to avoid import cycles).
    """

    ts: str
    run_id: str
    phase: str
    event_type: str
    summary: str
    phase_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ArtifactRecord:
    """Record of an artifact saved during a run.

    Attributes:
        run_id:        The run this artifact belongs to.
        phase:         Phase that produced the artifact (e.g., "plan", "test", "review").
        artifact_type: Type of artifact (e.g., "plan", "test_report", "review", "patch").
        payload:       The artifact content (JSON-serializable).
        saved_at:      ISO-8601 UTC timestamp when the artifact was saved.
        phase_id:      Optional identifier for the specific phase instance.
        evidence:      List of evidence references supporting this artifact.
    """

    run_id: str
    phase: str
    artifact_type: str
    payload: Dict[str, Any]
    saved_at: str
    phase_id: Optional[str] = None
    evidence: List[Dict[str, Any]] = field(default_factory=list)

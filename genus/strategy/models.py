"""
Strategy Layer Data Models

Defines JSON-serializable dataclasses for strategy selection and learning.
These models are designed to be simple, stable, and decoupled from other
GENUS modules.

All timestamp fields use ISO-8601 UTC strings for maximum interoperability.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Playbook Identifiers
# ---------------------------------------------------------------------------

class PlaybookId:
    """String constants for playbook identifiers.

    These are the core strategies that GENUS can adopt when implementing
    or fixing code. Each playbook represents a different approach to
    achieving the goal.
    """

    TARGET_FAILING_TEST_FIRST = "target_failing_test_first"
    """Focus next iteration on fixing the specific failing test(s)."""

    MINIMIZE_CHANGESET = "minimize_changeset"
    """Reduce the scope of changes in next iteration."""

    INCREASE_TIMEOUT_ONCE = "increase_timeout_once"
    """Increase timeout and retry once (for timeout failures)."""

    ASK_OPERATOR_WITH_CONTEXT = "ask_operator_with_context"
    """Situation requires human intervention with full context."""

    DEFAULT = "default"
    """Default/standard approach without special constraints."""

    @classmethod
    def all_values(cls) -> List[str]:
        """Return all playbook identifier values."""
        return [
            cls.TARGET_FAILING_TEST_FIRST,
            cls.MINIMIZE_CHANGESET,
            cls.INCREASE_TIMEOUT_ONCE,
            cls.ASK_OPERATOR_WITH_CONTEXT,
            cls.DEFAULT,
        ]


# ---------------------------------------------------------------------------
# Strategy Decision
# ---------------------------------------------------------------------------

@dataclass
class StrategyDecision:
    """Record of a strategy selection decision.

    This captures what strategy was selected, why it was selected,
    and what context informed the decision. Logged to RunJournal
    for full traceability.

    Attributes:
        run_id: The run this decision applies to.
        phase: Current phase ("implement" or "fix").
        iteration: Iteration number within the phase (None for first iteration).
        selected_playbook: The playbook ID that was selected.
        candidates: List of candidate playbooks considered.
        reason: Human-readable explanation of why this playbook was selected.
        derived_from: Context that informed the decision (e.g., failure_class,
                     root_cause_hint, last_score, learned_preferences).
        created_at: ISO-8601 UTC timestamp when decision was made.
    """

    run_id: str
    phase: str  # "implement" or "fix"
    selected_playbook: str
    candidates: List[str]
    reason: str
    derived_from: Dict[str, Any]
    created_at: str
    iteration: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "run_id": self.run_id,
            "phase": self.phase,
            "iteration": self.iteration,
            "selected_playbook": self.selected_playbook,
            "candidates": self.candidates,
            "reason": self.reason,
            "derived_from": self.derived_from,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyDecision":
        """Create from dict."""
        return cls(
            run_id=data["run_id"],
            phase=data["phase"],
            iteration=data.get("iteration"),
            selected_playbook=data["selected_playbook"],
            candidates=data["candidates"],
            reason=data["reason"],
            derived_from=data["derived_from"],
            created_at=data["created_at"],
        )


# ---------------------------------------------------------------------------
# Strategy Profile
# ---------------------------------------------------------------------------

@dataclass
class StrategyProfile:
    """Named strategy profile with playbook weights.

    Profiles allow different configurations of strategy preferences.
    Weights determine playbook priority (higher wins). Default weight is 0.

    Attributes:
        name: Profile name (e.g., "default", "conservative", "aggressive").
        playbook_weights: Mapping from playbook_id to weight (int).
                         Higher weight = higher priority.
    """

    name: str
    playbook_weights: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "name": self.name,
            "playbook_weights": self.playbook_weights,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyProfile":
        """Create from dict."""
        return cls(
            name=data["name"],
            playbook_weights=data.get("playbook_weights", {}),
        )

    @classmethod
    def default_profile(cls) -> "StrategyProfile":
        """Create default profile with standard weights."""
        return cls(
            name="default",
            playbook_weights={
                PlaybookId.TARGET_FAILING_TEST_FIRST: 10,
                PlaybookId.MINIMIZE_CHANGESET: 5,
                PlaybookId.INCREASE_TIMEOUT_ONCE: 8,
                PlaybookId.DEFAULT: 0,
                PlaybookId.ASK_OPERATOR_WITH_CONTEXT: -10,  # last resort
            }
        )

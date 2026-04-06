"""
Meta Topic Constants

Defines the standard topic strings for GENUS meta-layer events.
Meta events are published after analysis and evaluation of runs.

These topics are separate from dev-loop topics to maintain clean separation
between the execution layer and the meta/learning layer.
"""

# ---------------------------------------------------------------------------
# Evaluation events
# ---------------------------------------------------------------------------
META_EVALUATION_COMPLETED = "meta.evaluation.completed"
"""Published when a run evaluation is completed and the artifact is saved."""

# ---------------------------------------------------------------------------
# Collection – single source of truth for all meta topics.
# ---------------------------------------------------------------------------
ALL_META_TOPICS = (
    META_EVALUATION_COMPLETED,
)

"""
Quality Dimensions

Defines the five canonical quality dimensions used by the QualityGate to
evaluate agent builds in the GENUS growth flow.  Each dimension carries a
weight (all weights sum to exactly 1.0), a minimum threshold below which the
dimension is considered "failed", and an optional hard-block threshold that
triggers an unconditional BLOCK verdict regardless of the total score.

In the GENUS flow this module sits between the scoring layer (e.g.
``QualityAgent``) and the gating layer (``QualityGate``).  Other modules
should import ``DIMENSIONS`` and ``DIMENSION_MAP`` rather than hardcoding
dimension names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class QualityDimension:
    """A single quality dimension used in gate evaluation.

    Attributes:
        name: Unique identifier for the dimension (used as dict key).
        weight: Contribution to the total score (all weights must sum to 1.0).
        min_threshold: Score below this value marks the dimension as "failed".
        hard_block_threshold: When set and the score is below this value, the
            gate issues a BLOCK verdict unconditionally, regardless of the
            total score.  Must be <= min_threshold when set.
        description: Human-readable explanation of what this dimension measures.
    """

    name: str
    weight: float
    min_threshold: float
    hard_block_threshold: Optional[float]
    description: str


# ---------------------------------------------------------------------------
# The five canonical GENUS quality dimensions
# ---------------------------------------------------------------------------

DIMENSIONS: List[QualityDimension] = [
    QualityDimension(
        name="test_coverage",
        weight=0.25,
        min_threshold=0.70,
        hard_block_threshold=0.50,
        description="Anteil des Codes, der durch Tests abgedeckt ist",
    ),
    QualityDimension(
        name="security_compliance",
        weight=0.25,
        min_threshold=0.90,
        hard_block_threshold=0.90,
        description="Einhaltung von Sicherheitsregeln (Kill-Switch, ACL, Sandbox)",
    ),
    QualityDimension(
        name="complexity_score",
        weight=0.20,
        min_threshold=0.60,
        hard_block_threshold=None,
        description="Umgekehrte Komplexität — einfacher = höherer Score",
    ),
    QualityDimension(
        name="feedback_history",
        weight=0.20,
        min_threshold=0.50,
        hard_block_threshold=None,
        description="Durchschnittlicher Outcome-Score aus vergangenen Runs",
    ),
    QualityDimension(
        name="stability_score",
        weight=0.10,
        min_threshold=0.40,
        hard_block_threshold=None,
        description="Zeitliche Stabilität — wie lange läuft der Agent ohne Fehler",
    ),
]

# Convenience map: dimension name → QualityDimension
DIMENSION_MAP: Dict[str, QualityDimension] = {d.name: d for d in DIMENSIONS}

# ---------------------------------------------------------------------------
# Invariant: weights must sum to exactly 1.0
# ---------------------------------------------------------------------------

assert abs(sum(d.weight for d in DIMENSIONS) - 1.0) < 1e-9, (
    "DIMENSIONS weights do not sum to 1.0: {!r}".format(
        [d.weight for d in DIMENSIONS]
    )
)

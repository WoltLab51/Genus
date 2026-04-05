"""
Quality Scorecard

Defines the QualityScorecard dataclass used to carry quality evaluation
results through the GENUS message bus.

The ``overall`` field is the single numeric quality score in the range
[0.0, 1.0] and maps to the ``quality_score`` field expected by
``DecisionAgent`` for backward compatibility.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class QualityScorecard:
    """Structured quality evaluation result.

    Attributes:
        overall:    Aggregate quality score in [0.0, 1.0].  This value is
                    published as ``quality_score`` in ``quality.scored``
                    messages so that ``DecisionAgent`` can consume it
                    without any changes.
        dimensions: Optional per-dimension scores (e.g.
                    ``{"completeness": 0.9, "accuracy": 0.85}``).
        evidence:   Optional list of evidence dicts describing how the
                    score was derived (e.g.
                    ``[{"source": "analysis_fallback", "note": "…"}]``).
    """

    overall: Optional[float]
    dimensions: Dict[str, float] = field(default_factory=dict)
    evidence: List[Dict] = field(default_factory=list)

    def to_payload(self) -> dict:
        """Return a plain dict suitable for ``Message.payload``.

        The ``quality_score`` key is included for backward compatibility
        with ``DecisionAgent``.
        """
        return {
            "quality_score": self.overall,
            "dimensions": dict(self.dimensions),
            "evidence": list(self.evidence),
        }

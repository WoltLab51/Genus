"""
Quality Gate

Provides the ``QualityGate`` class that evaluates a set of per-dimension
scores and returns a ``GateResult`` with a verdict of PASS, WARN, or BLOCK.

In the GENUS growth flow this module sits between the QualityHistory (trend
data) and the GrowthOrchestrator (build decision).  A BLOCK verdict prevents
a new agent from being deployed; a WARN verdict allows deployment with a
warning flag; a PASS verdict allows unconditional deployment.

Hard-block rules (unconditional BLOCK regardless of total score):
    - ``security_compliance < 0.90``
    - ``test_coverage < 0.50``

Score-based verdict thresholds:
    - ``total_score < 0.55``   → BLOCK
    - ``0.55 ≤ total_score < 0.70`` → WARN
    - ``total_score ≥ 0.70``   → PASS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from genus.quality.dimensions import DIMENSIONS, DIMENSION_MAP


class GateVerdict(Enum):
    """Possible outcomes of a QualityGate evaluation.

    Attributes:
        PASS: All thresholds met; deployment is unconditionally allowed.
        WARN: Total score is marginal (0.55–0.69); deployment allowed with
            a warning.
        BLOCK: Hard block or total score too low; deployment is prevented.
    """

    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


@dataclass
class GateResult:
    """Result of a single QualityGate evaluation.

    Attributes:
        verdict: The overall gate decision (PASS / WARN / BLOCK).
        total_score: Weighted aggregate score in the range [0.0, 1.0].
        dimension_scores: Per-dimension scores as provided to ``evaluate()``.
        failed_dimensions: Names of dimensions whose score is below their
            ``min_threshold``.
        reasons: Human-readable, reproducible explanations for every WARN or
            BLOCK trigger.  Always non-empty when verdict is WARN or BLOCK.
        run_id: Optional identifier of the run being evaluated.
        evaluated_at: ISO 8601 UTC timestamp of the evaluation.
    """

    verdict: GateVerdict
    total_score: float
    dimension_scores: Dict[str, float]
    failed_dimensions: List[str]
    reasons: List[str]
    run_id: Optional[str] = None
    evaluated_at: str = field(default_factory=lambda: "")


class QualityGate:
    """Evaluates per-dimension scores and returns a deterministic GateResult.

    The gate applies hard-block rules first (unconditional BLOCK regardless of
    total score), then falls back to score-based thresholds.  Every blocking
    or warning condition is recorded in ``GateResult.reasons`` so that
    downstream systems can display or log the cause.

    Usage::

        gate = QualityGate()
        result = gate.evaluate(
            scores={
                "test_coverage": 0.80,
                "security_compliance": 0.95,
                "complexity_score": 0.70,
                "feedback_history": 0.60,
                "stability_score": 0.50,
            },
            run_id="my-run-001",
        )
        if result.verdict == GateVerdict.BLOCK:
            print(result.reasons)
    """

    # Score-based verdict thresholds
    _BLOCK_THRESHOLD: float = 0.55
    _WARN_THRESHOLD: float = 0.70

    def evaluate(
        self,
        scores: Dict[str, float],
        run_id: Optional[str] = None,
    ) -> GateResult:
        """Evaluate dimension scores and return a GateResult.

        Args:
            scores: Mapping of dimension name to score in [0.0, 1.0].
                    Missing dimensions are treated as 0.0.
            run_id: Optional run identifier for traceability.

        Returns:
            A ``GateResult`` with a deterministic verdict, total score,
            failed dimensions, and human-readable reasons.
        """
        reasons: List[str] = []
        failed_dimensions: List[str] = []
        hard_block = False

        # ------------------------------------------------------------------
        # Compute weighted total score and collect failed dimensions
        # ------------------------------------------------------------------
        total_score: float = 0.0
        for dim in DIMENSIONS:
            raw = scores.get(dim.name, 0.0)
            total_score += raw * dim.weight
            if raw < dim.min_threshold:
                failed_dimensions.append(dim.name)

        # ------------------------------------------------------------------
        # Hard-block rules (checked against raw dimension scores)
        # ------------------------------------------------------------------
        for dim in DIMENSIONS:
            if dim.hard_block_threshold is None:
                continue
            raw = scores.get(dim.name, 0.0)
            if raw < dim.hard_block_threshold:
                hard_block = True
                reasons.append(
                    "Hard block: '{name}' score {score:.3f} is below the "
                    "mandatory threshold {threshold:.3f}.".format(
                        name=dim.name,
                        score=raw,
                        threshold=dim.hard_block_threshold,
                    )
                )

        # ------------------------------------------------------------------
        # Score-based threshold explanations (always recorded for audit)
        # ------------------------------------------------------------------
        for dim_name in failed_dimensions:
            dim = DIMENSION_MAP[dim_name]
            # Hard-block reasons are already added above; skip duplicates
            if dim.hard_block_threshold is not None and scores.get(dim_name, 0.0) < dim.hard_block_threshold:
                continue
            reasons.append(
                "Dimension '{name}' score {score:.3f} is below the minimum "
                "threshold {threshold:.3f}.".format(
                    name=dim_name,
                    score=scores.get(dim_name, 0.0),
                    threshold=dim.min_threshold,
                )
            )

        # ------------------------------------------------------------------
        # Determine verdict
        # ------------------------------------------------------------------
        if hard_block:
            verdict = GateVerdict.BLOCK
        elif total_score < self._BLOCK_THRESHOLD:
            verdict = GateVerdict.BLOCK
            reasons.append(
                "Total score {score:.3f} is below the block threshold "
                "{threshold:.3f}.".format(
                    score=total_score,
                    threshold=self._BLOCK_THRESHOLD,
                )
            )
        elif total_score < self._WARN_THRESHOLD:
            verdict = GateVerdict.WARN
            if not reasons:
                reasons.append(
                    "Total score {score:.3f} is in the warning range "
                    "[{low:.2f}, {high:.2f}).".format(
                        score=total_score,
                        low=self._BLOCK_THRESHOLD,
                        high=self._WARN_THRESHOLD,
                    )
                )
        else:
            verdict = GateVerdict.PASS

        evaluated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return GateResult(
            verdict=verdict,
            total_score=total_score,
            dimension_scores=dict(scores),
            failed_dimensions=failed_dimensions,
            reasons=reasons,
            run_id=run_id,
            evaluated_at=evaluated_at,
        )

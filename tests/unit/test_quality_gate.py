"""
Tests for genus.quality.gate (QualityGate)

Verifies:
- PASS when all dimensions are above threshold
- BLOCK via hard block on security_compliance < 0.90
- BLOCK via hard block on test_coverage < 0.50
- BLOCK when total_score < 0.55
- WARN when total_score is in [0.55, 0.70)
- reasons is never empty on BLOCK or WARN
- failed_dimensions contains the correct dimension names
"""

import pytest

from genus.quality.gate import GateVerdict, QualityGate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_passing_scores() -> dict:
    """Return scores where every dimension is comfortably above its threshold."""
    return {
        "test_coverage": 0.80,
        "security_compliance": 0.95,
        "complexity_score": 0.75,
        "feedback_history": 0.65,
        "stability_score": 0.60,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestQualityGate:
    def setup_method(self):
        self.gate = QualityGate()

    def test_pass_when_all_above_threshold(self):
        """All dimensions above threshold and good total → PASS."""
        result = self.gate.evaluate(_all_passing_scores())
        assert result.verdict == GateVerdict.PASS
        assert result.total_score >= 0.70
        assert result.failed_dimensions == []

    def test_block_security_compliance_hard_block(self):
        """security_compliance < 0.90 must always trigger BLOCK."""
        scores = _all_passing_scores()
        scores["security_compliance"] = 0.85  # below hard block of 0.90
        result = self.gate.evaluate(scores)
        assert result.verdict == GateVerdict.BLOCK
        assert len(result.reasons) > 0
        assert any("security_compliance" in r for r in result.reasons)

    def test_block_test_coverage_hard_block(self):
        """test_coverage < 0.50 must always trigger BLOCK."""
        scores = _all_passing_scores()
        scores["test_coverage"] = 0.45  # below hard block of 0.50
        result = self.gate.evaluate(scores)
        assert result.verdict == GateVerdict.BLOCK
        assert len(result.reasons) > 0
        assert any("test_coverage" in r for r in result.reasons)

    def test_hard_block_overrides_good_total_score(self):
        """Even if total score would be high, hard block must force BLOCK."""
        scores = {
            "test_coverage": 1.0,
            "security_compliance": 0.89,  # hard block threshold is 0.90
            "complexity_score": 1.0,
            "feedback_history": 1.0,
            "stability_score": 1.0,
        }
        result = self.gate.evaluate(scores)
        assert result.verdict == GateVerdict.BLOCK

    def test_block_when_total_score_below_055(self):
        """Low total score (no hard blocks) → BLOCK."""
        scores = {
            "test_coverage": 0.60,   # above hard block but contributes low
            "security_compliance": 0.90,
            "complexity_score": 0.30,
            "feedback_history": 0.10,
            "stability_score": 0.10,
        }
        result = self.gate.evaluate(scores)
        assert result.total_score < 0.55
        assert result.verdict == GateVerdict.BLOCK
        assert len(result.reasons) > 0

    def test_warn_when_total_score_between_055_and_070(self):
        """Total score in [0.55, 0.70) → WARN."""
        # Construct scores that land in WARN band without triggering hard blocks
        scores = {
            "test_coverage": 0.60,
            "security_compliance": 0.90,
            "complexity_score": 0.60,
            "feedback_history": 0.50,
            "stability_score": 0.40,
        }
        result = self.gate.evaluate(scores)
        assert 0.55 <= result.total_score < 0.70, (
            f"Expected WARN band, got total_score={result.total_score}"
        )
        assert result.verdict == GateVerdict.WARN
        assert len(result.reasons) > 0

    def test_reasons_not_empty_on_block(self):
        """GateResult.reasons must be non-empty for every BLOCK verdict."""
        scores = _all_passing_scores()
        scores["security_compliance"] = 0.50
        result = self.gate.evaluate(scores)
        assert result.verdict == GateVerdict.BLOCK
        assert len(result.reasons) > 0

    def test_reasons_not_empty_on_warn(self):
        """GateResult.reasons must be non-empty for every WARN verdict."""
        scores = {
            "test_coverage": 0.60,
            "security_compliance": 0.90,
            "complexity_score": 0.60,
            "feedback_history": 0.50,
            "stability_score": 0.40,
        }
        result = self.gate.evaluate(scores)
        if result.verdict == GateVerdict.WARN:
            assert len(result.reasons) > 0

    def test_failed_dimensions_correct(self):
        """failed_dimensions must list dimensions below their min_threshold."""
        scores = _all_passing_scores()
        scores["feedback_history"] = 0.40  # min_threshold is 0.50
        scores["stability_score"] = 0.30   # min_threshold is 0.40
        result = self.gate.evaluate(scores)
        assert "feedback_history" in result.failed_dimensions
        assert "stability_score" in result.failed_dimensions
        assert "test_coverage" not in result.failed_dimensions

    def test_run_id_propagated(self):
        """run_id passed to evaluate must appear in the GateResult."""
        result = self.gate.evaluate(_all_passing_scores(), run_id="test-run-42")
        assert result.run_id == "test-run-42"

    def test_evaluated_at_is_iso8601(self):
        """evaluated_at must be a non-empty ISO 8601 string."""
        result = self.gate.evaluate(_all_passing_scores())
        assert result.evaluated_at != ""
        # Basic format check: YYYY-MM-DDThh:mm:ssZ
        assert "T" in result.evaluated_at and result.evaluated_at.endswith("Z")

    def test_dimension_scores_preserved(self):
        """evaluate() must preserve all dimension scores in the result."""
        scores = _all_passing_scores()
        result = self.gate.evaluate(scores)
        for k, v in scores.items():
            assert result.dimension_scores[k] == pytest.approx(v)

    def test_missing_dimension_treated_as_zero(self):
        """A missing dimension score defaults to 0.0 and can trigger hard blocks."""
        # Omit security_compliance entirely → defaults to 0.0 → hard block
        scores = {
            "test_coverage": 0.80,
            "complexity_score": 0.75,
            "feedback_history": 0.65,
            "stability_score": 0.60,
        }
        result = self.gate.evaluate(scores)
        assert result.verdict == GateVerdict.BLOCK

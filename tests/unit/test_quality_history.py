"""
Tests for genus.quality.history (QualityHistory)

Verifies:
- record() + get_trend() roundtrip
- is_improving() → True when scores are rising
- is_improving() → False when scores are falling
- is_improving() → None when fewer than 5 entries
- average_score() correct calculation
"""

import pytest

from genus.quality.gate import GateResult, GateVerdict
from genus.quality.history import QualityHistory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(score: float, run_id: str = "run-x") -> GateResult:
    """Create a minimal GateResult with the given total_score."""
    if score >= 0.70:
        verdict = GateVerdict.PASS
    elif score >= 0.55:
        verdict = GateVerdict.WARN
    else:
        verdict = GateVerdict.BLOCK
    return GateResult(
        verdict=verdict,
        total_score=score,
        dimension_scores={},
        failed_dimensions=[],
        reasons=[],
        run_id=run_id,
        evaluated_at="2026-04-10T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestQualityHistory:
    def test_record_and_get_trend_roundtrip(self, tmp_path):
        """record() then get_trend() must return the recorded entries."""
        path = tmp_path / "quality_history.jsonl"
        history = QualityHistory(path=path)

        results = [_make_result(0.80), _make_result(0.75), _make_result(0.90)]
        for r in results:
            history.record(r)

        trend = history.get_trend(10)
        assert len(trend) == 3
        assert [r.total_score for r in trend] == pytest.approx([0.80, 0.75, 0.90])

    def test_get_trend_respects_last_n(self, tmp_path):
        """get_trend(n) must return at most n entries."""
        path = tmp_path / "quality_history.jsonl"
        history = QualityHistory(path=path)

        for score in [0.6, 0.7, 0.8, 0.9, 0.75]:
            history.record(_make_result(score))

        trend = history.get_trend(3)
        assert len(trend) == 3
        # Last 3 should be 0.8, 0.9, 0.75
        assert trend[-1].total_score == pytest.approx(0.75)

    def test_average_score_correct(self, tmp_path):
        """average_score() must return the arithmetic mean of total_scores."""
        path = tmp_path / "quality_history.jsonl"
        history = QualityHistory(path=path)

        for score in [0.60, 0.80, 1.00]:
            history.record(_make_result(score))

        avg = history.average_score(last_n=10)
        assert avg == pytest.approx(0.80)

    def test_average_score_none_when_empty(self, tmp_path):
        """average_score() must return None if no entries exist."""
        path = tmp_path / "quality_history.jsonl"
        history = QualityHistory(path=path)
        assert history.average_score() is None

    def test_is_improving_true_when_scores_rise(self, tmp_path):
        """is_improving() must return True when the second half average > first half."""
        path = tmp_path / "quality_history.jsonl"
        history = QualityHistory(path=path)

        # First half: 0.50, 0.55 → avg ≈ 0.525
        # Second half: 0.75, 0.80, 0.85 → avg = 0.80
        for score in [0.50, 0.55, 0.75, 0.80, 0.85]:
            history.record(_make_result(score))

        assert history.is_improving(last_n=5) is True

    def test_is_improving_false_when_scores_fall(self, tmp_path):
        """is_improving() must return False when the second half average <= first half."""
        path = tmp_path / "quality_history.jsonl"
        history = QualityHistory(path=path)

        # Falling scores
        for score in [0.90, 0.85, 0.70, 0.60, 0.55]:
            history.record(_make_result(score))

        assert history.is_improving(last_n=5) is False

    def test_is_improving_none_when_too_few_entries(self, tmp_path):
        """is_improving() must return None when fewer than last_n entries exist."""
        path = tmp_path / "quality_history.jsonl"
        history = QualityHistory(path=path)

        for score in [0.70, 0.80, 0.75]:
            history.record(_make_result(score))

        assert history.is_improving(last_n=5) is None

    def test_verdict_serialization_roundtrip(self, tmp_path):
        """Enum verdicts must survive JSONL serialization."""
        path = tmp_path / "quality_history.jsonl"
        history = QualityHistory(path=path)

        history.record(_make_result(0.80))   # PASS
        history.record(_make_result(0.60))   # WARN
        history.record(_make_result(0.40))   # BLOCK

        trend = history.get_trend(10)
        assert trend[0].verdict == GateVerdict.PASS
        assert trend[1].verdict == GateVerdict.WARN
        assert trend[2].verdict == GateVerdict.BLOCK

    def test_no_file_created_before_first_record(self, tmp_path):
        """Instantiating QualityHistory must not create the file prematurely."""
        path = tmp_path / "quality_history.jsonl"
        QualityHistory(path=path)
        assert not path.exists()

    def test_append_only_grows_file(self, tmp_path):
        """Each record() call must grow the file (append-only)."""
        path = tmp_path / "quality_history.jsonl"
        history = QualityHistory(path=path)

        history.record(_make_result(0.70))
        size_after_one = path.stat().st_size

        history.record(_make_result(0.80))
        size_after_two = path.stat().st_size

        assert size_after_two > size_after_one

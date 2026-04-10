"""
Tests for genus.quality.dimensions

Verifies structural invariants of the DIMENSIONS list:
- Weights sum to exactly 1.0
- hard_block_threshold <= min_threshold for every dimension that has one
- All dimension names are unique
"""

import pytest

from genus.quality.dimensions import DIMENSIONS, DIMENSION_MAP


class TestQualityDimensions:
    def test_weights_sum_to_one(self):
        """All dimension weights must sum to exactly 1.0."""
        total = sum(d.weight for d in DIMENSIONS)
        assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"

    def test_dimension_names_unique(self):
        """Each dimension name must appear exactly once."""
        names = [d.name for d in DIMENSIONS]
        assert len(names) == len(set(names)), "Duplicate dimension names detected"

    def test_hard_block_threshold_lte_min_threshold(self):
        """hard_block_threshold, when set, must be <= min_threshold."""
        for dim in DIMENSIONS:
            if dim.hard_block_threshold is not None:
                assert dim.hard_block_threshold <= dim.min_threshold, (
                    f"Dimension '{dim.name}': hard_block_threshold "
                    f"{dim.hard_block_threshold} > min_threshold {dim.min_threshold}"
                )

    def test_five_dimensions_defined(self):
        """There must be exactly five canonical dimensions."""
        assert len(DIMENSIONS) == 5

    def test_dimension_map_matches_dimensions_list(self):
        """DIMENSION_MAP must contain exactly the same entries as DIMENSIONS."""
        assert set(DIMENSION_MAP.keys()) == {d.name for d in DIMENSIONS}

    def test_all_weights_positive(self):
        """Every dimension weight must be strictly positive."""
        for dim in DIMENSIONS:
            assert dim.weight > 0, f"Dimension '{dim.name}' has non-positive weight"

    def test_required_dimensions_present(self):
        """The five canonical dimension names must all be present."""
        required = {
            "test_coverage",
            "security_compliance",
            "complexity_score",
            "feedback_history",
            "stability_score",
        }
        actual = {d.name for d in DIMENSIONS}
        assert required == actual

    def test_test_coverage_hard_block_is_050(self):
        """test_coverage hard_block_threshold must be 0.50."""
        dim = DIMENSION_MAP["test_coverage"]
        assert dim.hard_block_threshold == pytest.approx(0.50)

    def test_security_compliance_hard_block_is_090(self):
        """security_compliance hard_block_threshold must be 0.90."""
        dim = DIMENSION_MAP["security_compliance"]
        assert dim.hard_block_threshold == pytest.approx(0.90)

    def test_complexity_and_feedback_and_stability_have_no_hard_block(self):
        """complexity_score, feedback_history, stability_score must have no hard block."""
        for name in ("complexity_score", "feedback_history", "stability_score"):
            assert DIMENSION_MAP[name].hard_block_threshold is None

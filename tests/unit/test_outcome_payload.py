"""
Unit tests for genus.feedback.outcome – OutcomePayload + validate_outcome_payload.
"""

import pytest

from genus.feedback.outcome import (
    NOTES_MAX_LEN,
    OUTCOME_VALUES,
    SCORE_DELTA_MAX,
    SCORE_DELTA_MIN,
    SOURCE_DEFAULT,
    SOURCE_MAX_LEN,
    OutcomePayload,
    validate_outcome_payload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_payload(**overrides):
    base = {"outcome": "good", "score_delta": 1.0}
    base.update(overrides)
    return base


# ===========================================================================
# Valid cases
# ===========================================================================

class TestValidOutcomePayload:
    def test_good_outcome(self):
        p = validate_outcome_payload(_valid_payload(outcome="good"))
        assert p.outcome == "good"

    def test_bad_outcome(self):
        p = validate_outcome_payload(_valid_payload(outcome="bad"))
        assert p.outcome == "bad"

    def test_unknown_outcome(self):
        p = validate_outcome_payload(_valid_payload(outcome="unknown"))
        assert p.outcome == "unknown"

    def test_outcome_case_insensitive(self):
        p = validate_outcome_payload(_valid_payload(outcome="GOOD"))
        assert p.outcome == "good"

    def test_score_delta_stored(self):
        p = validate_outcome_payload(_valid_payload(score_delta=2.5))
        assert p.score_delta == 2.5

    def test_score_delta_zero(self):
        p = validate_outcome_payload(_valid_payload(score_delta=0.0))
        assert p.score_delta == 0.0

    def test_score_delta_accepts_int(self):
        p = validate_outcome_payload(_valid_payload(score_delta=3))
        assert p.score_delta == 3.0
        assert isinstance(p.score_delta, float)

    def test_notes_stored_and_stripped(self):
        p = validate_outcome_payload(_valid_payload(notes="  nice run  "))
        assert p.notes == "nice run"

    def test_notes_absent_is_none(self):
        p = validate_outcome_payload(_valid_payload())
        assert p.notes is None

    def test_notes_empty_after_strip_is_none(self):
        p = validate_outcome_payload(_valid_payload(notes="   "))
        assert p.notes is None

    def test_source_default_when_absent(self):
        p = validate_outcome_payload(_valid_payload())
        assert p.source == SOURCE_DEFAULT

    def test_source_stored_and_stripped(self):
        p = validate_outcome_payload(_valid_payload(source="  system  "))
        assert p.source == "system"

    def test_timestamp_stored(self):
        ts = "2026-04-05T17:00:00+00:00"
        p = validate_outcome_payload(_valid_payload(timestamp=ts))
        assert p.timestamp == ts

    def test_timestamp_absent_is_none(self):
        p = validate_outcome_payload(_valid_payload())
        assert p.timestamp is None


# ===========================================================================
# Clamping – score_delta
# ===========================================================================

class TestScoreDeltaClamping:
    def test_clamp_above_max(self):
        p = validate_outcome_payload(_valid_payload(score_delta=999.0))
        assert p.score_delta == SCORE_DELTA_MAX

    def test_clamp_below_min(self):
        p = validate_outcome_payload(_valid_payload(score_delta=-999.0))
        assert p.score_delta == SCORE_DELTA_MIN

    def test_exactly_max_not_clamped(self):
        p = validate_outcome_payload(_valid_payload(score_delta=SCORE_DELTA_MAX))
        assert p.score_delta == SCORE_DELTA_MAX

    def test_exactly_min_not_clamped(self):
        p = validate_outcome_payload(_valid_payload(score_delta=SCORE_DELTA_MIN))
        assert p.score_delta == SCORE_DELTA_MIN


# ===========================================================================
# Length limits
# ===========================================================================

class TestLengthLimits:
    def test_notes_at_max_length_ok(self):
        notes = "x" * NOTES_MAX_LEN
        p = validate_outcome_payload(_valid_payload(notes=notes))
        assert len(p.notes) == NOTES_MAX_LEN

    def test_notes_over_max_length_raises(self):
        notes = "x" * (NOTES_MAX_LEN + 1)
        with pytest.raises(ValueError, match="notes"):
            validate_outcome_payload(_valid_payload(notes=notes))

    def test_source_at_max_length_ok(self):
        source = "s" * SOURCE_MAX_LEN
        p = validate_outcome_payload(_valid_payload(source=source))
        assert len(p.source) == SOURCE_MAX_LEN

    def test_source_over_max_length_raises(self):
        source = "s" * (SOURCE_MAX_LEN + 1)
        with pytest.raises(ValueError, match="source"):
            validate_outcome_payload(_valid_payload(source=source))


# ===========================================================================
# Invalid / missing required fields
# ===========================================================================

class TestInvalidPayload:
    def test_missing_outcome_raises(self):
        with pytest.raises(ValueError, match="outcome"):
            validate_outcome_payload({"score_delta": 1.0})

    def test_invalid_outcome_raises(self):
        with pytest.raises(ValueError, match="outcome"):
            validate_outcome_payload(_valid_payload(outcome="excellent"))

    def test_missing_score_delta_raises(self):
        with pytest.raises(ValueError, match="score_delta"):
            validate_outcome_payload({"outcome": "good"})

    def test_non_numeric_score_delta_raises(self):
        with pytest.raises(ValueError, match="score_delta"):
            validate_outcome_payload(_valid_payload(score_delta="fast"))

    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            validate_outcome_payload("not-a-dict")

    def test_notes_non_string_raises(self):
        with pytest.raises(ValueError, match="notes"):
            validate_outcome_payload(_valid_payload(notes=42))

    def test_source_non_string_raises(self):
        with pytest.raises(ValueError, match="source"):
            validate_outcome_payload(_valid_payload(source=123))

    def test_timestamp_non_string_raises(self):
        with pytest.raises(ValueError, match="timestamp"):
            validate_outcome_payload(_valid_payload(timestamp=20260405))


# ===========================================================================
# to_message_payload
# ===========================================================================

class TestToMessagePayload:
    def test_required_fields_present(self):
        p = validate_outcome_payload(_valid_payload(outcome="bad", score_delta=-1.0))
        d = p.to_message_payload()
        assert d["outcome"] == "bad"
        assert d["score_delta"] == -1.0
        assert d["source"] == SOURCE_DEFAULT

    def test_optional_fields_absent_when_not_set(self):
        p = validate_outcome_payload(_valid_payload())
        d = p.to_message_payload()
        assert "notes" not in d
        assert "timestamp" not in d

    def test_optional_fields_present_when_set(self):
        ts = "2026-04-05T17:00:00+00:00"
        p = validate_outcome_payload(_valid_payload(notes="ok", timestamp=ts))
        d = p.to_message_payload()
        assert d["notes"] == "ok"
        assert d["timestamp"] == ts

    def test_run_id_not_in_payload(self):
        p = validate_outcome_payload(_valid_payload())
        d = p.to_message_payload()
        assert "run_id" not in d

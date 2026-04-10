"""
Tests for genus.growth.need_record (NeedRecord)

Verifies:
- Instantiation with minimal arguments
- need_id is automatically set
- first_seen_at and last_seen_at are automatically set
- increment_trigger() increases trigger_count
- increment_trigger() adds source_topic only once (no duplicates)
- increment_trigger() updates last_seen_at
- is_ready_for_build(min=2) → False when trigger_count=1
- is_ready_for_build(min=2) → True when trigger_count=2
- is_ready_for_build(min=2) → False when status != "observed"
- to_payload() contains all fields
"""

import time

import pytest

from genus.growth.need_record import NeedRecord


class TestNeedRecordInstantiation:
    def test_minimal_instantiation(self):
        """NeedRecord can be created with only domain and need_description."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        assert nr.domain == "system"
        assert nr.need_description == "repeated_failure"

    def test_need_id_auto_generated(self):
        """need_id is automatically set to a UUID when left empty."""
        nr = NeedRecord(domain="quality", need_description="low_quality_score")
        assert nr.need_id != ""
        # UUID format: 8-4-4-4-12 hex digits separated by hyphens
        parts = nr.need_id.split("-")
        assert len(parts) == 5

    def test_need_id_not_overwritten_when_provided(self):
        """need_id is preserved when explicitly provided."""
        custom_id = "custom-id-123"
        nr = NeedRecord(need_id=custom_id, domain="system", need_description="run_failure")
        assert nr.need_id == custom_id

    def test_first_seen_at_auto_set(self):
        """first_seen_at is automatically set to a UTC timestamp."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        assert nr.first_seen_at != ""
        assert "T" in nr.first_seen_at  # ISO 8601

    def test_last_seen_at_auto_set(self):
        """last_seen_at is automatically set to a UTC timestamp."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        assert nr.last_seen_at != ""
        assert "T" in nr.last_seen_at  # ISO 8601

    def test_default_status_is_observed(self):
        """Default status is 'observed'."""
        nr = NeedRecord(domain="system", need_description="run_failure")
        assert nr.status == "observed"

    def test_default_trigger_count_is_zero(self):
        """Default trigger_count is 0."""
        nr = NeedRecord(domain="system", need_description="run_failure")
        assert nr.trigger_count == 0

    def test_two_records_have_different_need_ids(self):
        """Two NeedRecords created consecutively have different UUIDs."""
        nr1 = NeedRecord(domain="system", need_description="run_failure")
        nr2 = NeedRecord(domain="system", need_description="run_failure")
        assert nr1.need_id != nr2.need_id


class TestNeedRecordIncrementTrigger:
    def test_increment_increases_trigger_count(self):
        """increment_trigger() increases trigger_count by 1."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        nr.increment_trigger("feedback.received")
        assert nr.trigger_count == 1

    def test_increment_multiple_times(self):
        """Multiple calls to increment_trigger() accumulate correctly."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        nr.increment_trigger("feedback.received")
        nr.increment_trigger("feedback.received")
        nr.increment_trigger("run.failed")
        assert nr.trigger_count == 3

    def test_increment_adds_source_topic(self):
        """increment_trigger() adds source_topic to source_topics."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        nr.increment_trigger("feedback.received")
        assert "feedback.received" in nr.source_topics

    def test_increment_no_duplicate_source_topic(self):
        """The same source_topic is never added twice to source_topics."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        nr.increment_trigger("feedback.received")
        nr.increment_trigger("feedback.received")
        assert nr.source_topics.count("feedback.received") == 1

    def test_increment_multiple_source_topics(self):
        """Different source topics are all added to source_topics."""
        nr = NeedRecord(domain="system", need_description="run_failure")
        nr.increment_trigger("run.failed")
        nr.increment_trigger("feedback.received")
        assert "run.failed" in nr.source_topics
        assert "feedback.received" in nr.source_topics

    def test_increment_updates_last_seen_at(self):
        """increment_trigger() updates last_seen_at to a newer timestamp."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        before = nr.last_seen_at
        # A small sleep to ensure a different timestamp
        time.sleep(0.01)
        nr.increment_trigger("feedback.received")
        assert nr.last_seen_at >= before


class TestNeedRecordIsReadyForBuild:
    def test_not_ready_below_min(self):
        """is_ready_for_build returns False when trigger_count < min_trigger_count."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        nr.increment_trigger("feedback.received")
        assert nr.is_ready_for_build(min_trigger_count=2) is False

    def test_ready_at_min(self):
        """is_ready_for_build returns True when trigger_count == min_trigger_count."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        nr.increment_trigger("feedback.received")
        nr.increment_trigger("feedback.received")
        assert nr.is_ready_for_build(min_trigger_count=2) is True

    def test_ready_above_min(self):
        """is_ready_for_build returns True when trigger_count > min_trigger_count."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        for _ in range(5):
            nr.increment_trigger("feedback.received")
        assert nr.is_ready_for_build(min_trigger_count=2) is True

    def test_not_ready_when_status_not_observed(self):
        """is_ready_for_build returns False when status != 'observed'."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        nr.increment_trigger("feedback.received")
        nr.increment_trigger("feedback.received")
        nr.status = "queued"
        assert nr.is_ready_for_build(min_trigger_count=2) is False

    def test_not_ready_when_status_fulfilled(self):
        """is_ready_for_build returns False when status is 'fulfilled'."""
        nr = NeedRecord(domain="system", need_description="repeated_failure")
        for _ in range(3):
            nr.increment_trigger("feedback.received")
        nr.status = "fulfilled"
        assert nr.is_ready_for_build(min_trigger_count=2) is False


class TestNeedRecordToPayload:
    def test_payload_contains_all_fields(self):
        """to_payload() returns a dict containing all NeedRecord fields."""
        nr = NeedRecord(domain="quality", need_description="low_quality_score")
        nr.increment_trigger("quality.scored")
        payload = nr.to_payload()
        assert payload["need_id"] == nr.need_id
        assert payload["domain"] == "quality"
        assert payload["need_description"] == "low_quality_score"
        assert payload["trigger_count"] == 1
        assert payload["first_seen_at"] == nr.first_seen_at
        assert payload["last_seen_at"] == nr.last_seen_at
        assert payload["status"] == "observed"
        assert payload["source_topics"] == ["quality.scored"]
        assert isinstance(payload["metadata"], dict)

    def test_payload_is_copy(self):
        """Mutating the returned payload dict does not affect the NeedRecord."""
        nr = NeedRecord(domain="system", need_description="run_failure")
        payload = nr.to_payload()
        payload["domain"] = "mutated"
        assert nr.domain == "system"

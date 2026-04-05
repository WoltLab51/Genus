"""
Tests for genus/run/events.py

Validates that all run lifecycle message factories:
- set the correct topic and sender_id
- attach run_id into metadata["run_id"]
- include step_id in payload for step events
- do not mutate the caller's payload or metadata dicts
"""

import pytest

from genus.run import topics
from genus.run.events import (
    run_started_message,
    run_step_planned_message,
    run_step_started_message,
    run_step_completed_message,
    run_step_failed_message,
    run_completed_message,
    run_failed_message,
)

RUN_ID = "2026-04-05T10-00-00Z__test__abc123"
SENDER = "test-orchestrator"
STEP_ID = "step-42"


# ---------------------------------------------------------------------------
# run_started_message
# ---------------------------------------------------------------------------

class TestRunStartedMessage:
    def test_correct_topic(self):
        msg = run_started_message(RUN_ID, SENDER)
        assert msg.topic == topics.RUN_STARTED

    def test_correct_sender_id(self):
        msg = run_started_message(RUN_ID, SENDER)
        assert msg.sender_id == SENDER

    def test_run_id_in_metadata(self):
        msg = run_started_message(RUN_ID, SENDER)
        assert msg.metadata["run_id"] == RUN_ID

    def test_optional_payload(self):
        msg = run_started_message(RUN_ID, SENDER, payload={"goal": "test"})
        assert msg.payload["goal"] == "test"

    def test_optional_metadata_merged(self):
        msg = run_started_message(RUN_ID, SENDER, metadata={"trace_id": "t1"})
        assert msg.metadata["trace_id"] == "t1"
        assert msg.metadata["run_id"] == RUN_ID

    def test_does_not_mutate_input_payload(self):
        original_payload = {"key": "value"}
        run_started_message(RUN_ID, SENDER, payload=original_payload)
        assert original_payload == {"key": "value"}

    def test_does_not_mutate_input_metadata(self):
        original_metadata = {"trace_id": "t1"}
        run_started_message(RUN_ID, SENDER, metadata=original_metadata)
        assert original_metadata == {"trace_id": "t1"}


# ---------------------------------------------------------------------------
# run_step_planned_message
# ---------------------------------------------------------------------------

class TestRunStepPlannedMessage:
    def test_correct_topic(self):
        msg = run_step_planned_message(RUN_ID, SENDER, STEP_ID)
        assert msg.topic == topics.RUN_STEP_PLANNED

    def test_correct_sender_id(self):
        msg = run_step_planned_message(RUN_ID, SENDER, STEP_ID)
        assert msg.sender_id == SENDER

    def test_run_id_in_metadata(self):
        msg = run_step_planned_message(RUN_ID, SENDER, STEP_ID)
        assert msg.metadata["run_id"] == RUN_ID

    def test_step_id_in_payload(self):
        msg = run_step_planned_message(RUN_ID, SENDER, STEP_ID)
        assert msg.payload["step_id"] == STEP_ID

    def test_does_not_mutate_input_payload(self):
        original_payload = {"extra": "data"}
        run_step_planned_message(RUN_ID, SENDER, STEP_ID, payload=original_payload)
        assert original_payload == {"extra": "data"}

    def test_does_not_mutate_input_metadata(self):
        original_metadata = {"trace_id": "t1"}
        run_step_planned_message(RUN_ID, SENDER, STEP_ID, metadata=original_metadata)
        assert original_metadata == {"trace_id": "t1"}


# ---------------------------------------------------------------------------
# run_step_started_message
# ---------------------------------------------------------------------------

class TestRunStepStartedMessage:
    def test_correct_topic(self):
        msg = run_step_started_message(RUN_ID, SENDER, STEP_ID)
        assert msg.topic == topics.RUN_STEP_STARTED

    def test_correct_sender_id(self):
        msg = run_step_started_message(RUN_ID, SENDER, STEP_ID)
        assert msg.sender_id == SENDER

    def test_run_id_in_metadata(self):
        msg = run_step_started_message(RUN_ID, SENDER, STEP_ID)
        assert msg.metadata["run_id"] == RUN_ID

    def test_step_id_in_payload(self):
        msg = run_step_started_message(RUN_ID, SENDER, STEP_ID)
        assert msg.payload["step_id"] == STEP_ID

    def test_does_not_mutate_input_payload(self):
        original_payload = {"extra": "data"}
        run_step_started_message(RUN_ID, SENDER, STEP_ID, payload=original_payload)
        assert original_payload == {"extra": "data"}

    def test_does_not_mutate_input_metadata(self):
        original_metadata = {"trace_id": "t1"}
        run_step_started_message(RUN_ID, SENDER, STEP_ID, metadata=original_metadata)
        assert original_metadata == {"trace_id": "t1"}


# ---------------------------------------------------------------------------
# run_step_completed_message
# ---------------------------------------------------------------------------

class TestRunStepCompletedMessage:
    def test_correct_topic(self):
        msg = run_step_completed_message(RUN_ID, SENDER, STEP_ID)
        assert msg.topic == topics.RUN_STEP_COMPLETED

    def test_correct_sender_id(self):
        msg = run_step_completed_message(RUN_ID, SENDER, STEP_ID)
        assert msg.sender_id == SENDER

    def test_run_id_in_metadata(self):
        msg = run_step_completed_message(RUN_ID, SENDER, STEP_ID)
        assert msg.metadata["run_id"] == RUN_ID

    def test_step_id_in_payload(self):
        msg = run_step_completed_message(RUN_ID, SENDER, STEP_ID)
        assert msg.payload["step_id"] == STEP_ID

    def test_does_not_mutate_input_payload(self):
        original_payload = {"result": "ok"}
        run_step_completed_message(RUN_ID, SENDER, STEP_ID, payload=original_payload)
        assert original_payload == {"result": "ok"}

    def test_does_not_mutate_input_metadata(self):
        original_metadata = {"trace_id": "t1"}
        run_step_completed_message(RUN_ID, SENDER, STEP_ID, metadata=original_metadata)
        assert original_metadata == {"trace_id": "t1"}


# ---------------------------------------------------------------------------
# run_step_failed_message
# ---------------------------------------------------------------------------

class TestRunStepFailedMessage:
    def test_correct_topic(self):
        msg = run_step_failed_message(RUN_ID, SENDER, STEP_ID)
        assert msg.topic == topics.RUN_STEP_FAILED

    def test_correct_sender_id(self):
        msg = run_step_failed_message(RUN_ID, SENDER, STEP_ID)
        assert msg.sender_id == SENDER

    def test_run_id_in_metadata(self):
        msg = run_step_failed_message(RUN_ID, SENDER, STEP_ID)
        assert msg.metadata["run_id"] == RUN_ID

    def test_step_id_in_payload(self):
        msg = run_step_failed_message(RUN_ID, SENDER, STEP_ID)
        assert msg.payload["step_id"] == STEP_ID

    def test_does_not_mutate_input_payload(self):
        original_payload = {"error": "oops"}
        run_step_failed_message(RUN_ID, SENDER, STEP_ID, payload=original_payload)
        assert original_payload == {"error": "oops"}

    def test_does_not_mutate_input_metadata(self):
        original_metadata = {"trace_id": "t1"}
        run_step_failed_message(RUN_ID, SENDER, STEP_ID, metadata=original_metadata)
        assert original_metadata == {"trace_id": "t1"}


# ---------------------------------------------------------------------------
# run_completed_message
# ---------------------------------------------------------------------------

class TestRunCompletedMessage:
    def test_correct_topic(self):
        msg = run_completed_message(RUN_ID, SENDER)
        assert msg.topic == topics.RUN_COMPLETED

    def test_correct_sender_id(self):
        msg = run_completed_message(RUN_ID, SENDER)
        assert msg.sender_id == SENDER

    def test_run_id_in_metadata(self):
        msg = run_completed_message(RUN_ID, SENDER)
        assert msg.metadata["run_id"] == RUN_ID

    def test_does_not_mutate_input_metadata(self):
        original_metadata = {"trace_id": "t1"}
        run_completed_message(RUN_ID, SENDER, metadata=original_metadata)
        assert original_metadata == {"trace_id": "t1"}


# ---------------------------------------------------------------------------
# run_failed_message
# ---------------------------------------------------------------------------

class TestRunFailedMessage:
    def test_correct_topic(self):
        msg = run_failed_message(RUN_ID, SENDER)
        assert msg.topic == topics.RUN_FAILED

    def test_correct_sender_id(self):
        msg = run_failed_message(RUN_ID, SENDER)
        assert msg.sender_id == SENDER

    def test_run_id_in_metadata(self):
        msg = run_failed_message(RUN_ID, SENDER)
        assert msg.metadata["run_id"] == RUN_ID

    def test_does_not_mutate_input_metadata(self):
        original_metadata = {"trace_id": "t1"}
        run_failed_message(RUN_ID, SENDER, metadata=original_metadata)
        assert original_metadata == {"trace_id": "t1"}


# ---------------------------------------------------------------------------
# Cross-cutting: run_id value equality for all factories
# ---------------------------------------------------------------------------

class TestRunIdPropagation:
    def test_run_id_equals_provided_value_for_all_factories(self):
        run_id = "2026-04-05T10-00-00Z__check__zz9999"
        messages = [
            run_started_message(run_id, SENDER),
            run_step_planned_message(run_id, SENDER, STEP_ID),
            run_step_started_message(run_id, SENDER, STEP_ID),
            run_step_completed_message(run_id, SENDER, STEP_ID),
            run_step_failed_message(run_id, SENDER, STEP_ID),
            run_completed_message(run_id, SENDER),
            run_failed_message(run_id, SENDER),
        ]
        for msg in messages:
            assert msg.metadata["run_id"] == run_id, f"run_id mismatch for topic {msg.topic!r}"

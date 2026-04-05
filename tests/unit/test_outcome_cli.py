"""
Unit tests for genus.cli.outcome – CLI publish behaviour.

Tests use an in-memory MessageBus with a test subscriber; no files are written
and no real bus is started externally.
"""

import pytest

from genus.cli.outcome import SENDER_ID, TOPIC, _async_main, build_message, _build_parser
from genus.communication.message_bus import Message, MessageBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_args(**overrides):
    """Return a namespace that represents a valid CLI invocation."""
    import argparse

    defaults = dict(
        run_id="2026-04-05T17-00-00__test__abc123",
        outcome="good",
        score_delta=1.0,
        notes=None,
        source="user",
        timestamp=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


async def _collect(argv, bus=None):
    """Run _async_main with *argv* and return all collected messages."""
    received = []

    if bus is None:
        bus = MessageBus()

    bus.subscribe(TOPIC, "test-collector", lambda msg: received.append(msg))
    await _async_main(argv=argv, bus=bus)
    return received


# ===========================================================================
# build_message
# ===========================================================================

class TestBuildMessage:
    def test_topic_is_outcome_recorded(self):
        bus = MessageBus()
        msg = build_message(_make_args(), bus)
        assert msg.topic == TOPIC

    def test_sender_id_is_outcome_cli(self):
        bus = MessageBus()
        msg = build_message(_make_args(), bus)
        assert msg.sender_id == SENDER_ID

    def test_run_id_in_metadata(self):
        run_id = "2026-04-05T17-00-00__test__abc123"
        bus = MessageBus()
        msg = build_message(_make_args(run_id=run_id), bus)
        assert msg.metadata["run_id"] == run_id

    def test_run_id_not_in_payload(self):
        bus = MessageBus()
        msg = build_message(_make_args(), bus)
        assert "run_id" not in msg.payload

    def test_outcome_in_payload(self):
        bus = MessageBus()
        msg = build_message(_make_args(outcome="bad"), bus)
        assert msg.payload["outcome"] == "bad"

    def test_score_delta_clamped_in_payload(self):
        bus = MessageBus()
        msg = build_message(_make_args(score_delta=999.0), bus)
        assert msg.payload["score_delta"] == 10.0

    def test_notes_in_payload_when_provided(self):
        bus = MessageBus()
        msg = build_message(_make_args(notes="looks great"), bus)
        assert msg.payload["notes"] == "looks great"

    def test_notes_absent_in_payload_when_not_provided(self):
        bus = MessageBus()
        msg = build_message(_make_args(notes=None), bus)
        assert "notes" not in msg.payload

    def test_timestamp_set_automatically_when_absent(self):
        bus = MessageBus()
        msg = build_message(_make_args(timestamp=None), bus)
        assert "timestamp" in msg.payload
        assert msg.payload["timestamp"]  # non-empty string

    def test_timestamp_used_when_provided(self):
        ts = "2026-04-05T17:00:00+00:00"
        bus = MessageBus()
        msg = build_message(_make_args(timestamp=ts), bus)
        assert msg.payload["timestamp"] == ts


# ===========================================================================
# Full CLI argv → publish
# ===========================================================================

class TestAsyncMain:
    @pytest.mark.asyncio
    async def test_publishes_exactly_one_message(self):
        argv = [
            "--run-id", "run-001",
            "--outcome", "good",
            "--score-delta", "1.0",
        ]
        received = await _collect(argv)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_message_has_correct_topic(self):
        argv = [
            "--run-id", "run-001",
            "--outcome", "good",
            "--score-delta", "1.0",
        ]
        received = await _collect(argv)
        assert received[0].topic == TOPIC

    @pytest.mark.asyncio
    async def test_run_id_in_metadata(self):
        argv = [
            "--run-id", "run-xyz",
            "--outcome", "bad",
            "--score-delta", "-1.0",
        ]
        received = await _collect(argv)
        assert received[0].metadata["run_id"] == "run-xyz"

    @pytest.mark.asyncio
    async def test_outcome_in_payload(self):
        argv = [
            "--run-id", "run-001",
            "--outcome", "unknown",
            "--score-delta", "0",
        ]
        received = await _collect(argv)
        assert received[0].payload["outcome"] == "unknown"

    @pytest.mark.asyncio
    async def test_score_delta_in_payload(self):
        argv = [
            "--run-id", "run-001",
            "--outcome", "good",
            "--score-delta", "3.5",
        ]
        received = await _collect(argv)
        assert received[0].payload["score_delta"] == 3.5

    @pytest.mark.asyncio
    async def test_notes_in_payload_when_provided(self):
        argv = [
            "--run-id", "run-001",
            "--outcome", "good",
            "--score-delta", "1",
            "--notes", "all checks passed",
        ]
        received = await _collect(argv)
        assert received[0].payload["notes"] == "all checks passed"

    @pytest.mark.asyncio
    async def test_source_default_when_not_provided(self):
        argv = [
            "--run-id", "run-001",
            "--outcome", "good",
            "--score-delta", "1",
        ]
        received = await _collect(argv)
        assert received[0].payload["source"] == "user"

    @pytest.mark.asyncio
    async def test_source_custom_when_provided(self):
        argv = [
            "--run-id", "run-001",
            "--outcome", "good",
            "--score-delta", "1",
            "--source", "system",
        ]
        received = await _collect(argv)
        assert received[0].payload["source"] == "system"

    @pytest.mark.asyncio
    async def test_timestamp_auto_when_not_provided(self):
        argv = [
            "--run-id", "run-001",
            "--outcome", "good",
            "--score-delta", "1",
        ]
        received = await _collect(argv)
        assert "timestamp" in received[0].payload
        assert received[0].payload["timestamp"]

    @pytest.mark.asyncio
    async def test_timestamp_used_when_provided(self):
        ts = "2026-04-05T17:00:00+00:00"
        argv = [
            "--run-id", "run-001",
            "--outcome", "good",
            "--score-delta", "1",
            "--timestamp", ts,
        ]
        received = await _collect(argv)
        assert received[0].payload["timestamp"] == ts

    @pytest.mark.asyncio
    async def test_sender_id_is_outcome_cli(self):
        argv = [
            "--run-id", "run-001",
            "--outcome", "good",
            "--score-delta", "1",
        ]
        received = await _collect(argv)
        assert received[0].sender_id == SENDER_ID

    @pytest.mark.asyncio
    async def test_score_delta_clamped(self):
        argv = [
            "--run-id", "run-001",
            "--outcome", "good",
            "--score-delta", "9999",
        ]
        received = await _collect(argv)
        assert received[0].payload["score_delta"] == 10.0

    def test_missing_run_id_exits(self):
        """--run-id is required; argparse raises SystemExit when absent."""
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--outcome", "good", "--score-delta", "1"])

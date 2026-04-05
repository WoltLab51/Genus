"""
Unit tests for genus.communication.serialization

These tests run without any Redis dependency.

Verifies:
- message_to_dict produces the expected keys and types
- message_from_dict round-trips a message correctly
- timestamp is stored as ISO 8601 UTC string
- priority is stored as its name string
- run_id (in metadata) survives round-trip
- payload and metadata are deep-copied (no aliasing)
"""

import uuid
from datetime import datetime, timezone

import pytest

from genus.communication.message_bus import Message, MessagePriority
from genus.communication.serialization import message_from_dict, message_to_dict
from genus.core.run import attach_run_id, get_run_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_message(
    topic: str = "tool.call.requested",
    payload: object = None,
    sender_id: str = "TestSender",
    priority: MessagePriority = MessagePriority.NORMAL,
    metadata: dict = None,
) -> Message:
    return Message(
        topic=topic,
        payload=payload if payload is not None else {"key": "value"},
        sender_id=sender_id,
        priority=priority,
        metadata=metadata if metadata is not None else {},
    )


# ---------------------------------------------------------------------------
# message_to_dict
# ---------------------------------------------------------------------------

class TestMessageToDict:

    def test_returns_dict(self):
        msg = _make_message()
        result = message_to_dict(msg)
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        msg = _make_message()
        result = message_to_dict(msg)
        expected_keys = {"message_id", "topic", "sender_id", "timestamp", "priority", "payload", "metadata"}
        assert expected_keys == set(result.keys())

    def test_topic_preserved(self):
        msg = _make_message(topic="run.started")
        assert message_to_dict(msg)["topic"] == "run.started"

    def test_sender_id_preserved(self):
        msg = _make_message(sender_id="Orchestrator")
        assert message_to_dict(msg)["sender_id"] == "Orchestrator"

    def test_message_id_is_string(self):
        msg = _make_message()
        result = message_to_dict(msg)
        assert isinstance(result["message_id"], str)
        # Must be a valid UUID
        uuid.UUID(result["message_id"])

    def test_timestamp_is_iso_string(self):
        msg = _make_message()
        result = message_to_dict(msg)
        ts = result["timestamp"]
        assert isinstance(ts, str)
        assert "T" in ts
        assert ts.endswith("Z")

    def test_priority_is_name_string(self):
        msg = _make_message(priority=MessagePriority.HIGH)
        result = message_to_dict(msg)
        assert result["priority"] == "HIGH"

    def test_priority_low(self):
        msg = _make_message(priority=MessagePriority.LOW)
        assert message_to_dict(msg)["priority"] == "LOW"

    def test_priority_critical(self):
        msg = _make_message(priority=MessagePriority.CRITICAL)
        assert message_to_dict(msg)["priority"] == "CRITICAL"

    def test_payload_preserved(self):
        payload = {"tool_name": "echo", "tool_args": {"message": "hi"}}
        msg = _make_message(payload=payload)
        result = message_to_dict(msg)
        assert result["payload"] == payload

    def test_metadata_preserved(self):
        metadata = {"run_id": "2026-01-01T00-00-00Z__test__abc123"}
        msg = _make_message(metadata=metadata)
        result = message_to_dict(msg)
        assert result["metadata"]["run_id"] == metadata["run_id"]

    def test_metadata_is_copy(self):
        metadata = {"run_id": "original"}
        msg = _make_message(metadata=metadata)
        result = message_to_dict(msg)
        result["metadata"]["run_id"] = "mutated"
        # Original message metadata must be untouched
        assert msg.metadata["run_id"] == "original"

    def test_utc_naive_timestamp_serialized_as_utc(self):
        """Naive datetime (assumed UTC) should serialize with Z suffix."""
        naive_ts = datetime(2026, 4, 5, 19, 40, 20, 380000)
        msg = Message(
            topic="t", payload={}, sender_id="s",
            timestamp=naive_ts,
        )
        result = message_to_dict(msg)
        assert result["timestamp"].endswith("Z")

    def test_utc_aware_timestamp_serialized(self):
        """Timezone-aware UTC datetime should serialize correctly."""
        aware_ts = datetime(2026, 4, 5, 19, 40, 20, 380000, tzinfo=timezone.utc)
        msg = Message(
            topic="t", payload={}, sender_id="s",
            timestamp=aware_ts,
        )
        result = message_to_dict(msg)
        assert "2026-04-05T19:40:20" in result["timestamp"]


# ---------------------------------------------------------------------------
# message_from_dict
# ---------------------------------------------------------------------------

class TestMessageFromDict:

    def test_returns_message(self):
        msg = _make_message()
        d = message_to_dict(msg)
        result = message_from_dict(d)
        assert isinstance(result, Message)

    def test_topic_restored(self):
        msg = _make_message(topic="tool.call.succeeded")
        d = message_to_dict(msg)
        assert message_from_dict(d).topic == "tool.call.succeeded"

    def test_sender_id_restored(self):
        msg = _make_message(sender_id="ToolExecutor")
        d = message_to_dict(msg)
        assert message_from_dict(d).sender_id == "ToolExecutor"

    def test_message_id_restored(self):
        msg = _make_message()
        d = message_to_dict(msg)
        assert message_from_dict(d).message_id == msg.message_id

    def test_priority_restored(self):
        msg = _make_message(priority=MessagePriority.HIGH)
        d = message_to_dict(msg)
        assert message_from_dict(d).priority == MessagePriority.HIGH

    def test_payload_restored(self):
        payload = {"step_id": "abc", "result": 42}
        msg = _make_message(payload=payload)
        d = message_to_dict(msg)
        assert message_from_dict(d).payload == payload

    def test_metadata_restored(self):
        metadata = {"run_id": "2026-01-01T00-00-00Z__demo__xyz999"}
        msg = _make_message(metadata=metadata)
        d = message_to_dict(msg)
        restored = message_from_dict(d)
        assert restored.metadata["run_id"] == metadata["run_id"]

    def test_timestamp_is_aware(self):
        """Deserialized timestamp must be timezone-aware UTC."""
        msg = _make_message()
        d = message_to_dict(msg)
        restored = message_from_dict(d)
        assert restored.timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:

    def test_full_round_trip(self):
        original = _make_message(
            topic="tool.call.requested",
            payload={"step_id": str(uuid.uuid4()), "tool_name": "add", "tool_args": {"a": 3, "b": 4}},
            sender_id="Orchestrator",
            priority=MessagePriority.NORMAL,
            metadata={"run_id": "2026-04-05T19-40-20Z__test__abc123"},
        )
        d = message_to_dict(original)
        restored = message_from_dict(d)

        assert restored.message_id == original.message_id
        assert restored.topic == original.topic
        assert restored.sender_id == original.sender_id
        assert restored.priority == original.priority
        assert restored.payload == original.payload
        assert restored.metadata == original.metadata

    def test_run_id_survives_round_trip(self):
        """run_id in metadata must survive serialization."""
        msg = _make_message(
            metadata={"run_id": "2026-04-05T19-40-20Z__my-task__r4nd0m"}
        )
        d = message_to_dict(msg)
        restored = message_from_dict(d)
        assert get_run_id(restored) == "2026-04-05T19-40-20Z__my-task__r4nd0m"

    def test_run_id_via_attach_survives_round_trip(self):
        """run_id attached via attach_run_id must survive."""
        msg = _make_message()
        msg = attach_run_id(msg, "2026-04-05T19-40-20Z__attached__x1y2z3")
        d = message_to_dict(msg)
        restored = message_from_dict(d)
        assert get_run_id(restored) == "2026-04-05T19-40-20Z__attached__x1y2z3"

    def test_none_payload_round_trip(self):
        msg = Message(topic="t", payload=None, sender_id="s")
        d = message_to_dict(msg)
        restored = message_from_dict(d)
        assert restored.payload is None

    def test_list_payload_round_trip(self):
        msg = Message(topic="t", payload=[1, 2, 3], sender_id="s")
        d = message_to_dict(msg)
        restored = message_from_dict(d)
        assert restored.payload == [1, 2, 3]

    def test_all_priorities_round_trip(self):
        for priority in MessagePriority:
            msg = _make_message(priority=priority)
            d = message_to_dict(msg)
            restored = message_from_dict(d)
            assert restored.priority == priority

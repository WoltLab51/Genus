"""
Unit tests for the JSONL EventStore.

Covers:
- EventEnvelope construction and from_message factory
- append / iter returns correct envelopes in order
- latest() with and without topic filter
- per-run file path generation
- sanitize_run_id: rejects traversal sequences; cleans unsafe chars
- ENV override for storage directory
- list() convenience wrapper
- Malformed lines in JSONL are skipped gracefully
"""

import json
import os
import tempfile

import pytest

from genus.communication.message_bus import Message
from genus.memory.jsonl_event_store import (
    EventEnvelope,
    JsonlEventStore,
    sanitize_run_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = "2026-04-05T14-07-12Z__test__abc123"


def _make_message(
    topic: str = "quality.scored",
    payload: dict | None = None,
    run_id: str = RUN_ID,
    sender_id: str = "test-agent",
) -> Message:
    metadata: dict = {}
    if run_id is not None:
        metadata["run_id"] = run_id
    return Message(
        topic=topic,
        payload=payload or {"quality_score": 0.9},
        sender_id=sender_id,
        metadata=metadata,
    )


def _make_envelope(
    run_id: str = RUN_ID,
    topic: str = "quality.scored",
    payload: dict | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        timestamp="2026-04-05T14:07:12+00:00",
        run_id=run_id,
        topic=topic,
        sender_id="test-agent",
        payload=payload or {"quality_score": 0.9},
        metadata={"run_id": run_id},
    )


# ===========================================================================
# sanitize_run_id
# ===========================================================================

class TestSanitizeRunId:
    def test_normal_run_id_unchanged(self):
        assert sanitize_run_id(RUN_ID) == RUN_ID

    def test_replaces_slashes(self):
        result = sanitize_run_id("foo/bar")
        assert "/" not in result
        assert result == "foo_bar"

    def test_replaces_spaces(self):
        result = sanitize_run_id("my run id")
        assert " " not in result

    def test_traversal_raises(self):
        with pytest.raises(ValueError, match="path-traversal"):
            sanitize_run_id("../etc/passwd")

    def test_traversal_in_middle_raises(self):
        with pytest.raises(ValueError, match="path-traversal"):
            sanitize_run_id("run/../secret")

    def test_allows_dots_hyphens_underscores(self):
        safe = sanitize_run_id("run-2026_04_05.test")
        assert safe == "run-2026_04_05.test"

    def test_empty_string_becomes_unknown(self):
        # After replacing all chars we get empty → "unknown" fallback
        # NOTE: empty string has no traversal, just no valid chars
        result = sanitize_run_id("")
        assert result == "unknown"


# ===========================================================================
# EventEnvelope
# ===========================================================================

class TestEventEnvelope:
    def test_to_dict_contains_all_fields(self):
        env = _make_envelope()
        d = env.to_dict()
        assert d["run_id"] == RUN_ID
        assert d["topic"] == "quality.scored"
        assert d["sender_id"] == "test-agent"
        assert "timestamp" in d
        assert "payload" in d
        assert "metadata" in d

    def test_from_dict_round_trip(self):
        env = _make_envelope()
        restored = EventEnvelope.from_dict(env.to_dict())
        assert restored.run_id == env.run_id
        assert restored.topic == env.topic
        assert restored.payload == env.payload

    def test_from_dict_ignores_unknown_keys(self):
        d = _make_envelope().to_dict()
        d["future_field"] = "some_value"
        restored = EventEnvelope.from_dict(d)
        assert restored.run_id == RUN_ID

    def test_from_message_sets_correct_fields(self):
        msg = _make_message()
        env = EventEnvelope.from_message(msg)
        assert env.run_id == RUN_ID
        assert env.topic == "quality.scored"
        assert env.sender_id == "test-agent"
        assert env.payload == {"quality_score": 0.9}

    def test_from_message_run_id_override(self):
        msg = _make_message(run_id=RUN_ID)
        env = EventEnvelope.from_message(msg, run_id="override-run")
        assert env.run_id == "override-run"

    def test_from_message_missing_run_id_falls_back_to_unknown(self):
        msg = Message(topic="quality.scored", payload={}, sender_id="s", metadata={})
        env = EventEnvelope.from_message(msg)
        assert env.run_id == "unknown"

    def test_from_message_extra_metadata_merged(self):
        msg = _make_message()
        env = EventEnvelope.from_message(msg, extra_metadata={"run_id_missing": True})
        assert env.metadata.get("run_id_missing") is True

    def test_timestamp_is_iso_format(self):
        msg = _make_message()
        env = EventEnvelope.from_message(msg)
        # Should parse as ISO-8601
        from datetime import datetime
        dt = datetime.fromisoformat(env.timestamp)
        assert dt.tzinfo is not None  # UTC timezone-aware


# ===========================================================================
# JsonlEventStore – append / iter
# ===========================================================================

class TestJsonlEventStoreAppendIter:
    def test_append_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            store.append(_make_envelope())
            expected_file = os.path.join(tmpdir, f"{RUN_ID}.jsonl")
            assert os.path.isfile(expected_file)

    def test_iter_returns_envelopes_in_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            topics = ["analysis.completed", "quality.scored", "decision.made"]
            for topic in topics:
                store.append(_make_envelope(topic=topic))

            result = list(store.iter(RUN_ID))
            assert len(result) == 3
            assert [e.topic for e in result] == topics

    def test_iter_returns_nothing_for_unknown_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            result = list(store.iter("nonexistent-run"))
            assert result == []

    def test_multiple_appends_are_cumulative(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            for i in range(5):
                store.append(_make_envelope(payload={"i": i}))
            result = list(store.iter(RUN_ID))
            assert len(result) == 5
            assert [e.payload["i"] for e in result] == list(range(5))

    def test_different_runs_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            store.append(_make_envelope(run_id="run-a", topic="quality.scored"))
            store.append(_make_envelope(run_id="run-b", topic="decision.made"))
            assert [e.topic for e in store.iter("run-a")] == ["quality.scored"]
            assert [e.topic for e in store.iter("run-b")] == ["decision.made"]

    def test_each_line_is_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            store.append(_make_envelope())
            path = os.path.join(tmpdir, f"{RUN_ID}.jsonl")
            with open(path) as fh:
                lines = [l.strip() for l in fh if l.strip()]
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["run_id"] == RUN_ID

    def test_malformed_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            store.append(_make_envelope(topic="quality.scored"))
            path = os.path.join(tmpdir, f"{RUN_ID}.jsonl")
            # inject a malformed line in the middle
            with open(path, "a") as fh:
                fh.write("NOT VALID JSON\n")
            store.append(_make_envelope(topic="decision.made"))

            result = list(store.iter(RUN_ID))
            # malformed line is skipped
            assert len(result) == 2
            assert result[0].topic == "quality.scored"
            assert result[1].topic == "decision.made"


# ===========================================================================
# JsonlEventStore – latest()
# ===========================================================================

class TestJsonlEventStoreLatest:
    def test_latest_returns_last_appended(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            store.append(_make_envelope(topic="quality.scored"))
            store.append(_make_envelope(topic="decision.made"))
            latest = store.latest(RUN_ID)
            assert latest is not None
            assert latest.topic == "decision.made"

    def test_latest_with_topic_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            store.append(_make_envelope(topic="quality.scored"))
            store.append(_make_envelope(topic="decision.made"))
            store.append(_make_envelope(topic="quality.scored"))
            latest = store.latest(RUN_ID, topic="decision.made")
            assert latest is not None
            assert latest.topic == "decision.made"

    def test_latest_returns_none_for_empty_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            assert store.latest("no-such-run") is None

    def test_latest_returns_none_when_topic_not_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            store.append(_make_envelope(topic="quality.scored"))
            assert store.latest(RUN_ID, topic="outcome.recorded") is None


# ===========================================================================
# JsonlEventStore – list()
# ===========================================================================

class TestJsonlEventStoreList:
    def test_list_returns_all_in_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            for i in range(3):
                store.append(_make_envelope(payload={"seq": i}))
            result = store.list(RUN_ID)
            assert isinstance(result, list)
            assert [e.payload["seq"] for e in result] == [0, 1, 2]


# ===========================================================================
# JsonlEventStore – per-run file path generation
# ===========================================================================

class TestJsonlEventStorePathGeneration:
    def test_file_is_under_base_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            store.append(_make_envelope())
            files = os.listdir(tmpdir)
            assert len(files) == 1
            assert files[0].endswith(".jsonl")
            assert files[0].startswith(RUN_ID)

    def test_traversal_run_id_raises_on_append(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            env = EventEnvelope(
                timestamp="2026-01-01T00:00:00+00:00",
                run_id="../evil",
                topic="quality.scored",
                sender_id="attacker",
                payload={},
                metadata={},
            )
            with pytest.raises(ValueError, match="path-traversal"):
                store.append(env)

    def test_traversal_run_id_raises_on_iter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            with pytest.raises(ValueError, match="path-traversal"):
                list(store.iter("../evil"))

    def test_traversal_run_id_raises_on_latest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            with pytest.raises(ValueError, match="path-traversal"):
                store.latest("../../etc/passwd")

    def test_special_chars_sanitised_in_filename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlEventStore(base_dir=tmpdir)
            env = _make_envelope(run_id="run with spaces")
            store.append(env)
            files = os.listdir(tmpdir)
            assert len(files) == 1
            assert " " not in files[0]

    def test_base_dir_property(self):
        store = JsonlEventStore(base_dir="/some/path")
        assert store.base_dir == "/some/path"


# ===========================================================================
# JsonlEventStore – ENV override
# ===========================================================================

class TestJsonlEventStoreEnvOverride:
    def test_env_var_overrides_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.environ.get("GENUS_EVENTSTORE_DIR")
            try:
                os.environ["GENUS_EVENTSTORE_DIR"] = tmpdir
                store = JsonlEventStore()  # no explicit base_dir
                assert store.base_dir == tmpdir
            finally:
                if old is None:
                    os.environ.pop("GENUS_EVENTSTORE_DIR", None)
                else:
                    os.environ["GENUS_EVENTSTORE_DIR"] = old

    def test_explicit_base_dir_wins_over_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.environ.get("GENUS_EVENTSTORE_DIR")
            try:
                os.environ["GENUS_EVENTSTORE_DIR"] = "/should/be/ignored"
                store = JsonlEventStore(base_dir=tmpdir)
                assert store.base_dir == tmpdir
            finally:
                if old is None:
                    os.environ.pop("GENUS_EVENTSTORE_DIR", None)
                else:
                    os.environ["GENUS_EVENTSTORE_DIR"] = old

    def test_default_base_dir_used_when_no_env(self):
        old = os.environ.get("GENUS_EVENTSTORE_DIR")
        try:
            os.environ.pop("GENUS_EVENTSTORE_DIR", None)
            store = JsonlEventStore()
            assert store.base_dir == "var/events"
        finally:
            if old is not None:
                os.environ["GENUS_EVENTSTORE_DIR"] = old

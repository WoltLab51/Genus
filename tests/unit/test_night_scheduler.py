"""
Tests for genus.memory.night_scheduler — Phase 14b
"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from genus.communication.message_bus import Message, MessageBus
from genus.memory.night_scheduler import NightScheduler, _TOPIC_COMPRESS_REQUESTED


# ---------------------------------------------------------------------------
# _load_compressed_sessions()
# ---------------------------------------------------------------------------

class TestLoadCompressedSessions:
    def test_returns_empty_set_when_no_file(self, tmp_path):
        bus = MessageBus()
        sched = NightScheduler(
            bus,
            conversations_dir=str(tmp_path / "conversations"),
            compressed_log=str(tmp_path / "compressed.jsonl"),
        )
        result = sched._load_compressed_sessions()
        assert result == set()

    def test_returns_session_ids_from_log(self, tmp_path):
        log = tmp_path / "compressed.jsonl"
        log.write_text(
            json.dumps({"session_id": "sess-1"}) + "\n" +
            json.dumps({"session_id": "sess-2"}) + "\n"
        )
        bus = MessageBus()
        sched = NightScheduler(
            bus,
            conversations_dir=str(tmp_path / "conversations"),
            compressed_log=str(log),
        )
        result = sched._load_compressed_sessions()
        assert "sess-1" in result
        assert "sess-2" in result


# ---------------------------------------------------------------------------
# _mark_compressed() + _load_compressed_sessions()
# ---------------------------------------------------------------------------

class TestMarkCompressed:
    def test_mark_then_load_contains_session_id(self, tmp_path):
        log = tmp_path / "compressed.jsonl"
        bus = MessageBus()
        sched = NightScheduler(
            bus,
            conversations_dir=str(tmp_path / "conversations"),
            compressed_log=str(log),
        )
        sched._mark_compressed("my-session-abc")
        sessions = sched._load_compressed_sessions()
        assert "my-session-abc" in sessions

    def test_mark_multiple_sessions(self, tmp_path):
        log = tmp_path / "compressed.jsonl"
        bus = MessageBus()
        sched = NightScheduler(
            bus,
            conversations_dir=str(tmp_path / "conversations"),
            compressed_log=str(log),
        )
        for sid in ["a", "b", "c"]:
            sched._mark_compressed(sid)
        sessions = sched._load_compressed_sessions()
        assert sessions == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# _run_nightly_compression()
# ---------------------------------------------------------------------------

class TestRunNightlyCompression:
    def _make_scheduler(self, tmp_path) -> NightScheduler:
        bus = MessageBus()
        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir()
        compressed_log = tmp_path / "compressed.jsonl"
        sched = NightScheduler(
            bus,
            conversations_dir=str(conv_dir),
            compressed_log=str(compressed_log),
        )
        return sched, bus, conv_dir

    async def test_publishes_compress_requested_for_new_sessions(self, tmp_path):
        sched, bus, conv_dir = self._make_scheduler(tmp_path)

        # Create a conversation JSONL file
        session_file = conv_dir / "sess-001.jsonl"
        session_file.write_text(
            json.dumps({"role": "user", "content": "Hallo"}) + "\n"
        )

        published = []
        bus.subscribe(_TOPIC_COMPRESS_REQUESTED, "spy", lambda m: published.append(m))

        await sched._run_nightly_compression()

        assert len(published) == 1
        assert published[0].payload["session_id"] == "sess-001"

    async def test_skips_already_compressed_sessions(self, tmp_path):
        sched, bus, conv_dir = self._make_scheduler(tmp_path)

        session_file = conv_dir / "sess-old.jsonl"
        session_file.write_text(
            json.dumps({"role": "user", "content": "Alt"}) + "\n"
        )
        sched._mark_compressed("sess-old")

        published = []
        bus.subscribe(_TOPIC_COMPRESS_REQUESTED, "spy", lambda m: published.append(m))

        await sched._run_nightly_compression()

        assert published == []

    async def test_skips_empty_session_files(self, tmp_path):
        sched, bus, conv_dir = self._make_scheduler(tmp_path)

        # Empty file
        (conv_dir / "sess-empty.jsonl").write_text("")

        published = []
        bus.subscribe(_TOPIC_COMPRESS_REQUESTED, "spy", lambda m: published.append(m))

        await sched._run_nightly_compression()

        assert published == []

    async def test_publishes_only_new_sessions(self, tmp_path):
        """Already-compressed sessions must be skipped; new ones must be published."""
        sched, bus, conv_dir = self._make_scheduler(tmp_path)

        for sid in ["new-1", "new-2", "old-1"]:
            (conv_dir / f"{sid}.jsonl").write_text(
                json.dumps({"role": "user", "content": "test"}) + "\n"
            )
        sched._mark_compressed("old-1")

        published = []
        bus.subscribe(_TOPIC_COMPRESS_REQUESTED, "spy", lambda m: published.append(m))

        await sched._run_nightly_compression()

        session_ids = {m.payload["session_id"] for m in published}
        assert "new-1" in session_ids
        assert "new-2" in session_ids
        assert "old-1" not in session_ids

    async def test_no_conversations_dir_does_not_raise(self, tmp_path):
        """If the conversations dir does not exist, the method should not raise."""
        bus = MessageBus()
        sched = NightScheduler(
            bus,
            conversations_dir=str(tmp_path / "nonexistent"),
            compressed_log=str(tmp_path / "compressed.jsonl"),
        )
        # Must not raise
        await sched._run_nightly_compression()


# ---------------------------------------------------------------------------
# start() / stop()
# ---------------------------------------------------------------------------

class TestStartStop:
    async def test_start_creates_task(self, tmp_path):
        bus = MessageBus()
        sched = NightScheduler(
            bus,
            conversations_dir=str(tmp_path / "conversations"),
            compressed_log=str(tmp_path / "compressed.jsonl"),
        )
        sched.start()
        assert sched._task is not None
        assert not sched._task.done()
        sched.stop()
        await asyncio.sleep(0.05)  # let cancellation propagate

    async def test_stop_cancels_task(self, tmp_path):
        bus = MessageBus()
        sched = NightScheduler(
            bus,
            conversations_dir=str(tmp_path / "conversations"),
            compressed_log=str(tmp_path / "compressed.jsonl"),
        )
        sched.start()
        task = sched._task
        sched.stop()
        await asyncio.sleep(0.05)
        assert task is not None
        assert task.cancelled() or task.done()

"""
Unit tests for EventRecorderAgent.

Covers:
- Records only whitelisted topics
- Non-whitelisted topics are silently ignored
- Missing run_id stored under 'unknown' with run_id_missing marker
- Custom record_topics whitelist respected
- All default whitelist topics are recorded
- Agent lifecycle (initialize / start / stop)
- data.sanitized opt-in via record_topics and GENUS_RECORD_TOPICS env var
"""

import os
import tempfile

import pytest

from genus.agents.event_recorder_agent import (
    DEFAULT_RECORD_TOPICS,
    EventRecorderAgent,
    _resolve_record_topics,
)
from genus.communication.message_bus import Message, MessageBus
from genus.memory.jsonl_event_store import JsonlEventStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = "2026-04-05T14-07-12Z__rec-test__xyz789"


def _make_message(
    topic: str,
    payload: dict | None = None,
    run_id: str | None = RUN_ID,
    sender_id: str = "some-agent",
) -> Message:
    metadata: dict = {}
    if run_id is not None:
        metadata["run_id"] = run_id
    return Message(
        topic=topic,
        payload=payload or {},
        sender_id=sender_id,
        metadata=metadata,
    )


async def _setup(
    tmpdir: str,
    record_topics: list | None = None,
) -> tuple[EventRecorderAgent, MessageBus, JsonlEventStore]:
    bus = MessageBus()
    store = JsonlEventStore(base_dir=tmpdir)
    agent = EventRecorderAgent(
        message_bus=bus,
        event_store=store,
        record_topics=record_topics,
    )
    await agent.initialize()
    await agent.start()
    return agent, bus, store


# ===========================================================================
# Default whitelist topics
# ===========================================================================

class TestDefaultWhitelist:
    def test_default_topics_list(self):
        assert "analysis.completed" in DEFAULT_RECORD_TOPICS
        assert "quality.scored" in DEFAULT_RECORD_TOPICS
        assert "decision.made" in DEFAULT_RECORD_TOPICS
        assert "outcome.recorded" in DEFAULT_RECORD_TOPICS

    def test_raw_data_not_in_default_whitelist(self):
        assert "data.collected" not in DEFAULT_RECORD_TOPICS


# ===========================================================================
# EventRecorderAgent – records whitelisted topics
# ===========================================================================

class TestEventRecorderAgentWhitelist:
    @pytest.mark.asyncio
    async def test_records_analysis_completed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            await bus.publish(_make_message("analysis.completed"))
            result = store.list(RUN_ID)
            assert len(result) == 1
            assert result[0].topic == "analysis.completed"

    @pytest.mark.asyncio
    async def test_records_quality_scored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            await bus.publish(_make_message("quality.scored"))
            result = store.list(RUN_ID)
            assert len(result) == 1
            assert result[0].topic == "quality.scored"

    @pytest.mark.asyncio
    async def test_records_decision_made(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            await bus.publish(_make_message("decision.made"))
            result = store.list(RUN_ID)
            assert len(result) == 1
            assert result[0].topic == "decision.made"

    @pytest.mark.asyncio
    async def test_records_outcome_recorded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            await bus.publish(_make_message("outcome.recorded"))
            result = store.list(RUN_ID)
            assert len(result) == 1
            assert result[0].topic == "outcome.recorded"

    @pytest.mark.asyncio
    async def test_does_not_record_data_collected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            await bus.publish(_make_message("data.collected"))
            result = store.list(RUN_ID)
            assert result == []

    @pytest.mark.asyncio
    async def test_does_not_record_unwhitelisted_topic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            await bus.publish(_make_message("some.random.topic"))
            result = store.list(RUN_ID)
            assert result == []

    @pytest.mark.asyncio
    async def test_records_multiple_whitelisted_messages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            await bus.publish(_make_message("analysis.completed"))
            await bus.publish(_make_message("quality.scored"))
            await bus.publish(_make_message("decision.made"))
            result = store.list(RUN_ID)
            assert len(result) == 3
            assert [e.topic for e in result] == [
                "analysis.completed",
                "quality.scored",
                "decision.made",
            ]


# ===========================================================================
# EventRecorderAgent – missing run_id
# ===========================================================================

class TestEventRecorderAgentMissingRunId:
    @pytest.mark.asyncio
    async def test_records_under_unknown_when_run_id_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            msg = Message(
                topic="quality.scored",
                payload={"quality_score": 0.8},
                sender_id="quality-agent",
                metadata={},  # no run_id
            )
            await bus.publish(msg)
            result = store.list("unknown")
            assert len(result) == 1
            assert result[0].run_id == "unknown"

    @pytest.mark.asyncio
    async def test_run_id_missing_marker_in_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            msg = Message(
                topic="quality.scored",
                payload={},
                sender_id="quality-agent",
                metadata={},
            )
            await bus.publish(msg)
            result = store.list("unknown")
            assert result[0].metadata.get("run_id_missing") is True

    @pytest.mark.asyncio
    async def test_with_run_id_no_missing_marker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            await bus.publish(_make_message("quality.scored", run_id=RUN_ID))
            result = store.list(RUN_ID)
            assert result[0].metadata.get("run_id_missing") is None


# ===========================================================================
# EventRecorderAgent – custom record_topics
# ===========================================================================

class TestEventRecorderAgentCustomTopics:
    @pytest.mark.asyncio
    async def test_custom_whitelist_records_only_listed_topics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(
                tmpdir, record_topics=["decision.made"]
            )
            await bus.publish(_make_message("analysis.completed"))
            await bus.publish(_make_message("quality.scored"))
            await bus.publish(_make_message("decision.made"))
            result = store.list(RUN_ID)
            assert len(result) == 1
            assert result[0].topic == "decision.made"

    @pytest.mark.asyncio
    async def test_empty_whitelist_records_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir, record_topics=[])
            for topic in DEFAULT_RECORD_TOPICS:
                await bus.publish(_make_message(topic))
            result = store.list(RUN_ID)
            assert result == []


# ===========================================================================
# EventRecorderAgent – lifecycle
# ===========================================================================

class TestEventRecorderAgentLifecycle:
    @pytest.mark.asyncio
    async def test_agent_can_be_stopped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            await agent.stop()
            # After stop, publishing should not record anything
            await bus.publish(_make_message("quality.scored"))
            result = store.list(RUN_ID)
            assert result == []

    @pytest.mark.asyncio
    async def test_agent_state_running_after_start(self):
        from genus.core.agent import AgentState

        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            assert agent.state == AgentState.RUNNING

    @pytest.mark.asyncio
    async def test_agent_state_stopped_after_stop(self):
        from genus.core.agent import AgentState

        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(tmpdir)
            await agent.stop()
            assert agent.state == AgentState.STOPPED


# ===========================================================================
# data.sanitized – opt-in persistence (P1-C2)
# ===========================================================================

class TestDataSanitizedOptIn:
    """Verify that data.sanitized is NOT persisted by default, but IS persisted
    when the operator explicitly opts in via record_topics or the
    GENUS_RECORD_TOPICS environment variable."""

    def test_data_sanitized_not_in_default_whitelist(self):
        assert "data.sanitized" not in DEFAULT_RECORD_TOPICS

    @pytest.mark.asyncio
    async def test_default_does_not_persist_data_sanitized(self):
        """Without opt-in, data.sanitized events must not be stored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use default (no record_topics argument, no env var)
            agent, bus, store = await _setup(tmpdir)
            await bus.publish(
                _make_message(
                    "data.sanitized",
                    payload={"source": "test", "data": {}, "evidence": {}},
                )
            )
            result = store.list(RUN_ID)
            assert result == [], "data.sanitized must not be persisted by default"

    @pytest.mark.asyncio
    async def test_opt_in_via_record_topics_persists_data_sanitized(self):
        """When record_topics explicitly includes data.sanitized, it must be stored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(
                tmpdir,
                record_topics=[*DEFAULT_RECORD_TOPICS, "data.sanitized"],
            )
            payload = {
                "source": "home-assistant",
                "data": {"sensor_type": "temperature", "value": 21.5},
                "evidence": {
                    "policy_id": "default",
                    "policy_version": "p1-c1",
                    "removed_fields": [],
                    "truncated_fields": [],
                    "blocked_by_policy": False,
                    "run_id_missing": False,
                },
            }
            await bus.publish(_make_message("data.sanitized", payload=payload))
            result = store.list(RUN_ID)
            assert len(result) == 1
            assert result[0].topic == "data.sanitized"
            assert result[0].payload["source"] == "home-assistant"

    @pytest.mark.asyncio
    async def test_opt_in_still_records_default_topics(self):
        """After opt-in, default whitelisted topics are still recorded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, bus, store = await _setup(
                tmpdir,
                record_topics=[*DEFAULT_RECORD_TOPICS, "data.sanitized"],
            )
            await bus.publish(_make_message("analysis.completed"))
            await bus.publish(_make_message("data.sanitized", payload={"source": "x"}))
            result = store.list(RUN_ID)
            assert len(result) == 2
            topics = [e.topic for e in result]
            assert "analysis.completed" in topics
            assert "data.sanitized" in topics


# ===========================================================================
# _resolve_record_topics – env var support (P1-C2)
# ===========================================================================

class TestResolveRecordTopics:
    """Unit tests for the _resolve_record_topics helper."""

    def test_explicit_list_wins_over_env(self):
        old = os.environ.get("GENUS_RECORD_TOPICS")
        try:
            os.environ["GENUS_RECORD_TOPICS"] = "quality.scored"
            result = _resolve_record_topics(["decision.made"])
            assert result == ["decision.made"]
        finally:
            if old is None:
                os.environ.pop("GENUS_RECORD_TOPICS", None)
            else:
                os.environ["GENUS_RECORD_TOPICS"] = old

    def test_env_var_used_when_no_explicit_list(self):
        old = os.environ.get("GENUS_RECORD_TOPICS")
        try:
            os.environ["GENUS_RECORD_TOPICS"] = (
                "analysis.completed,quality.scored,data.sanitized"
            )
            result = _resolve_record_topics(None)
            assert result == ["analysis.completed", "quality.scored", "data.sanitized"]
        finally:
            if old is None:
                os.environ.pop("GENUS_RECORD_TOPICS", None)
            else:
                os.environ["GENUS_RECORD_TOPICS"] = old

    def test_default_used_when_no_explicit_and_no_env(self):
        old = os.environ.get("GENUS_RECORD_TOPICS")
        try:
            os.environ.pop("GENUS_RECORD_TOPICS", None)
            result = _resolve_record_topics(None)
            assert result == DEFAULT_RECORD_TOPICS
        finally:
            if old is not None:
                os.environ["GENUS_RECORD_TOPICS"] = old

    def test_empty_env_var_falls_back_to_default(self):
        old = os.environ.get("GENUS_RECORD_TOPICS")
        try:
            os.environ["GENUS_RECORD_TOPICS"] = ""
            result = _resolve_record_topics(None)
            assert result == DEFAULT_RECORD_TOPICS
        finally:
            if old is None:
                os.environ.pop("GENUS_RECORD_TOPICS", None)
            else:
                os.environ["GENUS_RECORD_TOPICS"] = old

    @pytest.mark.asyncio
    async def test_env_var_opt_in_persists_data_sanitized(self):
        """Integration: GENUS_RECORD_TOPICS env var enables data.sanitized persistence."""
        old = os.environ.get("GENUS_RECORD_TOPICS")
        try:
            os.environ["GENUS_RECORD_TOPICS"] = (
                "analysis.completed,quality.scored,decision.made,"
                "outcome.recorded,data.sanitized"
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                # record_topics=None → picks up env var
                agent, bus, store = await _setup(tmpdir, record_topics=None)
                await bus.publish(
                    _make_message("data.sanitized", payload={"source": "env-test"})
                )
                result = store.list(RUN_ID)
                assert len(result) == 1
                assert result[0].topic == "data.sanitized"
        finally:
            if old is None:
                os.environ.pop("GENUS_RECORD_TOPICS", None)
            else:
                os.environ["GENUS_RECORD_TOPICS"] = old

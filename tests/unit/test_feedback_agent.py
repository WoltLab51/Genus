"""
Unit tests for FeedbackAgent.

Covers:
- Lifecycle (initialize / start / stop)
- Happy path: good/bad/unknown outcome writes journal event + artifact,
  publishes feedback.received
- Drop conditions: missing run_id, "unknown" run_id, invalid payload,
  journal_factory returns None
- Journal failure tolerance: log_event or save_artifact raises, agent continues
"""

import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import AgentState
from genus.feedback.agent import FeedbackAgent
from genus.feedback.topics import FEEDBACK_RECEIVED, OUTCOME_RECORDED
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = "2026-04-07T10-00-00Z__feedbacktest__abc123"


def _make_journal(run_id: str = RUN_ID) -> RunJournal:
    tmpdir = tempfile.mkdtemp()
    store = JsonlRunStore(base_dir=Path(tmpdir))
    journal = RunJournal(run_id=run_id, store=store)
    journal.initialize(goal="feedback test")
    return journal


def _make_outcome_message(
    outcome: str = "good",
    score_delta: float = 1.0,
    run_id: str = RUN_ID,
    source: str = "user",
    notes: Optional[str] = None,
) -> Message:
    payload: dict = {"outcome": outcome, "score_delta": score_delta, "source": source}
    if notes:
        payload["notes"] = notes
    return Message(
        topic=OUTCOME_RECORDED,
        payload=payload,
        sender_id="OutcomeCLI",
        metadata={"run_id": run_id},
    )


async def _make_agent(
    bus: MessageBus,
    journal: Optional[RunJournal] = None,
) -> FeedbackAgent:
    """Create, initialize, and start a FeedbackAgent backed by *journal*."""
    j = journal or _make_journal()

    def factory(run_id: str) -> Optional[RunJournal]:
        return j if run_id == j.run_id else None

    agent = FeedbackAgent(message_bus=bus, journal_factory=factory)
    await agent.initialize()
    await agent.start()
    return agent


# ===========================================================================
# Lifecycle
# ===========================================================================

class TestFeedbackAgentLifecycle:
    @pytest.mark.asyncio
    async def test_initializes_subscribes_to_outcome_recorded(self):
        bus = MessageBus()
        journal = _make_journal()
        agent = FeedbackAgent(
            message_bus=bus,
            journal_factory=lambda rid: journal,
        )
        await agent.initialize()
        assert OUTCOME_RECORDED in bus.get_topics()

    @pytest.mark.asyncio
    async def test_stop_unsubscribes(self):
        bus = MessageBus()
        journal = _make_journal()
        agent = FeedbackAgent(
            message_bus=bus,
            journal_factory=lambda rid: journal,
        )
        await agent.initialize()
        await agent.start()
        assert agent.state == AgentState.RUNNING

        await agent.stop()
        assert agent.state == AgentState.STOPPED
        # After stop, publishing should not deliver to agent callback
        received: list = []
        bus.subscribe(OUTCOME_RECORDED, "spy", lambda m: received.append(m))
        await bus.publish(_make_outcome_message())
        # spy gets it but agent callback is gone — no crash
        assert len(received) == 1


# ===========================================================================
# Happy path
# ===========================================================================

class TestFeedbackAgentHappyPath:
    @pytest.mark.asyncio
    async def test_good_outcome_writes_journal_event(self):
        bus = MessageBus()
        journal = _make_journal()
        await _make_agent(bus, journal)

        await bus.publish(_make_outcome_message(outcome="good"))

        events = journal.get_events(phase="feedback", event_type="feedback.received")
        assert len(events) == 1
        assert events[0].data["outcome"] == "good"

    @pytest.mark.asyncio
    async def test_bad_outcome_writes_journal_event(self):
        bus = MessageBus()
        journal = _make_journal()
        await _make_agent(bus, journal)

        await bus.publish(_make_outcome_message(outcome="bad", score_delta=-1.0))

        events = journal.get_events(phase="feedback", event_type="feedback.received")
        assert len(events) == 1
        assert events[0].data["outcome"] == "bad"
        assert events[0].data["score_delta"] == -1.0

    @pytest.mark.asyncio
    async def test_unknown_outcome_writes_journal_event(self):
        bus = MessageBus()
        journal = _make_journal()
        await _make_agent(bus, journal)

        await bus.publish(_make_outcome_message(outcome="unknown", score_delta=0.0))

        events = journal.get_events(phase="feedback", event_type="feedback.received")
        assert len(events) == 1
        assert events[0].data["outcome"] == "unknown"

    @pytest.mark.asyncio
    async def test_publishes_feedback_received_event(self):
        bus = MessageBus()
        journal = _make_journal()
        await _make_agent(bus, journal)

        received: list = []
        bus.subscribe(FEEDBACK_RECEIVED, "spy", lambda m: received.append(m))

        await bus.publish(_make_outcome_message())

        assert len(received) == 1
        assert received[0].topic == FEEDBACK_RECEIVED

    @pytest.mark.asyncio
    async def test_feedback_received_payload_structure(self):
        bus = MessageBus()
        journal = _make_journal()
        await _make_agent(bus, journal)

        received: list = []
        bus.subscribe(FEEDBACK_RECEIVED, "spy", lambda m: received.append(m))

        await bus.publish(_make_outcome_message(outcome="bad", score_delta=-2.5, source="operator"))

        msg = received[0]
        assert msg.payload["run_id"] == RUN_ID
        assert msg.payload["outcome"] == "bad"
        assert msg.payload["score_delta"] == -2.5
        assert msg.payload["source"] == "operator"

    @pytest.mark.asyncio
    async def test_saves_artifact_with_correct_type(self):
        bus = MessageBus()
        journal = _make_journal()
        await _make_agent(bus, journal)

        await bus.publish(_make_outcome_message(outcome="good", score_delta=1.0))

        artifact_ids = journal.list_artifacts(artifact_type="feedback_record")
        assert len(artifact_ids) == 1

        artifact = journal.load_artifact(artifact_ids[0])
        assert artifact is not None
        assert artifact.artifact_type == "feedback_record"
        assert artifact.payload["outcome"] == "good"
        assert artifact.payload["score_delta"] == 1.0


# ===========================================================================
# Drop conditions
# ===========================================================================

class TestFeedbackAgentDropConditions:
    @pytest.mark.asyncio
    async def test_drops_message_without_run_id(self):
        bus = MessageBus()
        journal = _make_journal()
        await _make_agent(bus, journal)

        msg = Message(
            topic=OUTCOME_RECORDED,
            payload={"outcome": "good", "score_delta": 1.0, "source": "user"},
            sender_id="OutcomeCLI",
            metadata={},  # no run_id
        )
        await bus.publish(msg)

        events = journal.get_events(phase="feedback")
        assert events == []

    @pytest.mark.asyncio
    async def test_drops_message_with_unknown_run_id(self):
        bus = MessageBus()
        journal = _make_journal()
        await _make_agent(bus, journal)

        msg = Message(
            topic=OUTCOME_RECORDED,
            payload={"outcome": "good", "score_delta": 1.0, "source": "user"},
            sender_id="OutcomeCLI",
            metadata={"run_id": "unknown"},
        )
        await bus.publish(msg)

        events = journal.get_events(phase="feedback")
        assert events == []

    @pytest.mark.asyncio
    async def test_drops_invalid_payload_missing_outcome(self):
        bus = MessageBus()
        journal = _make_journal()
        await _make_agent(bus, journal)

        msg = Message(
            topic=OUTCOME_RECORDED,
            payload={"score_delta": 1.0},  # missing outcome
            sender_id="OutcomeCLI",
            metadata={"run_id": RUN_ID},
        )
        await bus.publish(msg)

        events = journal.get_events(phase="feedback")
        assert events == []

    @pytest.mark.asyncio
    async def test_drops_invalid_payload_wrong_type(self):
        bus = MessageBus()
        journal = _make_journal()
        await _make_agent(bus, journal)

        msg = Message(
            topic=OUTCOME_RECORDED,
            payload="not-a-dict",  # wrong type
            sender_id="OutcomeCLI",
            metadata={"run_id": RUN_ID},
        )
        await bus.publish(msg)

        events = journal.get_events(phase="feedback")
        assert events == []

    @pytest.mark.asyncio
    async def test_drops_when_journal_factory_returns_none(self):
        bus = MessageBus()

        agent = FeedbackAgent(
            message_bus=bus,
            journal_factory=lambda rid: None,  # always returns None
        )
        await agent.initialize()
        await agent.start()

        received: list = []
        bus.subscribe(FEEDBACK_RECEIVED, "spy", lambda m: received.append(m))

        await bus.publish(_make_outcome_message())

        # No feedback.received published when journal is unavailable
        assert received == []


# ===========================================================================
# Journal failure tolerance
# ===========================================================================

class TestFeedbackAgentJournalFailure:
    @pytest.mark.asyncio
    async def test_continues_on_journal_log_event_failure(self):
        """If journal.log_event raises, agent does not crash and still publishes."""
        bus = MessageBus()
        journal = _make_journal()

        broken_journal = MagicMock(spec=RunJournal)
        broken_journal.run_id = RUN_ID
        broken_journal.log_event.side_effect = RuntimeError("disk full")
        broken_journal.save_artifact.return_value = "artifact-1"

        agent = FeedbackAgent(
            message_bus=bus,
            journal_factory=lambda rid: broken_journal,
        )
        await agent.initialize()
        await agent.start()

        received: list = []
        bus.subscribe(FEEDBACK_RECEIVED, "spy", lambda m: received.append(m))

        # Should not raise
        await bus.publish(_make_outcome_message())

        # feedback.received still published despite log_event failure
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_continues_on_journal_save_artifact_failure(self):
        """If journal.save_artifact raises, agent does not crash and still publishes."""
        bus = MessageBus()
        journal = _make_journal()

        broken_journal = MagicMock(spec=RunJournal)
        broken_journal.run_id = RUN_ID
        broken_journal.log_event.return_value = MagicMock()
        broken_journal.save_artifact.side_effect = RuntimeError("disk full")

        agent = FeedbackAgent(
            message_bus=bus,
            journal_factory=lambda rid: broken_journal,
        )
        await agent.initialize()
        await agent.start()

        received: list = []
        bus.subscribe(FEEDBACK_RECEIVED, "spy", lambda m: received.append(m))

        # Should not raise
        await bus.publish(_make_outcome_message())

        # feedback.received still published despite save_artifact failure
        assert len(received) == 1

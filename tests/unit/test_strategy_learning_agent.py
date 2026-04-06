"""
Unit tests for StrategyLearningAgent.

Tests the learning agent's ability to:
- Subscribe to meta.evaluation.completed events
- Extract evaluation and strategy decision artifacts
- Apply learning rules to update failure_class_weights
- Log learning events to journal
- Handle edge cases and errors gracefully
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.core.run import attach_run_id
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore
from genus.meta import topics as meta_topics
from genus.strategy.agents.learning_agent import (
    StrategyLearningAgent,
    WEIGHT_BOOST_THRESHOLD,
    WEIGHT_PENALTY_THRESHOLD,
    WEIGHT_CHANGE_BOOST,
    WEIGHT_CHANGE_PENALTY,
    WEIGHT_MIN,
    WEIGHT_MAX,
)
from genus.strategy.models import PlaybookId
from genus.strategy.store_json import StrategyStoreJson


# ---------------------------------------------------------------------------
# Test agent lifecycle
# ---------------------------------------------------------------------------

def test_learning_agent_init():
    """Test StrategyLearningAgent initialization."""
    bus = MessageBus()
    agent = StrategyLearningAgent(bus, agent_id="test-agent")
    assert agent.agent_id == "test-agent"
    assert agent._bus is bus


def test_learning_agent_start_stop():
    """Test agent start/stop lifecycle."""
    bus = MessageBus()
    agent = StrategyLearningAgent(bus, agent_id="test-agent")

    # Start should subscribe to meta.evaluation.completed
    agent.start()
    assert agent._started

    # Stop should unsubscribe
    agent.stop()
    assert not agent._started


# ---------------------------------------------------------------------------
# Test learning logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_learning_agent_processes_evaluation_completed():
    """Test agent processes meta.evaluation.completed events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test-agent",
            run_store=run_store,
            strategy_store=strategy_store,
        )
        agent.start()

        # Create a run with strategy decision and evaluation
        run_id = "test_run_001"
        journal = RunJournal(run_id, run_store)
        journal.initialize(goal="Test learning")

        # Save strategy decision artifact
        strategy_decision = {
            "run_id": run_id,
            "phase": "fix",
            "iteration": 1,
            "selected_playbook": PlaybookId.TARGET_FAILING_TEST_FIRST,
            "candidates": [PlaybookId.TARGET_FAILING_TEST_FIRST, PlaybookId.DEFAULT],
            "reason": "Test failure detected",
            "derived_from": {"failure_class": "test_failure"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        journal.save_artifact(
            phase="strategy",
            artifact_type="strategy_decision",
            payload=strategy_decision,
        )

        # Save evaluation artifact
        evaluation_artifact = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": 85,  # Success - should boost weight
            "final_status": "completed",
            "failure_class": "test_failure",
            "root_cause_hint": None,
            "highlights": ["Fixed the test"],
            "issues": [],
            "recommendations": [],
            "strategy_recommendations": [],
            "evidence": [],
        }
        journal.save_artifact(
            phase="meta",
            artifact_type="evaluation",
            payload=evaluation_artifact,
        )

        # Publish meta.evaluation.completed
        msg = Message(
            topic=meta_topics.META_EVALUATION_COMPLETED,
            payload={"score": 85, "failure_class": "test_failure"},
            sender_id="test",
        )
        msg = attach_run_id(msg, run_id)

        await bus.publish(msg)

        # Check that weight was updated
        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST
        )
        assert weight == WEIGHT_CHANGE_BOOST  # Should be +1

        # Check journal was updated
        events = journal.get_events(event_type="strategy_learned")
        assert len(events) == 1
        assert events[0].data["failure_class"] == "test_failure"
        assert events[0].data["new_weight"] == WEIGHT_CHANGE_BOOST

        agent.stop()


@pytest.mark.asyncio
async def test_learning_agent_penalty_on_failure():
    """Test agent penalizes playbook on failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test-agent",
            run_store=run_store,
            strategy_store=strategy_store,
        )
        agent.start()

        # Create a run with low score
        run_id = "test_run_002"
        journal = RunJournal(run_id, run_store)
        journal.initialize(goal="Test penalty")

        # Save strategy decision
        strategy_decision = {
            "run_id": run_id,
            "phase": "fix",
            "iteration": 1,
            "selected_playbook": PlaybookId.MINIMIZE_CHANGESET,
            "candidates": [PlaybookId.MINIMIZE_CHANGESET],
            "reason": "Try minimize",
            "derived_from": {"failure_class": "test_failure"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        journal.save_artifact(
            phase="strategy",
            artifact_type="strategy_decision",
            payload=strategy_decision,
        )

        # Save evaluation artifact with low score
        evaluation_artifact = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": 40,  # Failure - should penalize
            "final_status": "failed",
            "failure_class": "test_failure",
            "root_cause_hint": None,
            "highlights": [],
            "issues": ["Still failing"],
            "recommendations": [],
            "strategy_recommendations": [],
            "evidence": [],
        }
        journal.save_artifact(
            phase="meta",
            artifact_type="evaluation",
            payload=evaluation_artifact,
        )

        # Publish event
        msg = Message(
            topic=meta_topics.META_EVALUATION_COMPLETED,
            payload={"score": 40, "failure_class": "test_failure"},
            sender_id="test",
        )
        msg = attach_run_id(msg, run_id)

        await bus.publish(msg)

        # Check that weight was decreased
        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.MINIMIZE_CHANGESET
        )
        assert weight == WEIGHT_CHANGE_PENALTY  # Should be -1

        agent.stop()


@pytest.mark.asyncio
async def test_learning_agent_neutral_score_no_change():
    """Test agent does not change weights for neutral scores."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test-agent",
            run_store=run_store,
            strategy_store=strategy_store,
        )
        agent.start()

        # Create a run with neutral score
        run_id = "test_run_003"
        journal = RunJournal(run_id, run_store)
        journal.initialize(goal="Test neutral")

        strategy_decision = {
            "run_id": run_id,
            "phase": "fix",
            "iteration": 1,
            "selected_playbook": PlaybookId.DEFAULT,
            "candidates": [PlaybookId.DEFAULT],
            "reason": "Default",
            "derived_from": {"failure_class": "timeout"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        journal.save_artifact(
            phase="strategy",
            artifact_type="strategy_decision",
            payload=strategy_decision,
        )

        evaluation_artifact = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": 65,  # Neutral - no change
            "final_status": "completed",
            "failure_class": "timeout",
            "root_cause_hint": None,
            "highlights": [],
            "issues": [],
            "recommendations": [],
            "strategy_recommendations": [],
            "evidence": [],
        }
        journal.save_artifact(
            phase="meta",
            artifact_type="evaluation",
            payload=evaluation_artifact,
        )

        msg = Message(
            topic=meta_topics.META_EVALUATION_COMPLETED,
            payload={"score": 65, "failure_class": "timeout"},
            sender_id="test",
        )
        msg = attach_run_id(msg, run_id)

        await bus.publish(msg)

        # Check that weight was not changed
        weight = strategy_store.get_failure_class_weight("timeout", PlaybookId.DEFAULT)
        assert weight == 0  # Should remain 0

        # But event should be logged
        events = journal.get_events(event_type="strategy_learning_skipped")
        assert len(events) == 1
        assert "neutral" in events[0].data["reason"]

        agent.stop()


@pytest.mark.asyncio
async def test_learning_agent_weight_clamping():
    """Test agent clamps weights to valid range."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test-agent",
            run_store=run_store,
            strategy_store=strategy_store,
        )
        agent.start()

        # Set initial weight near max
        strategy_store.set_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST, WEIGHT_MAX
        )

        # Create successful run
        run_id = "test_run_004"
        journal = RunJournal(run_id, run_store)
        journal.initialize(goal="Test clamping")

        strategy_decision = {
            "run_id": run_id,
            "phase": "fix",
            "iteration": 1,
            "selected_playbook": PlaybookId.TARGET_FAILING_TEST_FIRST,
            "candidates": [PlaybookId.TARGET_FAILING_TEST_FIRST],
            "reason": "Test",
            "derived_from": {"failure_class": "test_failure"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        journal.save_artifact(
            phase="strategy",
            artifact_type="strategy_decision",
            payload=strategy_decision,
        )

        evaluation_artifact = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": 90,  # Success
            "final_status": "completed",
            "failure_class": "test_failure",
            "root_cause_hint": None,
            "highlights": [],
            "issues": [],
            "recommendations": [],
            "strategy_recommendations": [],
            "evidence": [],
        }
        journal.save_artifact(
            phase="meta",
            artifact_type="evaluation",
            payload=evaluation_artifact,
        )

        msg = Message(
            topic=meta_topics.META_EVALUATION_COMPLETED,
            payload={"score": 90, "failure_class": "test_failure"},
            sender_id="test",
        )
        msg = attach_run_id(msg, run_id)

        await bus.publish(msg)

        # Check that weight is still at max (clamped)
        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST
        )
        assert weight == WEIGHT_MAX  # Should be clamped to max

        agent.stop()


# ---------------------------------------------------------------------------
# Test edge cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_learning_agent_no_failure_class_skips():
    """Test agent skips learning when no failure_class."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test-agent",
            run_store=run_store,
            strategy_store=strategy_store,
        )
        agent.start()

        run_id = "test_run_005"
        journal = RunJournal(run_id, run_store)
        journal.initialize(goal="Test no failure_class")

        strategy_decision = {
            "run_id": run_id,
            "phase": "implement",
            "iteration": None,
            "selected_playbook": PlaybookId.DEFAULT,
            "candidates": [PlaybookId.DEFAULT],
            "reason": "First iteration",
            "derived_from": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        journal.save_artifact(
            phase="strategy",
            artifact_type="strategy_decision",
            payload=strategy_decision,
        )

        # No failure_class - successful run
        evaluation_artifact = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": 95,
            "final_status": "completed",
            "failure_class": None,  # No failure
            "root_cause_hint": None,
            "highlights": ["All good"],
            "issues": [],
            "recommendations": [],
            "strategy_recommendations": [],
            "evidence": [],
        }
        journal.save_artifact(
            phase="meta",
            artifact_type="evaluation",
            payload=evaluation_artifact,
        )

        msg = Message(
            topic=meta_topics.META_EVALUATION_COMPLETED,
            payload={"score": 95, "failure_class": None},
            sender_id="test",
        )
        msg = attach_run_id(msg, run_id)

        await bus.publish(msg)

        # No learning should occur
        events = journal.get_events(event_type="strategy_learned")
        assert len(events) == 0

        agent.stop()


@pytest.mark.asyncio
async def test_learning_agent_missing_artifacts_skips():
    """Test agent skips when artifacts are missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test-agent",
            run_store=run_store,
            strategy_store=strategy_store,
        )
        agent.start()

        run_id = "test_run_006"
        journal = RunJournal(run_id, run_store)
        journal.initialize(goal="Test missing artifacts")

        # Only save evaluation, no strategy decision
        evaluation_artifact = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": 85,
            "final_status": "completed",
            "failure_class": "test_failure",
            "root_cause_hint": None,
            "highlights": [],
            "issues": [],
            "recommendations": [],
            "strategy_recommendations": [],
            "evidence": [],
        }
        journal.save_artifact(
            phase="meta",
            artifact_type="evaluation",
            payload=evaluation_artifact,
        )

        msg = Message(
            topic=meta_topics.META_EVALUATION_COMPLETED,
            payload={"score": 85, "failure_class": "test_failure"},
            sender_id="test",
        )
        msg = attach_run_id(msg, run_id)

        await bus.publish(msg)

        # No learning should occur (no strategy decision)
        events = journal.get_events(event_type="strategy_learned")
        assert len(events) == 0

        agent.stop()


@pytest.mark.asyncio
async def test_learning_agent_no_run_id_skips():
    """Test agent skips when message has no run_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test-agent",
        )
        agent.start()

        # Publish message without run_id
        msg = Message(
            topic=meta_topics.META_EVALUATION_COMPLETED,
            payload={"score": 85, "failure_class": "test_failure"},
            sender_id="test",
        )
        # No run_id attached

        await bus.publish(msg)

        # Should not crash, just skip
        # (No way to verify beyond no crash)

        agent.stop()


@pytest.mark.asyncio
async def test_learning_agent_error_handling():
    """Test agent logs errors instead of crashing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test-agent",
            run_store=run_store,
        )
        agent.start()

        run_id = "test_run_007"
        journal = RunJournal(run_id, run_store)
        journal.initialize(goal="Test error handling")

        # Save malformed evaluation artifact (missing score)
        evaluation_artifact = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            # Missing "score" field
            "final_status": "completed",
            "failure_class": "test_failure",
        }
        journal.save_artifact(
            phase="meta",
            artifact_type="evaluation",
            payload=evaluation_artifact,
        )

        strategy_decision = {
            "run_id": run_id,
            "selected_playbook": PlaybookId.DEFAULT,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        journal.save_artifact(
            phase="strategy",
            artifact_type="strategy_decision",
            payload=strategy_decision,
        )

        msg = Message(
            topic=meta_topics.META_EVALUATION_COMPLETED,
            payload={},
            sender_id="test",
        )
        msg = attach_run_id(msg, run_id)

        await bus.publish(msg)

        # Should not crash, should log skipped event
        events = journal.get_events(event_type="strategy_learning_skipped")
        assert len(events) > 0

        agent.stop()

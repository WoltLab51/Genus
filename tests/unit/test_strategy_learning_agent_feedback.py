"""
Unit tests for StrategyLearningAgent._handle_feedback_received.

Tests the new feedback.received handler that closes the human-feedback
learning loop by applying score_delta to strategy weights.
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.core.run import attach_run_id
from genus.feedback.topics import FEEDBACK_RECEIVED
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore
from genus.strategy.agents.learning_agent import (
    FEEDBACK_SCORE_DELTA_NEGATIVE_THRESHOLD,
    FEEDBACK_SCORE_DELTA_POSITIVE_THRESHOLD,
    WEIGHT_MAX,
    WEIGHT_MIN,
    StrategyLearningAgent,
)
from genus.strategy.models import PlaybookId
from genus.strategy.store_json import StrategyStoreJson


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feedback_msg(
    run_id=None,
    outcome="good",
    score_delta=5.0,
    source="operator",
):
    """Build a feedback.received Message, optionally with run_id attached."""
    payload = {
        "outcome": outcome,
        "score_delta": score_delta,
        "source": source,
    }
    if run_id:
        payload["run_id"] = run_id
    msg = Message(
        topic=FEEDBACK_RECEIVED,
        payload=payload,
        sender_id="FeedbackAgent",
        metadata={"run_id": run_id} if run_id else {},
    )
    return msg


def _setup_run(run_store, run_id, failure_class="test_failure",
               selected_playbook=None, include_strategy=True, include_evaluation=True):
    """Create a run journal with optional strategy_decision and evaluation artifacts."""
    if selected_playbook is None:
        selected_playbook = PlaybookId.TARGET_FAILING_TEST_FIRST
    journal = RunJournal(run_id, run_store)
    journal.initialize(goal="Test feedback learning")

    if include_strategy:
        journal.save_artifact(
            phase="strategy",
            artifact_type="strategy_decision",
            payload={
                "run_id": run_id,
                "phase": "fix",
                "iteration": 1,
                "selected_playbook": selected_playbook,
                "candidates": [selected_playbook],
                "reason": "Test",
                "derived_from": {"failure_class": failure_class},
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    if include_evaluation:
        journal.save_artifact(
            phase="meta",
            artifact_type="evaluation",
            payload={
                "run_id": run_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "score": 75,
                "final_status": "completed",
                "failure_class": failure_class,
                "root_cause_hint": None,
                "highlights": [],
                "issues": [],
                "recommendations": [],
                "strategy_recommendations": [],
                "evidence": [],
            },
        )

    return journal


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feedback_good_outcome_boosts_weight():
    """feedback.received with outcome='good', score_delta=5.0 → weight += 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus, agent_id="test-agent",
            run_store=run_store, strategy_store=strategy_store,
        )
        agent.start()

        run_id = "fb_test_001"
        journal = _setup_run(run_store, run_id)

        msg = _make_feedback_msg(run_id=run_id, outcome="good", score_delta=5.0)
        await bus.publish(msg)

        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST
        )
        assert weight == 1, f"Expected weight=1, got {weight}"

        events = journal.get_events(event_type="feedback_learning_applied")
        assert len(events) == 1
        assert events[0].data["weight_change"] == 1
        assert events[0].data["failure_class"] == "test_failure"

        agent.stop()


@pytest.mark.asyncio
async def test_feedback_bad_outcome_penalizes_weight():
    """feedback.received with outcome='bad', score_delta=-5.0 → weight -= 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus, agent_id="test-agent",
            run_store=run_store, strategy_store=strategy_store,
        )
        agent.start()

        run_id = "fb_test_002"
        _setup_run(run_store, run_id, selected_playbook=PlaybookId.MINIMIZE_CHANGESET)

        msg = _make_feedback_msg(run_id=run_id, outcome="bad", score_delta=-5.0)
        await bus.publish(msg)

        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.MINIMIZE_CHANGESET
        )
        assert weight == -1, f"Expected weight=-1, got {weight}"

        agent.stop()


@pytest.mark.asyncio
async def test_feedback_unknown_outcome_no_weight_update(caplog):
    """feedback.received with outcome='unknown' → no weight update, journal log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus, agent_id="test-agent",
            run_store=run_store, strategy_store=strategy_store,
        )
        agent.start()

        run_id = "fb_test_003"
        journal = _setup_run(run_store, run_id)

        msg = _make_feedback_msg(run_id=run_id, outcome="unknown", score_delta=0.0)
        await bus.publish(msg)

        # Weight should remain 0
        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST
        )
        assert weight == 0

        # Journal should have a skipped event
        events = journal.get_events(event_type="feedback_learning_skipped")
        assert len(events) == 1

        agent.stop()


@pytest.mark.asyncio
async def test_feedback_neutral_score_delta_no_weight_update():
    """feedback.received with score_delta=1.0 (below threshold) → no weight update."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus, agent_id="test-agent",
            run_store=run_store, strategy_store=strategy_store,
        )
        agent.start()

        run_id = "fb_test_004"
        journal = _setup_run(run_store, run_id)

        # score_delta=1.0 is between -3.0 and 3.0 — neutral
        msg = _make_feedback_msg(run_id=run_id, outcome="good", score_delta=1.0)
        await bus.publish(msg)

        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST
        )
        assert weight == 0

        # Skipped event should be logged
        events = journal.get_events(event_type="feedback_learning_skipped")
        assert len(events) == 1
        assert events[0].data.get("reason") == "neutral_score_delta"

        agent.stop()


@pytest.mark.asyncio
async def test_feedback_missing_run_id_logs_warning(caplog):
    """feedback.received without run_id → warning logged, no crash."""
    bus = MessageBus()
    agent = StrategyLearningAgent(bus=bus, agent_id="test-agent")
    agent.start()

    # Message has no run_id in metadata or payload
    msg = Message(
        topic=FEEDBACK_RECEIVED,
        payload={"outcome": "good", "score_delta": 5.0, "source": "operator"},
        sender_id="test",
    )

    import logging
    with caplog.at_level(logging.WARNING):
        await bus.publish(msg)

    assert any("run_id" in rec.message for rec in caplog.records)

    agent.stop()


@pytest.mark.asyncio
async def test_feedback_run_without_journal_logs_debug(caplog):
    """feedback.received for run with no journal → debug log, no crash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        bus = MessageBus()

        agent = StrategyLearningAgent(bus=bus, agent_id="test-agent", run_store=run_store)
        agent.start()

        run_id = "fb_nonexistent_run"
        # No journal created for this run_id

        msg = _make_feedback_msg(run_id=run_id, outcome="good", score_delta=5.0)

        import logging
        with caplog.at_level(logging.DEBUG):
            await bus.publish(msg)

        # Should log debug about missing journal
        assert any("journal" in rec.message.lower() or "does not exist" in rec.message
                   for rec in caplog.records)

        agent.stop()


@pytest.mark.asyncio
async def test_feedback_run_without_strategy_decision():
    """feedback.received for run with no strategy_decision artifact → info, no weight update."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus, agent_id="test-agent",
            run_store=run_store, strategy_store=strategy_store,
        )
        agent.start()

        run_id = "fb_test_007"
        # include_strategy=False: no strategy_decision artifact
        _setup_run(run_store, run_id, include_strategy=False)

        msg = _make_feedback_msg(run_id=run_id, outcome="good", score_delta=5.0)
        await bus.publish(msg)

        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST
        )
        assert weight == 0

        agent.stop()


@pytest.mark.asyncio
async def test_feedback_run_without_evaluation_artifact():
    """feedback.received for run with no evaluation artifact → info, no weight update."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus, agent_id="test-agent",
            run_store=run_store, strategy_store=strategy_store,
        )
        agent.start()

        run_id = "fb_test_008"
        # include_evaluation=False: no evaluation artifact
        _setup_run(run_store, run_id, include_evaluation=False)

        msg = _make_feedback_msg(run_id=run_id, outcome="good", score_delta=5.0)
        await bus.publish(msg)

        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST
        )
        assert weight == 0

        agent.stop()


@pytest.mark.asyncio
async def test_feedback_run_with_none_failure_class():
    """feedback.received for run with failure_class=None → debug, no weight update."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus, agent_id="test-agent",
            run_store=run_store, strategy_store=strategy_store,
        )
        agent.start()

        run_id = "fb_test_009"
        # Setup run with failure_class=None (clean run)
        _setup_run(run_store, run_id, failure_class=None)

        msg = _make_feedback_msg(run_id=run_id, outcome="good", score_delta=5.0)
        await bus.publish(msg)

        # No weight update should have occurred
        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST
        )
        assert weight == 0

        agent.stop()


@pytest.mark.asyncio
async def test_feedback_weight_clamped_at_max():
    """Weight at WEIGHT_MAX + feedback 'good' → stays at WEIGHT_MAX."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus, agent_id="test-agent",
            run_store=run_store, strategy_store=strategy_store,
        )
        agent.start()

        run_id = "fb_test_010"
        # Pre-set weight to WEIGHT_MAX
        strategy_store.set_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST, WEIGHT_MAX
        )

        _setup_run(run_store, run_id)

        msg = _make_feedback_msg(run_id=run_id, outcome="good", score_delta=5.0)
        await bus.publish(msg)

        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST
        )
        assert weight == WEIGHT_MAX, f"Expected clamped weight={WEIGHT_MAX}, got {weight}"

        agent.stop()


@pytest.mark.asyncio
async def test_feedback_weight_clamped_at_min():
    """Weight at WEIGHT_MIN + feedback 'bad' → stays at WEIGHT_MIN."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus, agent_id="test-agent",
            run_store=run_store, strategy_store=strategy_store,
        )
        agent.start()

        run_id = "fb_test_011"
        # Pre-set weight to WEIGHT_MIN
        strategy_store.set_failure_class_weight(
            "test_failure", PlaybookId.MINIMIZE_CHANGESET, WEIGHT_MIN
        )

        _setup_run(run_store, run_id, selected_playbook=PlaybookId.MINIMIZE_CHANGESET)

        msg = _make_feedback_msg(run_id=run_id, outcome="bad", score_delta=-5.0)
        await bus.publish(msg)

        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.MINIMIZE_CHANGESET
        )
        assert weight == WEIGHT_MIN, f"Expected clamped weight={WEIGHT_MIN}, got {weight}"

        agent.stop()


# ---------------------------------------------------------------------------
# Threshold boundary tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feedback_score_delta_exactly_at_positive_threshold():
    """score_delta exactly at FEEDBACK_SCORE_DELTA_POSITIVE_THRESHOLD → weight += 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus, agent_id="test-agent",
            run_store=run_store, strategy_store=strategy_store,
        )
        agent.start()

        run_id = "fb_test_boundary_pos"
        _setup_run(run_store, run_id)

        msg = _make_feedback_msg(
            run_id=run_id, outcome="good",
            score_delta=FEEDBACK_SCORE_DELTA_POSITIVE_THRESHOLD,
        )
        await bus.publish(msg)

        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST
        )
        assert weight == 1

        agent.stop()


@pytest.mark.asyncio
async def test_feedback_score_delta_exactly_at_negative_threshold():
    """score_delta exactly at FEEDBACK_SCORE_DELTA_NEGATIVE_THRESHOLD → weight -= 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus, agent_id="test-agent",
            run_store=run_store, strategy_store=strategy_store,
        )
        agent.start()

        run_id = "fb_test_boundary_neg"
        _setup_run(run_store, run_id, selected_playbook=PlaybookId.MINIMIZE_CHANGESET)

        msg = _make_feedback_msg(
            run_id=run_id, outcome="bad",
            score_delta=FEEDBACK_SCORE_DELTA_NEGATIVE_THRESHOLD,
        )
        await bus.publish(msg)

        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.MINIMIZE_CHANGESET
        )
        assert weight == -1

        agent.stop()


# ---------------------------------------------------------------------------
# Regression: existing _handle_evaluation_completed still works
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluation_completed_still_works_after_feedback_subscription():
    """Regression: meta.evaluation.completed subscription still functions."""
    from genus.meta import topics as meta_topics

    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        agent = StrategyLearningAgent(
            bus=bus, agent_id="test-agent",
            run_store=run_store, strategy_store=strategy_store,
        )
        agent.start()

        run_id = "fb_regression_001"
        journal = RunJournal(run_id, run_store)
        journal.initialize(goal="Regression test")

        journal.save_artifact(
            phase="strategy",
            artifact_type="strategy_decision",
            payload={
                "run_id": run_id,
                "phase": "fix",
                "iteration": 1,
                "selected_playbook": PlaybookId.TARGET_FAILING_TEST_FIRST,
                "candidates": [PlaybookId.TARGET_FAILING_TEST_FIRST],
                "reason": "test",
                "derived_from": {"failure_class": "test_failure"},
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        journal.save_artifact(
            phase="meta",
            artifact_type="evaluation",
            payload={
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
            },
        )

        msg = Message(
            topic=meta_topics.META_EVALUATION_COMPLETED,
            payload={"score": 85, "failure_class": "test_failure"},
            sender_id="test",
        )
        msg = attach_run_id(msg, run_id)
        await bus.publish(msg)

        weight = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST
        )
        assert weight == 1  # Evaluation boosted weight

        agent.stop()

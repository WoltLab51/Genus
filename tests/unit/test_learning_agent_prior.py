"""
Tests for StrategyLearningAgent prior-score history integration.

Covers _calculate_weight_change_with_prior and its influence on
_handle_evaluation_completed (strategy_learned events + strategy_update artifacts).
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

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
    WEIGHT_CHANGE_BOOST_STRONG,
    WEIGHT_CHANGE_PENALTY_STRONG,
    HISTORY_PRIOR_LIMIT,
)
from genus.strategy.models import PlaybookId
from genus.strategy.store_json import StrategyStoreJson


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(tmpdir: str):
    run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
    strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
    bus = MessageBus()
    agent = StrategyLearningAgent(
        bus=bus,
        agent_id="test-prior-agent",
        run_store=run_store,
        strategy_store=strategy_store,
    )
    return agent, run_store, strategy_store, bus


def _add_history_entries(strategy_store: StrategyStoreJson, failure_class: str,
                         playbook: str, scores):
    for i, score in enumerate(scores):
        strategy_store.add_learning_entry(
            run_id=f"prior_run_{i}",
            failure_class=failure_class,
            root_cause_hint=None,
            selected_playbook=playbook,
            outcome_score=score,
        )


def _make_run(run_id: str, run_store: JsonlRunStore, failure_class: str,
              playbook: str, score: int, final_status: str = "completed"):
    journal = RunJournal(run_id, run_store)
    journal.initialize(goal="Prior test")

    journal.save_artifact(
        phase="strategy",
        artifact_type="strategy_decision",
        payload={
            "run_id": run_id,
            "phase": "fix",
            "iteration": 1,
            "selected_playbook": playbook,
            "candidates": [playbook],
            "reason": "test",
            "derived_from": {"failure_class": failure_class},
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    journal.save_artifact(
        phase="meta",
        artifact_type="evaluation",
        payload={
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": score,
            "final_status": final_status,
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
# Unit tests: _calculate_weight_change_with_prior directly
# ---------------------------------------------------------------------------

def test_prior_high_and_current_high_returns_boost_strong():
    """Prior-Score hoch + aktueller Score hoch → weight_change = +2."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _, _, strategy_store, bus = _make_agent(tmpdir)
        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test",
            strategy_store=strategy_store,
        )

        # Add history with high scores for this playbook/failure_class
        failure_class = "test_failure"
        playbook = PlaybookId.TARGET_FAILING_TEST_FIRST
        _add_history_entries(strategy_store, failure_class, playbook,
                             [90, 85, 95])  # all >= WEIGHT_BOOST_THRESHOLD

        weight_change, prior_score, prior_count = agent._calculate_weight_change_with_prior(
            score=85,  # high current score
            failure_class=failure_class,
            selected_playbook=playbook,
        )

        assert weight_change == WEIGHT_CHANGE_BOOST_STRONG
        assert prior_score is not None
        assert prior_score >= WEIGHT_BOOST_THRESHOLD
        assert prior_count == 3


def test_prior_low_and_current_low_returns_penalty_strong():
    """Prior-Score niedrig + aktueller Score niedrig → weight_change = -2."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _, _, strategy_store, bus = _make_agent(tmpdir)
        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test",
            strategy_store=strategy_store,
        )

        failure_class = "test_failure"
        playbook = PlaybookId.MINIMIZE_CHANGESET
        _add_history_entries(strategy_store, failure_class, playbook,
                             [20, 30, 40])  # all <= WEIGHT_PENALTY_THRESHOLD

        weight_change, prior_score, prior_count = agent._calculate_weight_change_with_prior(
            score=35,  # low current score
            failure_class=failure_class,
            selected_playbook=playbook,
        )

        assert weight_change == WEIGHT_CHANGE_PENALTY_STRONG
        assert prior_score is not None
        assert prior_score <= WEIGHT_PENALTY_THRESHOLD
        assert prior_count == 3


def test_no_history_falls_back_to_normal_rule_boost():
    """Kein Eintrag in History → weight_change = normale Regel (+1)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _, _, strategy_store, bus = _make_agent(tmpdir)
        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test",
            strategy_store=strategy_store,
        )

        weight_change, prior_score, prior_count = agent._calculate_weight_change_with_prior(
            score=90,
            failure_class="test_failure",
            selected_playbook=PlaybookId.TARGET_FAILING_TEST_FIRST,
        )

        assert weight_change == WEIGHT_CHANGE_BOOST
        assert prior_score is None
        assert prior_count == 0


def test_no_history_falls_back_to_normal_rule_penalty():
    """Kein Eintrag in History → weight_change = normale Regel (-1)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _, _, strategy_store, bus = _make_agent(tmpdir)
        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test",
            strategy_store=strategy_store,
        )

        weight_change, prior_score, prior_count = agent._calculate_weight_change_with_prior(
            score=30,
            failure_class="test_failure",
            selected_playbook=PlaybookId.TARGET_FAILING_TEST_FIRST,
        )

        assert weight_change == WEIGHT_CHANGE_PENALTY
        assert prior_score is None
        assert prior_count == 0


def test_get_learning_history_exception_falls_back_to_normal_rule():
    """get_learning_history() wirft Exception → Fallback auf normale Regel, kein Crash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _, _, strategy_store, bus = _make_agent(tmpdir)
        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test",
            strategy_store=strategy_store,
        )

        # Patch get_learning_history to raise
        strategy_store.get_learning_history = MagicMock(
            side_effect=RuntimeError("simulated store error")
        )

        # Should not raise; must fall back gracefully
        weight_change, prior_score, prior_count = agent._calculate_weight_change_with_prior(
            score=90,
            failure_class="test_failure",
            selected_playbook=PlaybookId.TARGET_FAILING_TEST_FIRST,
        )

        assert weight_change == WEIGHT_CHANGE_BOOST
        assert prior_score is None
        assert prior_count == 0


def test_prior_high_but_current_low_no_mismatch_bonus():
    """Prior-Score hoch aber aktueller Score niedrig → weight_change = -1 (kein Mismatch-Bonus)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _, _, strategy_store, bus = _make_agent(tmpdir)
        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="test",
            strategy_store=strategy_store,
        )

        failure_class = "test_failure"
        playbook = PlaybookId.TARGET_FAILING_TEST_FIRST
        # High prior history
        _add_history_entries(strategy_store, failure_class, playbook,
                             [90, 85, 95])

        weight_change, prior_score, prior_count = agent._calculate_weight_change_with_prior(
            score=30,  # low current score — mismatch with high prior
            failure_class=failure_class,
            selected_playbook=playbook,
        )

        # No double bonus: prior high, current low → normal penalty
        assert weight_change == WEIGHT_CHANGE_PENALTY
        assert prior_score is not None
        assert prior_score >= WEIGHT_BOOST_THRESHOLD
        assert prior_count == 3


# ---------------------------------------------------------------------------
# Integration tests: prior fields appear in journal events and artifacts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prior_fields_logged_in_strategy_learned_event():
    """prior_score and prior_count appear in strategy_learned journal event."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent, run_store, strategy_store, bus = _make_agent(tmpdir)
        agent.start()

        failure_class = "test_failure"
        playbook = PlaybookId.TARGET_FAILING_TEST_FIRST

        # Seed history with high scores → should produce strong boost
        _add_history_entries(strategy_store, failure_class, playbook, [90, 85])

        run_id = "prior_integration_01"
        journal = _make_run(run_id, run_store, failure_class, playbook, score=90)

        msg = Message(
            topic=meta_topics.META_EVALUATION_COMPLETED,
            payload={"score": 90, "failure_class": failure_class},
            sender_id="test",
        )
        msg = attach_run_id(msg, run_id)
        await bus.publish(msg)

        events = journal.get_events(event_type="strategy_learned")
        assert len(events) == 1
        event_data = events[0].data
        assert "prior_score" in event_data
        assert "prior_count" in event_data
        assert event_data["prior_count"] == 2
        assert event_data["weight_change"] == WEIGHT_CHANGE_BOOST_STRONG

        agent.stop()


@pytest.mark.asyncio
async def test_prior_fields_logged_in_strategy_update_artifact():
    """prior_score and prior_count appear in strategy_update artifact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent, run_store, strategy_store, bus = _make_agent(tmpdir)
        agent.start()

        failure_class = "test_failure"
        playbook = PlaybookId.MINIMIZE_CHANGESET

        # Seed history with low scores → should produce strong penalty
        _add_history_entries(strategy_store, failure_class, playbook, [20, 30])

        run_id = "prior_integration_02"
        journal = _make_run(run_id, run_store, failure_class, playbook, score=20)

        msg = Message(
            topic=meta_topics.META_EVALUATION_COMPLETED,
            payload={"score": 20, "failure_class": failure_class},
            sender_id="test",
        )
        msg = attach_run_id(msg, run_id)
        await bus.publish(msg)

        artifacts = journal.get_artifacts(artifact_type="strategy_update")
        assert len(artifacts) == 1
        payload = artifacts[0].payload
        assert "prior_score" in payload
        assert "prior_count" in payload
        assert payload["prior_count"] == 2
        assert payload["weight_change"] == WEIGHT_CHANGE_PENALTY_STRONG

        agent.stop()

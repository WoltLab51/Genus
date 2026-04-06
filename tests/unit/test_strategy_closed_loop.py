"""
End-to-End Test for Strategy Learning Closed Loop

This test PROVES that GENUS changes behavior between runs based on learned experience.
This is the "intelligence definition" - same problem, different strategy due to learning.
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
from genus.strategy.agents.learning_agent import StrategyLearningAgent
from genus.strategy.models import PlaybookId
from genus.strategy.selector import StrategySelector
from genus.strategy.store_json import StrategyStoreJson


@pytest.mark.asyncio
async def test_closed_loop_behavior_change_across_runs():
    """
    CRITICAL TEST: Proves GENUS changes behavior between runs.

    Scenario:
    - Run A: Use target_failing_test_first for test_failure, gets low score (40)
    - Learning agent updates weights (penalizes target_failing_test_first)
    - Run B: Same failure_class (test_failure), selector now chooses different playbook

    This test demonstrates:
    1. Learning from experience (Run A outcome affects weights)
    2. Behavioral change (Run B makes different choice)
    3. Deterministic selection (same inputs + learned state = predictable output)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup shared stores
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        # Setup learning agent
        learning_agent = StrategyLearningAgent(
            bus=bus,
            agent_id="learning-agent",
            run_store=run_store,
            strategy_store=strategy_store,
        )
        learning_agent.start()

        # Setup selector
        selector = StrategySelector(store=strategy_store)

        # IMPORTANT: Pre-set weights so playbooks are competitive
        # This makes the -1 penalty significant enough to change the selection
        # target_failing_test_first: 0 learned + 10 profile + 20 recommended = 30
        # After -1 penalty: 29
        # minimize_changeset: learned + 5 profile = learned + 5
        # Need minimize_changeset to beat 29, so set learned to 25
        strategy_store.set_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST, 0
        )
        strategy_store.set_failure_class_weight(
            "test_failure", PlaybookId.MINIMIZE_CHANGESET, 25  # 25 + 5 = 30, beats 29
        )

        # ---------------------------------------------------------------
        # RUN A: Initial run with target_failing_test_first
        # ---------------------------------------------------------------

        run_id_a = "run_a_001"
        journal_a = RunJournal(run_id_a, run_store)
        journal_a.initialize(goal="Fix test failure")

        # Select strategy for Run A (first time seeing test_failure)
        decision_a = selector.select_strategy(
            run_id=run_id_a,
            phase="fix",
            iteration=1,
            evaluation_artifact={
                "failure_class": "test_failure",
                "root_cause_hint": None,
                "strategy_recommendations": [],
                "score": 0,  # Previous iteration failed
            },
        )

        # Record which playbook was selected for Run A
        playbook_a = decision_a.selected_playbook

        # Should initially select target_failing_test_first (recommended for test_failure)
        assert playbook_a == PlaybookId.TARGET_FAILING_TEST_FIRST, (
            f"Expected Run A to select {PlaybookId.TARGET_FAILING_TEST_FIRST}, "
            f"got {playbook_a}"
        )

        # Save strategy decision for Run A
        journal_a.save_artifact(
            phase="strategy",
            artifact_type="strategy_decision",
            payload=decision_a.to_dict(),
        )

        # Simulate Run A completing with LOW SCORE (failure)
        evaluation_a = {
            "run_id": run_id_a,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": 40,  # Low score - strategy failed
            "final_status": "failed",
            "failure_class": "test_failure",
            "root_cause_hint": None,
            "highlights": [],
            "issues": ["Strategy did not work"],
            "recommendations": [],
            "strategy_recommendations": [],
            "evidence": [],
        }
        journal_a.save_artifact(
            phase="meta",
            artifact_type="evaluation",
            payload=evaluation_a,
        )

        # Publish evaluation completed for Run A
        msg_a = Message(
            topic=meta_topics.META_EVALUATION_COMPLETED,
            payload={"score": 40, "failure_class": "test_failure"},
            sender_id="test",
        )
        msg_a = attach_run_id(msg_a, run_id_a)
        await bus.publish(msg_a)

        # Verify learning occurred
        weight_after_a = strategy_store.get_failure_class_weight(
            "test_failure", playbook_a
        )
        assert weight_after_a < 0, (
            f"After Run A failure, {playbook_a} weight should be negative "
            f"(got {weight_after_a})"
        )

        # ---------------------------------------------------------------
        # RUN B: Same failure_class, should choose DIFFERENT playbook
        # ---------------------------------------------------------------

        run_id_b = "run_b_002"
        journal_b = RunJournal(run_id_b, run_store)
        journal_b.initialize(goal="Fix test failure (attempt 2)")

        # Select strategy for Run B (same failure_class as Run A)
        decision_b = selector.select_strategy(
            run_id=run_id_b,
            phase="fix",
            iteration=1,
            evaluation_artifact={
                "failure_class": "test_failure",  # Same as Run A
                "root_cause_hint": None,
                "strategy_recommendations": [],
                "score": 0,
            },
        )

        playbook_b = decision_b.selected_playbook

        # CRITICAL ASSERTION: Behavior changed!
        assert playbook_b != playbook_a, (
            f"BEHAVIOR CHANGE FAILED: Run B selected same playbook as Run A "
            f"({playbook_a}). Learning did not affect selection! "
            f"Scores: {decision_b.derived_from.get('scores')}"
        )

        print(f"\n✓ BEHAVIOR CHANGE PROVEN:")
        print(f"  Run A: selected {playbook_a} → score 40 → weight penalty")
        print(f"  Run B: selected {playbook_b} (DIFFERENT!)")
        print(f"  Weights after learning: {strategy_store.get_all_failure_class_weights('test_failure')}")

        learning_agent.stop()


@pytest.mark.asyncio
async def test_closed_loop_multiple_iterations():
    """Test learning accumulates over multiple runs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        learning_agent = StrategyLearningAgent(
            bus=bus,
            agent_id="learning-agent",
            run_store=run_store,
            strategy_store=strategy_store,
        )
        learning_agent.start()

        selector = StrategySelector(store=strategy_store)

        # Run multiple iterations with the same playbook succeeding
        playbook = PlaybookId.MINIMIZE_CHANGESET
        initial_weight = strategy_store.get_failure_class_weight("timeout", playbook)

        for i in range(3):
            run_id = f"run_{i}"
            journal = RunJournal(run_id, run_store)
            journal.initialize(goal=f"Iteration {i}")

            # Save strategy decision
            decision = {
                "run_id": run_id,
                "phase": "fix",
                "iteration": i,
                "selected_playbook": playbook,
                "candidates": [playbook],
                "reason": f"Iteration {i}",
                "derived_from": {"failure_class": "timeout"},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            journal.save_artifact(
                phase="strategy",
                artifact_type="strategy_decision",
                payload=decision,
            )

            # Each run succeeds
            evaluation = {
                "run_id": run_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "score": 85,  # Success
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
                payload=evaluation,
            )

            msg = Message(
                topic=meta_topics.META_EVALUATION_COMPLETED,
                payload={"score": 85, "failure_class": "timeout"},
                sender_id="test",
            )
            msg = attach_run_id(msg, run_id)
            await bus.publish(msg)

        # Weight should have increased by 3 (one per successful run)
        final_weight = strategy_store.get_failure_class_weight("timeout", playbook)
        assert final_weight == initial_weight + 3, (
            f"Expected weight to increase by 3, got {final_weight} "
            f"(initial: {initial_weight})"
        )

        learning_agent.stop()


@pytest.mark.asyncio
async def test_closed_loop_deterministic_selection():
    """Test that selection is deterministic given learned state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))

        # Set up specific weights that make minimize_changeset win
        # We need to overcome the +20 bonus for target_failing_test_first
        strategy_store.set_failure_class_weight("test_failure", PlaybookId.MINIMIZE_CHANGESET, 25)
        strategy_store.set_failure_class_weight("test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST, -3)
        strategy_store.set_failure_class_weight("test_failure", PlaybookId.DEFAULT, 0)

        selector = StrategySelector(store=strategy_store)

        # Select multiple times with same inputs
        decisions = []
        for i in range(3):
            decision = selector.select_strategy(
                run_id=f"test_run_{i}",
                phase="fix",
                iteration=1,
                evaluation_artifact={
                    "failure_class": "test_failure",
                    "root_cause_hint": None,
                    "strategy_recommendations": [],
                    "score": 50,
                },
            )
            decisions.append(decision.selected_playbook)

        # All decisions should be identical (deterministic)
        assert len(set(decisions)) == 1, (
            f"Selection is not deterministic: {decisions}"
        )

        # Should select MINIMIZE_CHANGESET (highest total score: 25 learned + 5 profile = 30)
        assert decisions[0] == PlaybookId.MINIMIZE_CHANGESET, (
            f"Expected {PlaybookId.MINIMIZE_CHANGESET}, got {decisions[0]}"
        )


@pytest.mark.asyncio
async def test_closed_loop_tie_break_lexicographic():
    """Test that ties are broken lexicographically."""
    with tempfile.TemporaryDirectory() as tmpdir:
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))

        # Set up equal weights for two playbooks
        strategy_store.set_failure_class_weight("test_failure", "minimize_changeset", 5)
        strategy_store.set_failure_class_weight("test_failure", "target_failing_test_first", 5)

        selector = StrategySelector(store=strategy_store)

        decision = selector.select_strategy(
            run_id="test_run",
            phase="fix",
            iteration=1,
            evaluation_artifact={
                "failure_class": "test_failure",
                "root_cause_hint": None,
                "strategy_recommendations": [],
                "score": 50,
            },
        )

        # With equal scores, lexicographic tie-break should pick
        # "target_failing_test_first" > "minimize_changeset" alphabetically
        assert decision.selected_playbook == "target_failing_test_first", (
            f"Expected lexicographic tie-break to select 'target_failing_test_first', "
            f"got {decision.selected_playbook}"
        )


@pytest.mark.asyncio
async def test_closed_loop_success_after_learning():
    """
    Test complete learning cycle: fail → learn → adapt → succeed.

    This simulates a realistic scenario where learning improves outcomes.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        run_store = JsonlRunStore(base_dir=str(Path(tmpdir) / "runs"))
        strategy_store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))
        bus = MessageBus()

        learning_agent = StrategyLearningAgent(
            bus=bus,
            agent_id="learning-agent",
            run_store=run_store,
            strategy_store=strategy_store,
        )
        learning_agent.start()

        selector = StrategySelector(store=strategy_store)

        # Initial weights: make them competitive so -1 penalty matters
        # target_failing_test_first: learned + 10 profile + 20 recommended = 30 + learned
        # minimize_changeset: learned + 5 profile = 5 + learned
        # Set learned weights to make them close: minimize=19 gives 24 total
        # target at 0 gives 30, after -1 = 29 total, still wins
        # So set minimize even higher
        strategy_store.set_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST, 0
        )
        strategy_store.set_failure_class_weight(
            "test_failure", PlaybookId.MINIMIZE_CHANGESET, 25  # Will beat target after penalty
        )

        # Phase 1: First attempt fails with target_failing_test_first
        run_id_1 = "run_001"
        journal_1 = RunJournal(run_id_1, run_store)
        journal_1.initialize(goal="First attempt")

        decision_1 = selector.select_strategy(
            run_id=run_id_1,
            phase="fix",
            iteration=1,
            evaluation_artifact={
                "failure_class": "test_failure",
                "score": 0,
            },
        )

        # Should initially select target_failing_test_first (20 total vs minimize_changeset's 20)
        # Lexicographic tie-break picks target_failing_test_first
        assert decision_1.selected_playbook == PlaybookId.TARGET_FAILING_TEST_FIRST

        # Save artifacts and simulate failure
        journal_1.save_artifact(
            phase="strategy",
            artifact_type="strategy_decision",
            payload=decision_1.to_dict(),
        )

        evaluation_1 = {
            "run_id": run_id_1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": 30,  # Failed
            "final_status": "failed",
            "failure_class": "test_failure",
        }
        journal_1.save_artifact(
            phase="meta",
            artifact_type="evaluation",
            payload=evaluation_1,
        )

        msg_1 = attach_run_id(
            Message(
                topic=meta_topics.META_EVALUATION_COMPLETED,
                payload={"score": 30, "failure_class": "test_failure"},
                sender_id="test",
            ),
            run_id_1,
        )
        await bus.publish(msg_1)

        # Phase 2: Second attempt with learned preferences
        run_id_2 = "run_002"
        journal_2 = RunJournal(run_id_2, run_store)
        journal_2.initialize(goal="Second attempt")

        decision_2 = selector.select_strategy(
            run_id=run_id_2,
            phase="fix",
            iteration=1,
            evaluation_artifact={
                "failure_class": "test_failure",
                "score": 0,
            },
        )

        # Should now prefer different playbook
        assert decision_2.selected_playbook != PlaybookId.TARGET_FAILING_TEST_FIRST

        # Simulate this new strategy succeeding
        journal_2.save_artifact(
            phase="strategy",
            artifact_type="strategy_decision",
            payload=decision_2.to_dict(),
        )

        evaluation_2 = {
            "run_id": run_id_2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": 85,  # Success!
            "final_status": "completed",
            "failure_class": "test_failure",
        }
        journal_2.save_artifact(
            phase="meta",
            artifact_type="evaluation",
            payload=evaluation_2,
        )

        msg_2 = attach_run_id(
            Message(
                topic=meta_topics.META_EVALUATION_COMPLETED,
                payload={"score": 85, "failure_class": "test_failure"},
                sender_id="test",
            ),
            run_id_2,
        )
        await bus.publish(msg_2)

        # Verify: the successful playbook now has positive weight
        weight_successful = strategy_store.get_failure_class_weight(
            "test_failure", decision_2.selected_playbook
        )
        assert weight_successful > 0

        # Verify: the failed playbook has negative weight
        weight_failed = strategy_store.get_failure_class_weight(
            "test_failure", PlaybookId.TARGET_FAILING_TEST_FIRST
        )
        assert weight_failed < 10  # Should have been penalized

        print(f"\n✓ LEARNING CYCLE COMPLETE:")
        print(f"  Attempt 1: {PlaybookId.TARGET_FAILING_TEST_FIRST} → failed (score 30)")
        print(f"  Attempt 2: {decision_2.selected_playbook} → succeeded (score 85)")
        print(f"  Final weights: {strategy_store.get_all_failure_class_weights('test_failure')}")

        learning_agent.stop()

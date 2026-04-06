"""
Strategy Layer Usage Examples

This file demonstrates how to use the GENUS Strategy Layer for
meta-driven playbook selection with learning rules.
"""

from datetime import datetime, timezone

from genus.strategy import (
    PlaybookId,
    StrategySelector,
    StrategyStoreJson,
    apply_learning_rule,
    log_strategy_decision,
    get_last_strategy_decision,
)
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore


# ==============================================================================
# Example 1: Basic Strategy Selection
# ==============================================================================

def example_basic_selection():
    """Select a strategy with no prior context."""
    # Initialize store and selector
    store = StrategyStoreJson(base_dir="var/strategy")
    selector = StrategySelector(store=store, profile_name="default")

    # Select strategy for first iteration
    decision = selector.select_strategy(
        run_id="run_001",
        phase="implement",
        iteration=None,  # First iteration
        evaluation_artifact=None,  # No prior evaluation
    )

    print(f"Selected playbook: {decision.selected_playbook}")
    print(f"Reason: {decision.reason}")
    print(f"Candidates considered: {decision.candidates}")


# ==============================================================================
# Example 2: Strategy Selection Based on Test Failure
# ==============================================================================

def example_test_failure_selection():
    """Select a strategy after a test failure."""
    store = StrategyStoreJson(base_dir="var/strategy")
    selector = StrategySelector(store=store)

    # Simulate evaluation artifact from a failed test run
    evaluation_artifact = {
        "run_id": "run_001",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "score": 30,
        "final_status": "failed",
        "failure_class": "test_failure",
        "root_cause_hint": "assertion_error",
        "strategy_recommendations": [
            PlaybookId.TARGET_FAILING_TEST_FIRST
        ],
    }

    # Select strategy for fix iteration
    decision = selector.select_strategy(
        run_id="run_001",
        phase="fix",
        iteration=1,
        evaluation_artifact=evaluation_artifact,
    )

    print(f"Selected playbook: {decision.selected_playbook}")
    print(f"Reason: {decision.reason}")
    # Expected: TARGET_FAILING_TEST_FIRST


# ==============================================================================
# Example 3: Strategy Selection with Learning
# ==============================================================================

def example_learning():
    """Demonstrate learning from past runs."""
    store = StrategyStoreJson(base_dir="var/strategy")
    selector = StrategySelector(store=store)

    # Simulate a successful run with TARGET_FAILING_TEST_FIRST
    decision_1 = selector.select_strategy(
        run_id="run_001",
        phase="fix",
        iteration=1,
        evaluation_artifact={
            "failure_class": "test_failure",
            "root_cause_hint": "assertion_error",
            "score": 40,
        },
    )

    # Apply learning: this run succeeded
    apply_learning_rule(
        store=store,
        decision=decision_1,
        outcome_score=85,  # Success!
        failure_class="test_failure",
        root_cause_hint="assertion_error",
    )

    # Next time we encounter test_failure, the successful playbook
    # will get a learning bonus
    decision_2 = selector.select_strategy(
        run_id="run_002",
        phase="fix",
        iteration=1,
        evaluation_artifact={
            "failure_class": "test_failure",
            "root_cause_hint": "assertion_error",
            "score": 35,
        },
    )

    print(f"First decision: {decision_1.selected_playbook}")
    print(f"Second decision (with learning): {decision_2.selected_playbook}")


# ==============================================================================
# Example 4: Integration with RunJournal
# ==============================================================================

def example_journal_integration():
    """Log strategy decisions to RunJournal."""
    # Initialize stores
    run_store = JsonlRunStore(base_dir="var/runs")
    strategy_store = StrategyStoreJson(base_dir="var/strategy")

    # Create journal for this run
    run_id = "run_001"
    journal = RunJournal(run_id=run_id, store=run_store)
    journal.initialize(goal="Fix failing tests")

    # Select strategy
    selector = StrategySelector(store=strategy_store)
    decision = selector.select_strategy(
        run_id=run_id,
        phase="fix",
        iteration=1,
        evaluation_artifact={
            "failure_class": "test_failure",
            "score": 40,
        },
    )

    # Log to journal
    log_strategy_decision(journal, decision, phase_id="fix_001")

    # Later, retrieve the decision
    last_decision = get_last_strategy_decision(journal, phase="fix")
    print(f"Last strategy decision: {last_decision.selected_playbook}")


# ==============================================================================
# Example 5: Timeout Handling
# ==============================================================================

def example_timeout():
    """Handle timeout failures with INCREASE_TIMEOUT_ONCE."""
    store = StrategyStoreJson(base_dir="var/strategy")
    selector = StrategySelector(store=store)

    # First timeout
    evaluation_artifact = {
        "failure_class": "timeout",
        "score": 0,
        "strategy_recommendations": [PlaybookId.INCREASE_TIMEOUT_ONCE],
    }

    decision = selector.select_strategy(
        run_id="run_timeout_001",
        phase="fix",
        iteration=1,
        evaluation_artifact=evaluation_artifact,
    )

    print(f"Timeout decision: {decision.selected_playbook}")
    # Expected: INCREASE_TIMEOUT_ONCE

    # If timeout happens again after increasing, we learn it doesn't work
    apply_learning_rule(
        store=store,
        decision=decision,
        outcome_score=0,  # Failed again
        failure_class="timeout",
    )

    # Next timeout will be less likely to choose INCREASE_TIMEOUT_ONCE
    # (it got penalized)


# ==============================================================================
# Example 6: Custom Strategy Profile
# ==============================================================================

def example_custom_profile():
    """Create and use a custom strategy profile."""
    from genus.strategy.models import StrategyProfile

    store = StrategyStoreJson(base_dir="var/strategy")

    # Create a conservative profile that avoids risky changes
    conservative_profile = StrategyProfile(
        name="conservative",
        playbook_weights={
            PlaybookId.MINIMIZE_CHANGESET: 20,  # Highly preferred
            PlaybookId.TARGET_FAILING_TEST_FIRST: 5,
            PlaybookId.INCREASE_TIMEOUT_ONCE: -5,  # Avoid
            PlaybookId.DEFAULT: 0,
            PlaybookId.ASK_OPERATOR_WITH_CONTEXT: 10,  # Prefer human input
        }
    )

    # Save the profile
    store.save_profile(conservative_profile)

    # Use the conservative profile
    selector = StrategySelector(store=store, profile_name="conservative")

    decision = selector.select_strategy(
        run_id="run_conservative",
        phase="implement",
        iteration=None,
    )

    print(f"Conservative profile selected: {decision.selected_playbook}")
    # More likely to choose MINIMIZE_CHANGESET or ASK_OPERATOR_WITH_CONTEXT


# ==============================================================================
# Example 7: Full DevLoop Integration Pattern
# ==============================================================================

def example_full_devloop_pattern():
    """
    Full pattern for integrating strategy layer with DevLoop.

    This shows how the strategy layer would be used in a complete
    implementation workflow.
    """
    # Setup
    run_id = "run_devloop_001"
    run_store = JsonlRunStore(base_dir="var/runs")
    strategy_store = StrategyStoreJson(base_dir="var/strategy")
    journal = RunJournal(run_id=run_id, store=run_store)
    selector = StrategySelector(store=strategy_store)

    # Initialize run
    journal.initialize(goal="Implement feature X")

    # PHASE 1: Initial implementation
    decision_impl = selector.select_strategy(
        run_id=run_id,
        phase="implement",
        iteration=None,
    )
    log_strategy_decision(journal, decision_impl, phase_id="impl_001")

    # ... implement code based on selected strategy ...
    # ... run tests ...

    # Save test results (simulated)
    test_artifact = {
        "phase": "test",
        "artifact_type": "test_report",
        "payload": {
            "tests_run": 10,
            "tests_passed": 7,
            "tests_failed": 3,
        },
    }

    # Save evaluation artifact (simulated)
    evaluation_artifact = {
        "score": 40,
        "final_status": "failed",
        "failure_class": "test_failure",
        "root_cause_hint": "assertion_error",
        "strategy_recommendations": [PlaybookId.TARGET_FAILING_TEST_FIRST],
    }

    # PHASE 2: Fix iteration
    decision_fix = selector.select_strategy(
        run_id=run_id,
        phase="fix",
        iteration=1,
        evaluation_artifact=evaluation_artifact,
    )
    log_strategy_decision(journal, decision_fix, phase_id="fix_001")

    # ... fix code based on selected strategy ...
    # ... run tests again ...

    # Success!
    final_evaluation = {
        "score": 85,
        "final_status": "completed",
    }

    # Apply learning
    apply_learning_rule(
        store=strategy_store,
        decision=decision_fix,
        outcome_score=85,
        failure_class="test_failure",
        root_cause_hint="assertion_error",
    )

    print("DevLoop completed with learning applied")


# ==============================================================================
# Run Examples
# ==============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Example 1: Basic Selection")
    print("=" * 70)
    example_basic_selection()

    print("\n" + "=" * 70)
    print("Example 2: Test Failure Selection")
    print("=" * 70)
    example_test_failure_selection()

    print("\n" + "=" * 70)
    print("Example 3: Learning")
    print("=" * 70)
    example_learning()

    print("\n" + "=" * 70)
    print("Example 6: Custom Profile")
    print("=" * 70)
    example_custom_profile()

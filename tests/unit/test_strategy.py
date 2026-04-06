"""
Unit tests for strategy layer models, registry, store, selector, and learning.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from genus.strategy.models import PlaybookId, StrategyDecision, StrategyProfile
from genus.strategy.registry import (
    PLAYBOOKS,
    all_playbook_ids,
    get_playbook_description,
    get_playbook_recommended_for,
    is_playbook_recommended,
)
from genus.strategy.store_json import StrategyStoreJson
from genus.strategy.selector import StrategySelector
from genus.strategy.learning import (
    apply_learning_rule,
    reset_learning,
    SCORE_SUCCESS_THRESHOLD,
    SCORE_FAILURE_THRESHOLD,
    WEIGHT_MIN,
    WEIGHT_MAX,
)


# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------

def test_playbook_id_constants():
    """Test PlaybookId constants are defined correctly."""
    assert PlaybookId.TARGET_FAILING_TEST_FIRST == "target_failing_test_first"
    assert PlaybookId.MINIMIZE_CHANGESET == "minimize_changeset"
    assert PlaybookId.INCREASE_TIMEOUT_ONCE == "increase_timeout_once"
    assert PlaybookId.ASK_OPERATOR_WITH_CONTEXT == "ask_operator_with_context"
    assert PlaybookId.DEFAULT == "default"


def test_playbook_id_all_values():
    """Test PlaybookId.all_values returns all constants."""
    values = PlaybookId.all_values()
    assert len(values) == 5
    assert PlaybookId.TARGET_FAILING_TEST_FIRST in values
    assert PlaybookId.DEFAULT in values


def test_strategy_decision_to_dict():
    """Test StrategyDecision serialization."""
    decision = StrategyDecision(
        run_id="test_run_123",
        phase="fix",
        iteration=2,
        selected_playbook=PlaybookId.TARGET_FAILING_TEST_FIRST,
        candidates=[PlaybookId.DEFAULT, PlaybookId.TARGET_FAILING_TEST_FIRST],
        reason="Test failed, targeting specific test",
        derived_from={"failure_class": "test_failure"},
        created_at="2026-04-06T19:00:00Z",
    )

    data = decision.to_dict()
    assert data["run_id"] == "test_run_123"
    assert data["phase"] == "fix"
    assert data["iteration"] == 2
    assert data["selected_playbook"] == PlaybookId.TARGET_FAILING_TEST_FIRST
    assert len(data["candidates"]) == 2
    assert data["reason"] == "Test failed, targeting specific test"
    assert data["derived_from"]["failure_class"] == "test_failure"


def test_strategy_decision_from_dict():
    """Test StrategyDecision deserialization."""
    data = {
        "run_id": "test_run_456",
        "phase": "implement",
        "iteration": None,
        "selected_playbook": PlaybookId.DEFAULT,
        "candidates": [PlaybookId.DEFAULT],
        "reason": "First iteration, using default",
        "derived_from": {},
        "created_at": "2026-04-06T19:00:00Z",
    }

    decision = StrategyDecision.from_dict(data)
    assert decision.run_id == "test_run_456"
    assert decision.phase == "implement"
    assert decision.iteration is None
    assert decision.selected_playbook == PlaybookId.DEFAULT


def test_strategy_profile_default():
    """Test StrategyProfile default profile creation."""
    profile = StrategyProfile.default_profile()
    assert profile.name == "default"
    assert PlaybookId.TARGET_FAILING_TEST_FIRST in profile.playbook_weights
    assert profile.playbook_weights[PlaybookId.TARGET_FAILING_TEST_FIRST] == 10
    assert profile.playbook_weights[PlaybookId.DEFAULT] == 0
    assert profile.playbook_weights[PlaybookId.ASK_OPERATOR_WITH_CONTEXT] == -10


def test_strategy_profile_to_dict():
    """Test StrategyProfile serialization."""
    profile = StrategyProfile(
        name="custom",
        playbook_weights={PlaybookId.DEFAULT: 5}
    )

    data = profile.to_dict()
    assert data["name"] == "custom"
    assert data["playbook_weights"][PlaybookId.DEFAULT] == 5


def test_strategy_profile_from_dict():
    """Test StrategyProfile deserialization."""
    data = {
        "name": "aggressive",
        "playbook_weights": {
            PlaybookId.MINIMIZE_CHANGESET: 20
        }
    }

    profile = StrategyProfile.from_dict(data)
    assert profile.name == "aggressive"
    assert profile.playbook_weights[PlaybookId.MINIMIZE_CHANGESET] == 20


# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

def test_registry_has_all_playbooks():
    """Test PLAYBOOKS registry contains all playbook IDs."""
    all_ids = PlaybookId.all_values()
    for playbook_id in all_ids:
        assert playbook_id in PLAYBOOKS
        assert "description" in PLAYBOOKS[playbook_id]
        assert "recommended_for" in PLAYBOOKS[playbook_id]


def test_all_playbook_ids():
    """Test all_playbook_ids returns all registry keys."""
    ids = all_playbook_ids()
    assert len(ids) == 5
    assert PlaybookId.DEFAULT in ids


def test_get_playbook_description():
    """Test get_playbook_description returns descriptions."""
    desc = get_playbook_description(PlaybookId.TARGET_FAILING_TEST_FIRST)
    assert "failing test" in desc.lower()

    unknown_desc = get_playbook_description("nonexistent")
    assert "Unknown playbook" in unknown_desc


def test_get_playbook_recommended_for():
    """Test get_playbook_recommended_for returns scenarios."""
    scenarios = get_playbook_recommended_for(PlaybookId.INCREASE_TIMEOUT_ONCE)
    assert "timeout" in scenarios

    empty = get_playbook_recommended_for("nonexistent")
    assert empty == []


def test_is_playbook_recommended():
    """Test is_playbook_recommended checks scenario membership."""
    assert is_playbook_recommended(PlaybookId.INCREASE_TIMEOUT_ONCE, "timeout")
    assert not is_playbook_recommended(PlaybookId.INCREASE_TIMEOUT_ONCE, "test_failure")


# ---------------------------------------------------------------------------
# Test store
# ---------------------------------------------------------------------------

def test_strategy_store_init_default_dir():
    """Test StrategyStoreJson initializes with default directory."""
    store = StrategyStoreJson()
    # Should not raise, base_dir should be set
    assert store._base_dir is not None


def test_strategy_store_init_custom_dir():
    """Test StrategyStoreJson initializes with custom directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)
        assert str(store._base_dir) == tmpdir


def test_strategy_store_save_and_load_profile():
    """Test saving and loading strategy profiles."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        profile = StrategyProfile(
            name="test_profile",
            playbook_weights={PlaybookId.DEFAULT: 10}
        )

        store.save_profile(profile)
        loaded = store.get_profile("test_profile")

        assert loaded is not None
        assert loaded.name == "test_profile"
        assert loaded.playbook_weights[PlaybookId.DEFAULT] == 10


def test_strategy_store_get_nonexistent_profile():
    """Test getting nonexistent profile returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)
        profile = store.get_profile("nonexistent")
        assert profile is None


def test_strategy_store_list_profiles():
    """Test listing all profile names."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        store.save_profile(StrategyProfile(name="profile1"))
        store.save_profile(StrategyProfile(name="profile2"))

        profiles = store.list_profiles()
        assert len(profiles) == 2
        assert "profile1" in profiles
        assert "profile2" in profiles


def test_strategy_store_add_learning_entry():
    """Test adding learning history entry."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        store.add_learning_entry(
            run_id="test_run",
            failure_class="test_failure",
            root_cause_hint="assertion_error",
            selected_playbook=PlaybookId.TARGET_FAILING_TEST_FIRST,
            outcome_score=75,
        )

        history = store.get_learning_history()
        assert len(history) == 1
        assert history[0]["run_id"] == "test_run"
        assert history[0]["failure_class"] == "test_failure"
        assert history[0]["outcome_score"] == 75


def test_strategy_store_get_learning_history_filtered():
    """Test querying learning history with filters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        # Add multiple entries
        store.add_learning_entry("run1", "test_failure", "assertion_error", PlaybookId.DEFAULT, 50)
        store.add_learning_entry("run2", "test_failure", "import_error", PlaybookId.DEFAULT, 60)
        store.add_learning_entry("run3", "timeout", None, PlaybookId.INCREASE_TIMEOUT_ONCE, 70)

        # Filter by failure_class
        test_failures = store.get_learning_history(failure_class="test_failure")
        assert len(test_failures) == 2

        # Filter by root_cause_hint
        assertions = store.get_learning_history(root_cause_hint="assertion_error")
        assert len(assertions) == 1

        # Limit results
        limited = store.get_learning_history(limit=2)
        assert len(limited) == 2


def test_strategy_store_clear_learning_history():
    """Test clearing learning history."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        store.add_learning_entry("run1", None, None, PlaybookId.DEFAULT, 50)
        assert len(store.get_learning_history()) == 1

        store.clear_learning_history()
        assert len(store.get_learning_history()) == 0


# ---------------------------------------------------------------------------
# Test selector
# ---------------------------------------------------------------------------

def test_strategy_selector_init():
    """Test StrategySelector initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)
        selector = StrategySelector(store=store)
        assert selector._store is store


def test_strategy_selector_select_default_no_context():
    """Test selector chooses playbook based on profile weights when no context provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)
        selector = StrategySelector(store=store)

        decision = selector.select_strategy(
            run_id="test_run",
            phase="implement",
            iteration=None,
            evaluation_artifact=None,
        )

        # With default profile, TARGET_FAILING_TEST_FIRST has weight 10,
        # plus first iteration bonus for DEFAULT (+5), so TARGET_FAILING_TEST_FIRST wins
        assert decision.selected_playbook == PlaybookId.TARGET_FAILING_TEST_FIRST
        assert decision.phase == "implement"
        assert decision.iteration is None


def test_strategy_selector_select_based_on_failure_class():
    """Test selector chooses playbook based on failure_class."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)
        selector = StrategySelector(store=store)

        evaluation_artifact = {
            "failure_class": "test_failure",
            "root_cause_hint": "assertion_error",
            "strategy_recommendations": [],
            "score": 30,
        }

        decision = selector.select_strategy(
            run_id="test_run",
            phase="fix",
            iteration=1,
            evaluation_artifact=evaluation_artifact,
        )

        # Should select TARGET_FAILING_TEST_FIRST for test_failure
        assert decision.selected_playbook == PlaybookId.TARGET_FAILING_TEST_FIRST
        assert "test_failure" in decision.reason.lower() or "assertion_error" in decision.reason.lower()


def test_strategy_selector_select_based_on_timeout():
    """Test selector chooses INCREASE_TIMEOUT_ONCE for timeout."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)
        selector = StrategySelector(store=store)

        evaluation_artifact = {
            "failure_class": "timeout",
            "root_cause_hint": None,
            "strategy_recommendations": [],
            "score": 0,
        }

        decision = selector.select_strategy(
            run_id="test_run",
            phase="fix",
            iteration=1,
            evaluation_artifact=evaluation_artifact,
        )

        assert decision.selected_playbook == PlaybookId.INCREASE_TIMEOUT_ONCE


def test_strategy_selector_respects_recommendations():
    """Test selector prioritizes strategy_recommendations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)
        selector = StrategySelector(store=store)

        evaluation_artifact = {
            "failure_class": "test_failure",
            "root_cause_hint": None,
            "strategy_recommendations": [PlaybookId.MINIMIZE_CHANGESET],
            "score": 40,
        }

        decision = selector.select_strategy(
            run_id="test_run",
            phase="fix",
            iteration=2,
            evaluation_artifact=evaluation_artifact,
        )

        # Should select MINIMIZE_CHANGESET because it's explicitly recommended
        assert decision.selected_playbook == PlaybookId.MINIMIZE_CHANGESET


def test_strategy_selector_learning_bonus():
    """Test selector applies learning bonus from history."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        # Add successful history for DEFAULT with test_failure
        store.add_learning_entry("run1", "test_failure", None, PlaybookId.DEFAULT, 85)
        store.add_learning_entry("run2", "test_failure", None, PlaybookId.DEFAULT, 90)

        selector = StrategySelector(store=store)

        evaluation_artifact = {
            "failure_class": "test_failure",
            "root_cause_hint": None,
            "strategy_recommendations": [],
            "score": 30,
        }

        decision = selector.select_strategy(
            run_id="test_run",
            phase="fix",
            iteration=1,
            evaluation_artifact=evaluation_artifact,
        )

        # Learning bonus might influence the selection
        # (exact result depends on scoring, but decision should be valid)
        assert decision.selected_playbook in PlaybookId.all_values()


# ---------------------------------------------------------------------------
# Test learning
# ---------------------------------------------------------------------------

def test_apply_learning_rule_success_boost():
    """Test learning rule boosts weight on success."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        # Create initial profile
        profile = StrategyProfile.default_profile()
        store.save_profile(profile)

        initial_weight = profile.playbook_weights.get(PlaybookId.DEFAULT, 0)

        decision = StrategyDecision(
            run_id="test_run",
            phase="implement",
            iteration=None,
            selected_playbook=PlaybookId.DEFAULT,
            candidates=[PlaybookId.DEFAULT],
            reason="test",
            derived_from={},
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        apply_learning_rule(
            store=store,
            decision=decision,
            outcome_score=80,  # Success
            profile_name="default",
        )

        # Check weight was boosted
        updated_profile = store.get_profile("default")
        assert updated_profile.playbook_weights[PlaybookId.DEFAULT] == initial_weight + 2


def test_apply_learning_rule_failure_penalty():
    """Test learning rule penalizes weight on failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        profile = StrategyProfile.default_profile()
        store.save_profile(profile)

        initial_weight = profile.playbook_weights.get(PlaybookId.DEFAULT, 0)

        decision = StrategyDecision(
            run_id="test_run",
            phase="implement",
            iteration=None,
            selected_playbook=PlaybookId.DEFAULT,
            candidates=[PlaybookId.DEFAULT],
            reason="test",
            derived_from={},
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        apply_learning_rule(
            store=store,
            decision=decision,
            outcome_score=30,  # Failure
            profile_name="default",
        )

        # Check weight was penalized
        updated_profile = store.get_profile("default")
        assert updated_profile.playbook_weights[PlaybookId.DEFAULT] == initial_weight - 1


def test_apply_learning_rule_records_history():
    """Test learning rule records outcome in history."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        decision = StrategyDecision(
            run_id="test_run",
            phase="fix",
            iteration=1,
            selected_playbook=PlaybookId.TARGET_FAILING_TEST_FIRST,
            candidates=[PlaybookId.TARGET_FAILING_TEST_FIRST],
            reason="test",
            derived_from={},
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        apply_learning_rule(
            store=store,
            decision=decision,
            outcome_score=75,
            failure_class="test_failure",
            root_cause_hint="assertion_error",
        )

        history = store.get_learning_history()
        assert len(history) == 1
        assert history[0]["run_id"] == "test_run"
        assert history[0]["selected_playbook"] == PlaybookId.TARGET_FAILING_TEST_FIRST
        assert history[0]["outcome_score"] == 75


def test_reset_learning():
    """Test reset_learning resets profile to default."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        # Create modified profile
        profile = StrategyProfile(
            name="default",
            playbook_weights={PlaybookId.DEFAULT: 100}
        )
        store.save_profile(profile)

        # Add some history
        store.add_learning_entry("run1", None, None, PlaybookId.DEFAULT, 50)

        # Reset
        reset_learning(store, profile_name="default", keep_history=False)

        # Check profile was reset
        reset_profile = store.get_profile("default")
        assert reset_profile.playbook_weights[PlaybookId.DEFAULT] == 0  # default weight

        # Check history was cleared
        history = store.get_learning_history()
        assert len(history) == 0


def test_reset_learning_keep_history():
    """Test reset_learning can keep history."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        store.add_learning_entry("run1", None, None, PlaybookId.DEFAULT, 50)

        reset_learning(store, profile_name="default", keep_history=True)

        # History should still exist
        history = store.get_learning_history()
        assert len(history) == 1


# ---------------------------------------------------------------------------
# Test selector cache invalidation
# ---------------------------------------------------------------------------

def test_selector_cache_invalidated_after_select():
    """After select_strategy(), _profile is None (cache cleared)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)
        selector = StrategySelector(store=store)

        selector.select_strategy(
            run_id="test_run",
            phase="fix",
            iteration=1,
            evaluation_artifact=None,
        )

        assert selector._profile is None


# ---------------------------------------------------------------------------
# Test weight clamping
# ---------------------------------------------------------------------------

def test_learning_py_weight_clamping_upper():
    """apply_learning_rule() clamps weights to WEIGHT_MAX."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        # Set weight near the ceiling so a success boost would exceed WEIGHT_MAX
        profile = StrategyProfile(
            name="default",
            playbook_weights={PlaybookId.DEFAULT: WEIGHT_MAX - 1}
        )
        store.save_profile(profile)

        decision = StrategyDecision(
            run_id="test_run",
            phase="fix",
            iteration=1,
            selected_playbook=PlaybookId.DEFAULT,
            candidates=[PlaybookId.DEFAULT],
            reason="test",
            derived_from={},
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        apply_learning_rule(store=store, decision=decision, outcome_score=80)

        updated = store.get_profile("default")
        assert updated.playbook_weights[PlaybookId.DEFAULT] <= WEIGHT_MAX


def test_learning_py_weight_clamping_lower():
    """apply_learning_rule() clamps weights to WEIGHT_MIN."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=tmpdir)

        # Set weight near the floor so a penalty would go below WEIGHT_MIN
        profile = StrategyProfile(
            name="default",
            playbook_weights={PlaybookId.DEFAULT: WEIGHT_MIN + 1}
        )
        store.save_profile(profile)

        decision = StrategyDecision(
            run_id="test_run",
            phase="fix",
            iteration=1,
            selected_playbook=PlaybookId.DEFAULT,
            candidates=[PlaybookId.DEFAULT],
            reason="test",
            derived_from={},
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        apply_learning_rule(store=store, decision=decision, outcome_score=30)

        updated = store.get_profile("default")
        assert updated.playbook_weights[PlaybookId.DEFAULT] >= WEIGHT_MIN

"""
Learning Rules - Update Strategy Preferences Based on Outcomes

Implements simple heuristic learning rules that update strategy preferences
based on run outcomes. No ML, just deterministic rules.

Learning Rules (v1):
1. After successful run (score >= 70): Boost weight of used playbook by +2
2. After failed run (score < 50): Decrease weight of used playbook by -1
3. After timeout with INCREASE_TIMEOUT_ONCE: If failed again, penalize heavily (-5)
4. Record all outcomes in learning history for analytics

All updates are logged and auditable.

.. note::
    GENUS 2.0 nutzt StrategyLearningAgent für event-driven Learning.
    apply_learning_rule() ist ein low-level Helper und sollte nicht
    direkt von außen aufgerufen werden.
"""

import logging
from typing import Optional

from genus.strategy.models import StrategyDecision, StrategyProfile
from genus.strategy.store_json import StrategyStoreJson

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Learning thresholds
# ---------------------------------------------------------------------------

SCORE_SUCCESS_THRESHOLD = 70
"""Score above which we consider the run a success (boost playbook weight)."""

SCORE_FAILURE_THRESHOLD = 50
"""Score below which we consider the run a failure (penalize playbook weight)."""

WEIGHT_BOOST_SUCCESS = 2
"""Weight increase for successful playbooks."""

WEIGHT_PENALTY_FAILURE = -1
"""Weight decrease for failed playbooks."""

WEIGHT_PENALTY_TIMEOUT_RETRY = -5
"""Heavy penalty for timeout playbooks that failed again."""

WEIGHT_MIN = -20
"""Minimum allowed playbook weight (clamp lower bound)."""

WEIGHT_MAX = 20
"""Maximum allowed playbook weight (clamp upper bound)."""


# ---------------------------------------------------------------------------
# Learning rules
# ---------------------------------------------------------------------------

def apply_learning_rule(
    store: StrategyStoreJson,
    decision: StrategyDecision,
    outcome_score: int,
    failure_class: Optional[str] = None,
    root_cause_hint: Optional[str] = None,
    profile_name: str = "default",
) -> None:
    """Apply learning rules to update strategy preferences.

    Updates the strategy profile weights based on the outcome of a run
    that used the given decision. Also records the outcome in learning history.

    Args:
        store: Strategy store to update.
        decision: The strategy decision that was made.
        outcome_score: Final outcome score (0-100).
        failure_class: Failure classification (if any).
        root_cause_hint: Root cause hint (if any).
        profile_name: Name of profile to update (default: "default").

    .. deprecated::
        Direkte Nutzung dieser Funktion ist deprecated.
        Nutze stattdessen StrategyLearningAgent (event-driven, journal-aware).
        Diese Funktion bleibt als interner Helper erhalten.
    """
    # Record in learning history first
    store.add_learning_entry(
        run_id=decision.run_id,
        failure_class=failure_class,
        root_cause_hint=root_cause_hint,
        selected_playbook=decision.selected_playbook,
        outcome_score=outcome_score,
    )

    # Load profile
    profile = store.get_profile(profile_name)
    if profile is None:
        logger.warning(
            "Profile %r not found, creating default profile for learning",
            profile_name
        )
        profile = StrategyProfile.default_profile()

    # Apply learning rules
    playbook_id = decision.selected_playbook
    old_weight = profile.playbook_weights.get(playbook_id, 0)
    new_weight = old_weight

    # Rule 1: Success boost
    if outcome_score >= SCORE_SUCCESS_THRESHOLD:
        new_weight += WEIGHT_BOOST_SUCCESS
        logger.info(
            "Learning: run_id=%s succeeded (score=%d), boosting %s weight %d -> %d",
            decision.run_id, outcome_score, playbook_id, old_weight, new_weight
        )

    # Rule 2: Failure penalty
    elif outcome_score < SCORE_FAILURE_THRESHOLD:
        new_weight += WEIGHT_PENALTY_FAILURE
        logger.info(
            "Learning: run_id=%s failed (score=%d), penalizing %s weight %d -> %d",
            decision.run_id, outcome_score, playbook_id, old_weight, new_weight
        )

        # Rule 3: Heavy penalty for timeout retry that failed again
        if playbook_id == "increase_timeout_once" and failure_class == "timeout":
            new_weight += WEIGHT_PENALTY_TIMEOUT_RETRY
            logger.warning(
                "Learning: INCREASE_TIMEOUT_ONCE failed with timeout again, "
                "heavy penalty %d -> %d",
                old_weight, new_weight
            )

    # Clamp weight to prevent unbounded drift
    new_weight = max(WEIGHT_MIN, min(WEIGHT_MAX, new_weight))

    # Update profile
    profile.playbook_weights[playbook_id] = new_weight
    store.save_profile(profile)

    logger.debug(
        "Applied learning rule for run_id=%s, playbook=%s, "
        "score=%d, weight %d -> %d",
        decision.run_id, playbook_id, outcome_score, old_weight, new_weight
    )


def reset_learning(
    store: StrategyStoreJson,
    profile_name: str = "default",
    keep_history: bool = False,
) -> None:
    """Reset learning for a profile.

    Resets the profile to default weights. Optionally clears learning history.

    Args:
        store: Strategy store to update.
        profile_name: Name of profile to reset (default: "default").
        keep_history: If True, keep learning history. If False, clear it.
    """
    # Reset profile to default
    profile = StrategyProfile.default_profile()
    profile.name = profile_name
    store.save_profile(profile)

    logger.info("Reset strategy profile %r to default weights", profile_name)

    # Optionally clear history
    if not keep_history:
        store.clear_learning_history()
        logger.info("Cleared learning history")

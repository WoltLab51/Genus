"""
Strategy Selector - Deterministic Strategy Selection

Selects the next playbook based on:
1. Last EvaluationArtifact (failure_class, root_cause_hint, strategy_recommendations)
2. Learning Store (historical preferences)
3. Strategy Profile (configured weights)

All decisions are fully deterministic and explainable.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from genus.strategy.models import PlaybookId, StrategyDecision, StrategyProfile
from genus.strategy.registry import PLAYBOOKS, all_playbook_ids
from genus.strategy.store_json import StrategyStoreJson

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# StrategySelector
# ---------------------------------------------------------------------------

class StrategySelector:
    """Deterministic strategy selector.

    Selects playbooks based on evaluation artifacts, learning history,
    and configured profiles. All decisions are logged and explainable.

    Args:
        store: Strategy store for persistence (optional, creates default if None).
        profile_name: Name of profile to use (default: "default").
    """

    def __init__(
        self,
        store: Optional[StrategyStoreJson] = None,
        profile_name: str = "default",
    ) -> None:
        self._store = store or StrategyStoreJson()
        self._profile_name = profile_name
        self._profile: Optional[StrategyProfile] = None

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def _load_profile(self) -> StrategyProfile:
        """Load the configured profile, or create default if not found."""
        if self._profile is not None:
            return self._profile

        profile = self._store.get_profile(self._profile_name)
        if profile is None:
            logger.info(
                "Profile %r not found, creating default profile",
                self._profile_name
            )
            profile = StrategyProfile.default_profile()
            self._store.save_profile(profile)

        self._profile = profile
        return profile

    # ------------------------------------------------------------------
    # Strategy selection
    # ------------------------------------------------------------------

    def select_strategy(
        self,
        run_id: str,
        phase: str,
        iteration: Optional[int] = None,
        evaluation_artifact: Optional[Dict[str, Any]] = None,
    ) -> StrategyDecision:
        """Select the best playbook for the current context.

        Args:
            run_id: Current run identifier.
            phase: Current phase ("implement" or "fix").
            iteration: Iteration number (None for first iteration).
            evaluation_artifact: Optional EvaluationArtifact from previous iteration.

        Returns:
            StrategyDecision with selected playbook and reasoning.
        """
        profile = self._load_profile()
        candidates = all_playbook_ids()

        # Build context from evaluation artifact
        failure_class = None
        root_cause_hint = None
        strategy_recommendations = []
        last_score = None

        if evaluation_artifact:
            failure_class = evaluation_artifact.get("failure_class")
            root_cause_hint = evaluation_artifact.get("root_cause_hint")
            strategy_recommendations = evaluation_artifact.get("strategy_recommendations", [])
            last_score = evaluation_artifact.get("score")

        # Calculate scores for each candidate
        scores: Dict[str, int] = {}
        for playbook_id in candidates:
            score = self._score_playbook(
                playbook_id=playbook_id,
                profile=profile,
                failure_class=failure_class,
                root_cause_hint=root_cause_hint,
                strategy_recommendations=strategy_recommendations,
                iteration=iteration,
            )
            scores[playbook_id] = score

        # Select highest-scoring playbook (deterministic tie-break: lexicographic)
        selected_playbook = max(candidates, key=lambda p: (scores[p], p))
        selected_score = scores[selected_playbook]

        # Build reason
        reason = self._build_reason(
            playbook_id=selected_playbook,
            score=selected_score,
            failure_class=failure_class,
            root_cause_hint=root_cause_hint,
            strategy_recommendations=strategy_recommendations,
        )

        # Build derived_from context
        derived_from = {
            "failure_class": failure_class,
            "root_cause_hint": root_cause_hint,
            "strategy_recommendations": strategy_recommendations,
            "last_score": last_score,
            "profile_name": profile.name,
            "scores": scores,
        }

        # Create decision
        decision = StrategyDecision(
            run_id=run_id,
            phase=phase,
            iteration=iteration,
            selected_playbook=selected_playbook,
            candidates=candidates,
            reason=reason,
            derived_from=derived_from,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            "Selected strategy for run_id=%s phase=%s iteration=%s: %s (score=%d)",
            run_id, phase, iteration, selected_playbook, selected_score
        )

        return decision

    # ------------------------------------------------------------------
    # Scoring logic
    # ------------------------------------------------------------------

    def _score_playbook(
        self,
        playbook_id: str,
        profile: StrategyProfile,
        failure_class: Optional[str],
        root_cause_hint: Optional[str],
        strategy_recommendations: List[str],
        iteration: Optional[int],
    ) -> int:
        """Calculate score for a playbook given the current context.

        Higher score = better fit.

        Scoring factors:
        1. Profile weight (base score)
        2. Failure class learned weight (from StrategyLearningAgent, v1)
        3. Recommended for failure_class (+20)
        4. Recommended for root_cause_hint (+15)
        5. In strategy_recommendations (+30)
        6. Learning history bonus (up to +10)
        7. First iteration bonus for DEFAULT (+5)

        Args:
            playbook_id: The playbook to score.
            profile: Current strategy profile.
            failure_class: Failure classification (if any).
            root_cause_hint: Root cause hint (if any).
            strategy_recommendations: Recommended strategies from evaluation.
            iteration: Current iteration (None for first).

        Returns:
            Integer score (can be negative).
        """
        score = 0

        # 1. Profile weight
        score += profile.playbook_weights.get(playbook_id, 0)

        # 2. Failure class learned weight (deterministic learning from StrategyLearningAgent)
        if failure_class:
            failure_class_weight = self._store.get_failure_class_weight(
                failure_class, playbook_id
            )
            score += failure_class_weight

        # 3. Recommended for failure_class
        if failure_class:
            playbook = PLAYBOOKS.get(playbook_id, {})
            recommended_for = playbook.get("recommended_for", [])
            if failure_class in recommended_for:
                score += 20

        # 4. Recommended for root_cause_hint
        if root_cause_hint:
            playbook = PLAYBOOKS.get(playbook_id, {})
            recommended_for = playbook.get("recommended_for", [])
            if root_cause_hint in recommended_for:
                score += 15

        # 5. In strategy_recommendations from evaluation
        if playbook_id in strategy_recommendations:
            score += 30

        # 6. Learning history bonus
        if failure_class or root_cause_hint:
            learning_bonus = self._get_learning_bonus(
                playbook_id=playbook_id,
                failure_class=failure_class,
                root_cause_hint=root_cause_hint,
            )
            score += learning_bonus

        # 7. First iteration bonus for DEFAULT
        if iteration is None and playbook_id == PlaybookId.DEFAULT:
            score += 5

        return score

    def _get_learning_bonus(
        self,
        playbook_id: str,
        failure_class: Optional[str],
        root_cause_hint: Optional[str],
    ) -> int:
        """Calculate learning bonus based on historical success.

        Looks at past runs with similar failure patterns and rewards
        playbooks that have worked well in those scenarios.

        Args:
            playbook_id: The playbook to score.
            failure_class: Failure classification.
            root_cause_hint: Root cause hint.

        Returns:
            Bonus score (0-10).
        """
        # Query learning history for similar scenarios
        history = self._store.get_learning_history(
            failure_class=failure_class,
            root_cause_hint=root_cause_hint,
            limit=10,  # Look at last 10 similar cases
        )

        if not history:
            return 0

        # Calculate average score for this playbook in similar scenarios
        matching_entries = [
            e for e in history
            if e.get("selected_playbook") == playbook_id
        ]

        if not matching_entries:
            return 0

        avg_score = sum(e.get("outcome_score", 0) for e in matching_entries) / len(matching_entries)

        # Convert to bonus (0-10 scale)
        # Score 80+ → +10 bonus
        # Score 50-79 → +5 bonus
        # Score <50 → 0 bonus
        if avg_score >= 80:
            return 10
        elif avg_score >= 50:
            return 5
        else:
            return 0

    # ------------------------------------------------------------------
    # Reasoning
    # ------------------------------------------------------------------

    def _build_reason(
        self,
        playbook_id: str,
        score: int,
        failure_class: Optional[str],
        root_cause_hint: Optional[str],
        strategy_recommendations: List[str],
    ) -> str:
        """Build human-readable explanation for the selection.

        Args:
            playbook_id: Selected playbook.
            score: Final score.
            failure_class: Failure classification.
            root_cause_hint: Root cause hint.
            strategy_recommendations: Recommended strategies.

        Returns:
            Human-readable reason string.
        """
        parts = [f"Selected '{playbook_id}' (score: {score})."]

        if playbook_id in strategy_recommendations:
            parts.append("Recommended by evaluation artifact.")

        if failure_class:
            playbook = PLAYBOOKS.get(playbook_id, {})
            recommended_for = playbook.get("recommended_for", [])
            if failure_class in recommended_for:
                parts.append(f"Recommended for failure class '{failure_class}'.")

        if root_cause_hint:
            playbook = PLAYBOOKS.get(playbook_id, {})
            recommended_for = playbook.get("recommended_for", [])
            if root_cause_hint in recommended_for:
                parts.append(f"Recommended for root cause '{root_cause_hint}'.")

        if not failure_class and not root_cause_hint:
            parts.append("Using default strategy (no specific failure context).")

        return " ".join(parts)

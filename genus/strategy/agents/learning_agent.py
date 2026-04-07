"""
Strategy Learning Agent

Subscribes to meta.evaluation.completed events and updates the Strategy Store
based on evaluation outcomes. This agent closes the learning loop by adjusting
playbook preferences per failure_class, ensuring GENUS changes behavior between runs.

Safety/Robustness:
- Read-only on RunJournal and Store (except for strategy store writes)
- No network calls
- All exceptions logged to Journal (never silent)
- Deterministic weight updates (no randomness)

Learning Logic v1:
- score >= 80: weight += 1
- score <= 50: weight -= 1
- weights clamped to [-20, +20]
- Only updates for runs with failure_class present
"""

import logging
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Any

from genus.communication.message_bus import Message, MessageBus
from genus.core.run import get_run_id
from genus.dev.agents.base import DevAgentBase
from genus.feedback.topics import FEEDBACK_RECEIVED
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore
from genus.meta import topics as meta_topics
from genus.strategy.store_json import StrategyStoreJson

logger = logging.getLogger(__name__)


# Learning thresholds
WEIGHT_BOOST_THRESHOLD = 80
"""Score threshold for boosting weights (success)."""

WEIGHT_PENALTY_THRESHOLD = 50
"""Score threshold for penalizing weights (failure)."""

WEIGHT_CHANGE_BOOST = 1
"""Weight increment for successful playbooks."""

WEIGHT_CHANGE_PENALTY = -1
"""Weight decrement for failed playbooks."""

WEIGHT_MIN = -20
"""Minimum weight value (clamp floor)."""

WEIGHT_MAX = 20
"""Maximum weight value (clamp ceiling)."""

FEEDBACK_SCORE_DELTA_POSITIVE_THRESHOLD = 3.0
"""score_delta threshold for positive feedback weight update."""

FEEDBACK_SCORE_DELTA_NEGATIVE_THRESHOLD = -3.0
"""score_delta threshold for negative feedback weight update."""


class StrategyLearningAgent(DevAgentBase):
    """Agent that learns from evaluation outcomes and updates strategy preferences.

    Subscribes to meta.evaluation.completed events. For each evaluation:
    1. Load run data from RunJournal
    2. Extract latest StrategyDecision artifact
    3. Extract latest EvaluationArtifact
    4. Apply learning rules to update failure_class_weights
    5. Log learning event to Journal
    6. Save updated weights to Strategy Store

    Args:
        bus: MessageBus instance for pub/sub.
        agent_id: Unique identifier for this agent.
        run_store: JsonlRunStore for accessing run journals.
        strategy_store: StrategyStoreJson for persisting learned preferences.

    Example::

        bus = MessageBus()
        run_store = JsonlRunStore()
        strategy_store = StrategyStoreJson()

        agent = StrategyLearningAgent(
            bus=bus,
            agent_id="strategy-learner-1",
            run_store=run_store,
            strategy_store=strategy_store,
        )
        agent.start()
        # Agent now listens for meta.evaluation.completed events
    """

    def __init__(
        self,
        bus: MessageBus,
        agent_id: str = "StrategyLearningAgent",
        run_store: Optional[JsonlRunStore] = None,
        strategy_store: Optional[StrategyStoreJson] = None,
    ) -> None:
        super().__init__(bus, agent_id)
        self._run_store = run_store or JsonlRunStore()
        self._strategy_store = strategy_store or StrategyStoreJson()

    def _subscribe_topics(self) -> List[Tuple[str, Callable[[Message], Awaitable[None]]]]:
        """Register handler for evaluation completion and feedback events."""
        return [
            (meta_topics.META_EVALUATION_COMPLETED, self._handle_evaluation_completed),
            (FEEDBACK_RECEIVED, self._handle_feedback_received),
        ]

    async def _handle_evaluation_completed(self, msg: Message) -> None:
        """Handle meta.evaluation.completed events.

        Args:
            msg: The evaluation completion message.
        """
        # Extract run_id from message metadata
        run_id = get_run_id(msg)
        if not run_id:
            # Cannot process without run_id
            logger.debug("Received meta.evaluation.completed without run_id, ignoring")
            return

        # Load run journal
        journal = RunJournal(run_id, self._run_store)
        if not journal.exists():
            logger.debug(
                "Run journal for run_id=%s does not exist, ignoring evaluation",
                run_id
            )
            return

        try:
            # Load latest evaluation artifact
            evaluation_artifact = self._load_latest_evaluation(journal)
            if not evaluation_artifact:
                logger.info(
                    "No evaluation artifact found for run_id=%s, skipping learning",
                    run_id
                )
                return

            # Load latest strategy decision artifact
            strategy_decision = self._load_latest_strategy_decision(journal)
            if not strategy_decision:
                logger.info(
                    "No strategy decision found for run_id=%s, skipping learning",
                    run_id
                )
                return

            # Extract learning inputs
            failure_class = evaluation_artifact.get("failure_class")
            score = evaluation_artifact.get("score")
            final_status = evaluation_artifact.get("final_status")
            selected_playbook = strategy_decision.get("selected_playbook")

            # Validate inputs
            if not self._validate_learning_inputs(
                run_id, failure_class, score, selected_playbook, journal
            ):
                return

            # Apply learning rules
            weight_change = self._calculate_weight_change(score)
            if weight_change == 0:
                logger.debug(
                    "Score %d is in neutral zone for run_id=%s, no weight update",
                    score, run_id
                )
                # Still log the event for traceability
                journal.log_event(
                    phase="strategy",
                    event_type="strategy_learning_skipped",
                    summary=f"Score {score} in neutral zone, no weight update",
                    data={
                        "run_id": run_id,
                        "failure_class": failure_class,
                        "selected_playbook": selected_playbook,
                        "score": score,
                        "reason": "neutral_score",
                    },
                )
                return

            # Update failure_class_weights in store
            old_weight = self._strategy_store.get_failure_class_weight(
                failure_class, selected_playbook
            )
            new_weight = self._clamp_weight(old_weight + weight_change)

            self._strategy_store.set_failure_class_weight(
                failure_class, selected_playbook, new_weight
            )

            logger.info(
                "Strategy learning: run_id=%s, failure_class=%s, playbook=%s, "
                "score=%d, weight %d -> %d",
                run_id, failure_class, selected_playbook, score, old_weight, new_weight
            )

            # Log learning event to journal
            journal.log_event(
                phase="strategy",
                event_type="strategy_learned",
                summary=f"Updated {selected_playbook} weight for {failure_class}: "
                        f"{old_weight} -> {new_weight}",
                data={
                    "run_id": run_id,
                    "failure_class": failure_class,
                    "selected_playbook": selected_playbook,
                    "score": score,
                    "final_status": final_status,
                    "old_weight": old_weight,
                    "new_weight": new_weight,
                    "weight_change": weight_change,
                },
            )

            # Save learning artifact for analytics
            journal.save_artifact(
                phase="strategy",
                artifact_type="strategy_update",
                payload={
                    "run_id": run_id,
                    "failure_class": failure_class,
                    "selected_playbook": selected_playbook,
                    "score": score,
                    "old_weight": old_weight,
                    "new_weight": new_weight,
                    "weight_change": weight_change,
                    "learning_rule": "v1_simple_threshold",
                },
            )

        except Exception as exc:
            # Never silent pass - log to journal
            error_msg = str(exc)[:500]  # Truncate long errors
            logger.error(
                "Strategy learning failed for run_id=%s: %s",
                run_id, error_msg, exc_info=True
            )

            try:
                journal.log_event(
                    phase="strategy",
                    event_type="strategy_learning_failed",
                    summary=f"Learning failed: {type(exc).__name__}",
                    data={
                        "run_id": run_id,
                        "error": error_msg,
                        "error_type": type(exc).__name__,
                    },
                )
            except Exception as _journal_exc:
                logger.warning(
                    "StrategyLearningAgent: secondary journal write failed for run %s: %s",
                    run_id, _journal_exc,
                )

    async def _handle_feedback_received(self, msg: Message) -> None:
        """Handle feedback.received — apply human outcome signal to strategy weights.

        Both outcome and score_delta must agree for a weight change to occur:
        - outcome="good" and score_delta >= FEEDBACK_SCORE_DELTA_POSITIVE_THRESHOLD → weight += 1
        - outcome="bad"  and score_delta <= FEEDBACK_SCORE_DELTA_NEGATIVE_THRESHOLD → weight -= 1
        - outcome="unknown" → no weight change, only journal log
        - outcome/score_delta mismatch or score_delta in (-3.0, 3.0) → neutral, no change

        Args:
            msg: The feedback.received message.
        """
        # 1. Extract run_id — from metadata first, then payload fallback
        run_id = get_run_id(msg)
        if not run_id:
            run_id = msg.payload.get("run_id") if msg.payload else None
        if not run_id:
            logger.warning(
                "Received feedback.received without run_id, ignoring"
            )
            return

        # 2. Read outcome and score_delta from payload
        payload = msg.payload or {}
        outcome = payload.get("outcome", "unknown")
        score_delta = payload.get("score_delta", 0.0)

        # 3. outcome == "unknown" → journal log, return
        if outcome == "unknown":
            logger.debug(
                "feedback.received for run_id=%s: outcome=unknown, no weight update",
                run_id,
            )
            # Load journal for logging if available
            journal = RunJournal(run_id, self._run_store)
            if journal.exists():
                journal.log_event(
                    phase="strategy",
                    event_type="feedback_learning_skipped",
                    summary="Feedback outcome=unknown, no weight update",
                    data={"run_id": run_id, "outcome": outcome, "score_delta": score_delta},
                )
            return

        try:
            # 4. Load RunJournal — if not exists: debug, return
            journal = RunJournal(run_id, self._run_store)
            if not journal.exists():
                logger.debug(
                    "Run journal for run_id=%s does not exist, ignoring feedback",
                    run_id,
                )
                return

            # 5. Load latest strategy_decision artifact — if not found: info, return
            strategy_decision = self._load_latest_strategy_decision(journal)
            if not strategy_decision:
                logger.info(
                    "No strategy decision found for run_id=%s, skipping feedback learning",
                    run_id,
                )
                return

            # 6. Load latest evaluation artifact — if not found: info, return
            evaluation_artifact = self._load_latest_evaluation(journal)
            if not evaluation_artifact:
                logger.info(
                    "No evaluation artifact found for run_id=%s, skipping feedback learning",
                    run_id,
                )
                return

            # 7. Extract failure_class — if None: debug, return
            failure_class = evaluation_artifact.get("failure_class")
            if not failure_class:
                logger.debug(
                    "No failure_class in evaluation for run_id=%s, skipping feedback learning",
                    run_id,
                )
                return

            selected_playbook = strategy_decision.get("selected_playbook")
            if not selected_playbook:
                logger.info(
                    "No selected_playbook in strategy decision for run_id=%s, "
                    "skipping feedback learning",
                    run_id,
                )
                return

            # 8. Calculate weight_change from outcome + score_delta using feedback thresholds
            if outcome == "good" and score_delta >= FEEDBACK_SCORE_DELTA_POSITIVE_THRESHOLD:
                weight_change = 1
            elif outcome == "bad" and score_delta <= FEEDBACK_SCORE_DELTA_NEGATIVE_THRESHOLD:
                weight_change = -1
            else:
                weight_change = 0

            if weight_change == 0:
                logger.debug(
                    "feedback.received for run_id=%s: score_delta=%.2f is neutral, "
                    "no weight update",
                    run_id, score_delta,
                )
                journal.log_event(
                    phase="strategy",
                    event_type="feedback_learning_skipped",
                    summary=f"score_delta {score_delta:.2f} is neutral, no weight update",
                    data={
                        "run_id": run_id,
                        "outcome": outcome,
                        "score_delta": score_delta,
                        "failure_class": failure_class,
                        "selected_playbook": selected_playbook,
                        "reason": "neutral_score_delta",
                    },
                )
                return

            # 9. Update weight in strategy store
            old_weight = self._strategy_store.get_failure_class_weight(
                failure_class, selected_playbook
            )
            new_weight = self._clamp_weight(old_weight + weight_change)

            self._strategy_store.set_failure_class_weight(
                failure_class, selected_playbook, new_weight
            )

            logger.info(
                "Feedback learning: run_id=%s, failure_class=%s, playbook=%s, "
                "outcome=%s, score_delta=%.2f, weight %d -> %d",
                run_id, failure_class, selected_playbook,
                outcome, score_delta, old_weight, new_weight,
            )

            # 10. Log learning event to journal
            journal.log_event(
                phase="strategy",
                event_type="feedback_learning_applied",
                summary=f"Feedback updated {selected_playbook} weight for {failure_class}: "
                        f"{old_weight} -> {new_weight}",
                data={
                    "run_id": run_id,
                    "outcome": outcome,
                    "score_delta": score_delta,
                    "failure_class": failure_class,
                    "selected_playbook": selected_playbook,
                    "old_weight": old_weight,
                    "new_weight": new_weight,
                    "weight_change": weight_change,
                },
            )

            # 11. Save feedback learning artifact for analytics
            journal.save_artifact(
                phase="strategy",
                artifact_type="feedback_learning_update",
                payload={
                    "run_id": run_id,
                    "outcome": outcome,
                    "score_delta": score_delta,
                    "failure_class": failure_class,
                    "selected_playbook": selected_playbook,
                    "old_weight": old_weight,
                    "new_weight": new_weight,
                    "weight_change": weight_change,
                },
            )

        except Exception as exc:
            # Never silent pass — log to journal
            error_msg = str(exc)[:500]
            logger.error(
                "Feedback learning failed for run_id=%s: %s",
                run_id, error_msg, exc_info=True,
            )

            try:
                journal = RunJournal(run_id, self._run_store)
                if journal.exists():
                    journal.log_event(
                        phase="strategy",
                        event_type="feedback_learning_failed",
                        summary=f"Feedback learning failed: {type(exc).__name__}",
                        data={
                            "run_id": run_id,
                            "error": error_msg,
                            "error_type": type(exc).__name__,
                        },
                    )
            except Exception as _journal_exc:
                logger.warning(
                    "StrategyLearningAgent: secondary journal write failed for feedback run %s: %s",
                    run_id, _journal_exc,
                )

    def _load_latest_evaluation(self, journal: RunJournal) -> Optional[Dict[str, Any]]:
        """Load the latest evaluation artifact from the journal.

        Args:
            journal: The RunJournal for the run.

        Returns:
            The evaluation artifact payload dict, or None if not found.
        """
        artifact_ids = journal.list_artifacts(artifact_type="evaluation")
        if not artifact_ids:
            return None

        # Get the most recent artifact (artifacts are ordered by save time)
        latest_id = artifact_ids[-1]
        artifact_record = journal.load_artifact(latest_id)

        if artifact_record:
            return artifact_record.payload
        return None

    def _load_latest_strategy_decision(
        self, journal: RunJournal
    ) -> Optional[Dict[str, Any]]:
        """Load the latest strategy decision artifact from the journal.

        Args:
            journal: The RunJournal for the run.

        Returns:
            The strategy decision payload dict, or None if not found.
        """
        artifact_ids = journal.list_artifacts(artifact_type="strategy_decision")
        if not artifact_ids:
            return None

        # Get the most recent artifact
        latest_id = artifact_ids[-1]
        artifact_record = journal.load_artifact(latest_id)

        if artifact_record:
            return artifact_record.payload
        return None

    def _validate_learning_inputs(
        self,
        run_id: str,
        failure_class: Optional[str],
        score: Optional[int],
        selected_playbook: Optional[str],
        journal: RunJournal,
    ) -> bool:
        """Validate that we have all required inputs for learning.

        Args:
            run_id: The run identifier.
            failure_class: The failure classification.
            score: The evaluation score.
            selected_playbook: The selected playbook.
            journal: The RunJournal for logging validation failures.

        Returns:
            True if inputs are valid, False otherwise.
        """
        # If no failure_class, this is a successful run without specific failure
        # In v1, we only learn from failure_class contexts
        if not failure_class:
            logger.debug(
                "No failure_class for run_id=%s, skipping learning (v1 scope)",
                run_id
            )
            return False

        if score is None:
            logger.warning(
                "No score in evaluation for run_id=%s, cannot apply learning",
                run_id
            )
            journal.log_event(
                phase="strategy",
                event_type="strategy_learning_skipped",
                summary="No score available in evaluation",
                data={"run_id": run_id, "reason": "missing_score"},
            )
            return False

        if not selected_playbook:
            logger.warning(
                "No selected_playbook in decision for run_id=%s, cannot apply learning",
                run_id
            )
            journal.log_event(
                phase="strategy",
                event_type="strategy_learning_skipped",
                summary="No selected playbook in strategy decision",
                data={"run_id": run_id, "reason": "missing_playbook"},
            )
            return False

        return True

    def _calculate_weight_change(self, score: int) -> int:
        """Calculate weight change based on score.

        Learning rules v1:
        - score >= 80: +1 (boost successful strategies)
        - score <= 50: -1 (penalize failed strategies)
        - 50 < score < 80: 0 (neutral, no change)

        Args:
            score: Evaluation score (0-100).

        Returns:
            Weight change delta (-1, 0, or +1).
        """
        if score >= WEIGHT_BOOST_THRESHOLD:
            return WEIGHT_CHANGE_BOOST
        elif score <= WEIGHT_PENALTY_THRESHOLD:
            return WEIGHT_CHANGE_PENALTY
        else:
            return 0

    def _clamp_weight(self, weight: int) -> int:
        """Clamp weight to valid range.

        Args:
            weight: Raw weight value.

        Returns:
            Weight clamped to [WEIGHT_MIN, WEIGHT_MAX].
        """
        return max(WEIGHT_MIN, min(WEIGHT_MAX, weight))

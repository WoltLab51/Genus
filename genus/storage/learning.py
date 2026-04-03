"""
Learning Engine for GENUS - enables learning from feedback.

This module implements the core learning mechanism that allows GENUS
to improve decisions based on past feedback without using ML libraries.
"""
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
import logging
import hashlib
import json

logger = logging.getLogger(__name__)


class PatternScore:
    """Represents a pattern's success/failure score."""

    def __init__(self):
        self.success_count = 0
        self.failure_count = 0
        self.total_score = 0.0
        self.decision_count = 0

    def add_feedback(self, label: str, score: float) -> None:
        """Add feedback to pattern score."""
        self.decision_count += 1
        self.total_score += score

        if label == "success":
            self.success_count += 1
        elif label == "failure":
            self.failure_count += 1

    def get_success_rate(self) -> float:
        """Calculate success rate."""
        if self.decision_count == 0:
            return 0.5  # Neutral for no data
        return self.success_count / self.decision_count

    def get_average_score(self) -> float:
        """Calculate average feedback score."""
        if self.decision_count == 0:
            return 0.0
        return self.total_score / self.decision_count

    def get_weight(self) -> float:
        """
        Calculate weight for this pattern.
        Weight increases for successful patterns and decreases for failed ones.
        """
        if self.decision_count == 0:
            return 1.0  # Neutral weight for new patterns

        success_rate = self.get_success_rate()
        avg_score = self.get_average_score()

        # Combine success rate and average score
        # Weight ranges from 0.1 (very bad) to 2.0 (very good)
        base_weight = success_rate * 1.5 + avg_score * 0.5
        return max(0.1, min(2.0, base_weight))


class LearningEngine:
    """
    Learning engine that analyzes feedback and adjusts decision recommendations.

    Uses simple, deterministic logic:
    - Tracks patterns in decision contexts
    - Assigns weights based on past success/failure
    - Adjusts confidence and recommendations based on learned patterns
    """

    def __init__(self, feedback_store, decision_store):
        """
        Initialize learning engine.

        Args:
            feedback_store: FeedbackStore instance
            decision_store: DecisionStore instance
        """
        self.feedback_store = feedback_store
        self.decision_store = decision_store
        self._pattern_cache: Dict[str, PatternScore] = {}
        self._cache_valid = False

    async def analyze_feedback(self) -> Dict[str, Any]:
        """
        Analyze all stored feedback to identify patterns.

        Returns:
            Analysis summary with success/failure patterns
        """
        all_feedback = await self.feedback_store.get_all_feedback()

        if not all_feedback:
            return {
                "total_feedback": 0,
                "success_count": 0,
                "failure_count": 0,
                "patterns": {},
            }

        success_count = 0
        failure_count = 0
        pattern_scores: Dict[str, PatternScore] = defaultdict(PatternScore)

        for feedback in all_feedback:
            if feedback["label"] == "success":
                success_count += 1
            elif feedback["label"] == "failure":
                failure_count += 1

            # Get the associated decision
            decision = await self.decision_store.get_decision(feedback["decision_id"])
            if decision:
                # Extract pattern from context and recommendation
                pattern = self._extract_pattern(
                    decision["context"], decision["recommendation"]
                )
                pattern_scores[pattern].add_feedback(
                    feedback["label"], feedback["score"]
                )

        # Cache the pattern scores
        self._pattern_cache = dict(pattern_scores)
        self._cache_valid = True

        logger.info(
            f"Analyzed {len(all_feedback)} feedback items, "
            f"found {len(pattern_scores)} patterns"
        )

        return {
            "total_feedback": len(all_feedback),
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": success_count / len(all_feedback) if all_feedback else 0.0,
            "patterns": {
                pattern: {
                    "weight": score.get_weight(),
                    "success_rate": score.get_success_rate(),
                    "decision_count": score.decision_count,
                    "average_score": score.get_average_score(),
                }
                for pattern, score in pattern_scores.items()
            },
        }

    def _extract_pattern(self, context: str, recommendation: str) -> str:
        """
        Extract a pattern identifier from context and recommendation.

        Uses a hash of key elements to create pattern signatures.
        This allows similar decisions to be grouped together.
        """
        # Create a normalized pattern representation
        # Extract key terms (simple tokenization)
        context_terms = set(context.lower().split()[:10])  # First 10 words
        rec_terms = set(recommendation.lower().split()[:5])  # First 5 words

        # Create a pattern signature
        pattern_str = f"{sorted(context_terms)}:{sorted(rec_terms)}"
        pattern_hash = hashlib.md5(pattern_str.encode()).hexdigest()[:8]

        return pattern_hash

    async def query_similar_decisions(
        self, context: str, recommendation: str
    ) -> List[Dict[str, Any]]:
        """
        Query past decisions similar to the current one.

        Args:
            context: Decision context
            recommendation: Proposed recommendation

        Returns:
            List of similar past decisions with their feedback
        """
        pattern = self._extract_pattern(context, recommendation)

        # Get all decisions
        all_decisions = await self.decision_store.get_all_decisions()

        similar_decisions = []
        for decision in all_decisions:
            decision_pattern = self._extract_pattern(
                decision["context"], decision["recommendation"]
            )
            if decision_pattern == pattern:
                # Get feedback for this decision
                feedback_list = await self.feedback_store.get_feedback_for_decision(
                    decision["decision_id"]
                )
                decision["feedback"] = feedback_list
                similar_decisions.append(decision)

        logger.debug(
            f"Found {len(similar_decisions)} similar decisions for pattern {pattern}"
        )

        return similar_decisions

    async def adjust_decision(
        self, context: str, recommendation: str, confidence: float
    ) -> Tuple[str, float, Dict[str, Any]]:
        """
        Adjust a decision based on past learning.

        Args:
            context: Decision context
            recommendation: Proposed recommendation
            confidence: Original confidence score

        Returns:
            Tuple of (adjusted_recommendation, adjusted_confidence, learning_info)
        """
        # Ensure pattern cache is up to date
        if not self._cache_valid:
            await self.analyze_feedback()

        # Extract pattern and get its score
        pattern = self._extract_pattern(context, recommendation)
        pattern_score = self._pattern_cache.get(pattern)

        if pattern_score is None:
            # No past data for this pattern
            logger.debug(f"No learning data for pattern {pattern}")
            return recommendation, confidence, {
                "pattern": pattern,
                "learning_applied": False,
                "reason": "No past feedback for this pattern",
            }

        # Get pattern weight
        weight = pattern_score.get_weight()
        success_rate = pattern_score.get_success_rate()

        # Adjust confidence based on past performance
        adjusted_confidence = confidence * weight

        # Clip confidence to valid range [0.0, 1.0]
        adjusted_confidence = max(0.0, min(1.0, adjusted_confidence))

        learning_info = {
            "pattern": pattern,
            "learning_applied": True,
            "original_confidence": confidence,
            "adjusted_confidence": adjusted_confidence,
            "pattern_weight": weight,
            "pattern_success_rate": success_rate,
            "pattern_decision_count": pattern_score.decision_count,
            "adjustment_reason": self._get_adjustment_reason(
                weight, success_rate, pattern_score.decision_count
            ),
        }

        logger.info(
            f"Learning applied: pattern={pattern}, "
            f"confidence {confidence:.2f} -> {adjusted_confidence:.2f}, "
            f"weight={weight:.2f}"
        )

        return recommendation, adjusted_confidence, learning_info

    def _get_adjustment_reason(
        self, weight: float, success_rate: float, decision_count: int
    ) -> str:
        """Generate human-readable reason for adjustment."""
        if weight > 1.2:
            return (
                f"Increased confidence based on {decision_count} past decisions "
                f"with {success_rate:.1%} success rate"
            )
        elif weight < 0.8:
            return (
                f"Decreased confidence based on {decision_count} past decisions "
                f"with {success_rate:.1%} success rate"
            )
        else:
            return f"Neutral adjustment based on {decision_count} past decisions"

    def invalidate_cache(self) -> None:
        """Invalidate pattern cache, forcing re-analysis on next use."""
        self._cache_valid = False
        logger.debug("Learning engine cache invalidated")

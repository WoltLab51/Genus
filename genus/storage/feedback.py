"""Feedback Store - Storage for user feedback on decisions."""

from typing import List, Optional
from genus.storage.models import Feedback
from datetime import datetime, timezone


class FeedbackStore:
    """
    Store for user feedback.

    Provides:
    - Adding feedback
    - Retrieving feedback by decision ID
    - Computing average ratings
    """

    def __init__(self, max_size: int = 1000):
        """
        Initialize the feedback store.

        Args:
            max_size: Maximum number of feedback entries to retain
        """
        self._feedback: List[Feedback] = []
        self._max_size = max_size

    def add(self, feedback: Feedback) -> None:
        """
        Add feedback to the store.

        Args:
            feedback: The feedback to add
        """
        self._feedback.append(feedback)
        if len(self._feedback) > self._max_size:
            self._feedback.pop(0)

    def get_for_decision(self, decision_id: str) -> List[Feedback]:
        """
        Get all feedback for a specific decision.

        Args:
            decision_id: Decision identifier

        Returns:
            List of feedback entries for the decision
        """
        return [f for f in self._feedback if f.decision_id == decision_id]

    def get_recent(self, limit: int = 20) -> List[Feedback]:
        """
        Get recent feedback.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of recent feedback
        """
        return self._feedback[-limit:]

    def get_average_rating(self, decision_id: Optional[str] = None) -> float:
        """
        Get average rating.

        Args:
            decision_id: Optional decision ID to filter by

        Returns:
            Average rating (0.0 if no feedback)
        """
        if decision_id:
            feedback_list = self.get_for_decision(decision_id)
        else:
            feedback_list = self._feedback

        if not feedback_list:
            return 0.0

        return sum(f.rating for f in feedback_list) / len(feedback_list)

    def count(self) -> int:
        """
        Get total number of feedback entries.

        Returns:
            Number of feedback entries stored
        """
        return len(self._feedback)

    def clear(self) -> None:
        """Clear all feedback."""
        self._feedback.clear()

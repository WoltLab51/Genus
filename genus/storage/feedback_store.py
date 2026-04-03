"""Storage for user feedback on agent decisions."""

from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class Feedback:
    """Represents user feedback on a decision."""
    feedback_id: str
    decision_id: str
    rating: int  # 1-5
    comment: Optional[str]
    timestamp: datetime


class FeedbackStore:
    """Store for collecting and managing user feedback."""

    def __init__(self):
        """Initialize the feedback store."""
        self._feedback: Dict[str, Feedback] = {}

    async def record_feedback(
        self,
        feedback_id: str,
        decision_id: str,
        rating: int,
        comment: Optional[str] = None
    ) -> None:
        """Record user feedback on a decision.

        Args:
            feedback_id: Unique feedback identifier
            decision_id: Decision being rated
            rating: Rating from 1-5
            comment: Optional feedback comment

        Raises:
            ValueError: If rating is not between 1-5
        """
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        feedback = Feedback(
            feedback_id=feedback_id,
            decision_id=decision_id,
            rating=rating,
            comment=comment,
            timestamp=datetime.utcnow()
        )
        self._feedback[feedback_id] = feedback

    async def get_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """Get feedback by ID.

        Args:
            feedback_id: Feedback identifier

        Returns:
            Feedback dict or None if not found
        """
        feedback = self._feedback.get(feedback_id)
        if feedback:
            result = asdict(feedback)
            result["timestamp"] = feedback.timestamp.isoformat()
            return result
        return None

    async def list_feedback(
        self,
        decision_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List recent feedback.

        Args:
            decision_id: Optional decision filter
            limit: Maximum number of feedback items to return

        Returns:
            List of feedback dicts
        """
        feedback_list = list(self._feedback.values())
        if decision_id:
            feedback_list = [f for f in feedback_list if f.decision_id == decision_id]

        # Sort by timestamp descending
        feedback_list.sort(key=lambda f: f.timestamp, reverse=True)
        feedback_list = feedback_list[:limit]

        return [
            {**asdict(f), "timestamp": f.timestamp.isoformat()}
            for f in feedback_list
        ]

    async def get_average_rating(self, decision_id: Optional[str] = None) -> Optional[float]:
        """Calculate average rating.

        Args:
            decision_id: Optional decision filter

        Returns:
            Average rating or None if no feedback
        """
        feedback_list = list(self._feedback.values())
        if decision_id:
            feedback_list = [f for f in feedback_list if f.decision_id == decision_id]

        if not feedback_list:
            return None

        return sum(f.rating for f in feedback_list) / len(feedback_list)

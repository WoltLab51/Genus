"""Feedback storage for tracking feedback and learning."""

from typing import Any, Dict, List, Optional
from datetime import datetime, UTC


class FeedbackStore:
    """
    Storage for feedback on agent actions and decisions.

    Collects feedback from users and other agents to support
    learning and improvement.
    """

    def __init__(self):
        """Initialize the feedback store."""
        self._feedback: List[Dict[str, Any]] = []

    async def store_feedback(
        self,
        target: str,
        feedback_type: str,
        content: Dict[str, Any],
        source: Optional[str] = None
    ) -> str:
        """
        Store feedback.

        Args:
            target: Target of the feedback (agent, decision, etc.)
            feedback_type: Type of feedback (positive, negative, suggestion)
            content: Feedback content
            source: Optional source of the feedback

        Returns:
            Feedback ID
        """
        feedback_entry = {
            "id": str(len(self._feedback)),
            "timestamp": datetime.now(UTC).isoformat(),
            "target": target,
            "type": feedback_type,
            "content": content,
            "source": source
        }
        self._feedback.append(feedback_entry)
        return feedback_entry["id"]

    async def get_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """
        Get specific feedback by ID.

        Args:
            feedback_id: ID of the feedback

        Returns:
            Feedback data or None if not found
        """
        try:
            idx = int(feedback_id)
            if 0 <= idx < len(self._feedback):
                return self._feedback[idx]
        except (ValueError, IndexError):
            pass
        return None

    async def query_feedback(
        self,
        target: Optional[str] = None,
        feedback_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query feedback with optional filters.

        Args:
            target: Optional target filter
            feedback_type: Optional feedback type filter
            limit: Maximum number of results

        Returns:
            List of matching feedback entries
        """
        results = self._feedback.copy()

        if target:
            results = [f for f in results if f["target"] == target]

        if feedback_type:
            results = [f for f in results if f["type"] == feedback_type]

        return results[-limit:]

    async def clear(self) -> None:
        """Clear all feedback."""
        self._feedback.clear()

    def count(self) -> int:
        """Get total count of feedback entries."""
        return len(self._feedback)

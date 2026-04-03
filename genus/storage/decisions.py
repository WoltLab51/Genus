"""Decision Store - Persistent storage for decisions."""

from typing import List, Optional
from genus.storage.models import Decision
from datetime import datetime, timezone


class DecisionStore:
    """
    Store for decision history.

    Provides:
    - Adding decisions
    - Retrieving recent decisions
    - Filtering by priority
    - Counting decisions
    """

    def __init__(self, max_size: int = 1000):
        """
        Initialize the decision store.

        Args:
            max_size: Maximum number of decisions to retain
        """
        self._decisions: List[Decision] = []
        self._max_size = max_size

    def add(self, decision: Decision) -> None:
        """
        Add a decision to the store.

        Args:
            decision: The decision to add
        """
        self._decisions.append(decision)
        if len(self._decisions) > self._max_size:
            self._decisions.pop(0)

    def get_recent(self, limit: int = 20) -> List[Decision]:
        """
        Get recent decisions.

        Args:
            limit: Maximum number of decisions to return

        Returns:
            List of recent decisions
        """
        return self._decisions[-limit:]

    def get_by_priority(self, priority: int) -> List[Decision]:
        """
        Get decisions by priority.

        Args:
            priority: Priority level to filter by

        Returns:
            List of decisions with matching priority
        """
        return [d for d in self._decisions if d.priority == priority]

    def count(self) -> int:
        """
        Get total number of decisions.

        Returns:
            Number of decisions stored
        """
        return len(self._decisions)

    def clear(self) -> None:
        """Clear all decisions."""
        self._decisions.clear()

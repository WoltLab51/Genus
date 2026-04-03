"""Decision storage for tracking agent decisions."""

from typing import Any, Dict, List, Optional
from datetime import datetime, UTC


class DecisionStore:
    """
    Storage for agent decisions and reasoning.

    Tracks all decisions made by agents including the context,
    reasoning, and outcomes.
    """

    def __init__(self):
        """Initialize the decision store."""
        self._decisions: List[Dict[str, Any]] = []

    async def store_decision(
        self,
        agent: str,
        decision: str,
        context: Dict[str, Any],
        reasoning: Optional[str] = None
    ) -> str:
        """
        Store a decision.

        Args:
            agent: Name of the agent making the decision
            decision: The decision made
            context: Context in which the decision was made
            reasoning: Optional reasoning behind the decision

        Returns:
            Decision ID
        """
        decision_entry = {
            "id": str(len(self._decisions)),
            "timestamp": datetime.now(UTC).isoformat(),
            "agent": agent,
            "decision": decision,
            "context": context,
            "reasoning": reasoning,
            "outcome": None
        }
        self._decisions.append(decision_entry)
        return decision_entry["id"]

    async def update_outcome(self, decision_id: str, outcome: Dict[str, Any]) -> bool:
        """
        Update the outcome of a decision.

        Args:
            decision_id: ID of the decision to update
            outcome: Outcome data

        Returns:
            True if updated, False if decision not found
        """
        try:
            idx = int(decision_id)
            if 0 <= idx < len(self._decisions):
                self._decisions[idx]["outcome"] = outcome
                return True
        except (ValueError, IndexError):
            pass
        return False

    async def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific decision by ID.

        Args:
            decision_id: ID of the decision

        Returns:
            Decision data or None if not found
        """
        try:
            idx = int(decision_id)
            if 0 <= idx < len(self._decisions):
                return self._decisions[idx]
        except (ValueError, IndexError):
            pass
        return None

    async def query_decisions(
        self,
        agent: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query decisions with optional filters.

        Args:
            agent: Optional agent name filter
            limit: Maximum number of results

        Returns:
            List of matching decisions
        """
        results = self._decisions.copy()

        if agent:
            results = [d for d in results if d["agent"] == agent]

        return results[-limit:]

    async def clear(self) -> None:
        """Clear all decisions."""
        self._decisions.clear()

    def count(self) -> int:
        """Get total count of decisions."""
        return len(self._decisions)

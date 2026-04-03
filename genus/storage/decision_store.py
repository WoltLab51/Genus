"""Storage for agent decisions and outcomes."""

from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class Decision:
    """Represents an agent decision."""
    decision_id: str
    agent: str
    decision_type: str
    data: Any
    timestamp: datetime
    outcome: Optional[str] = None


class DecisionStore:
    """Store for tracking agent decisions and their outcomes."""

    def __init__(self):
        """Initialize the decision store."""
        self._decisions: Dict[str, Decision] = {}

    async def record_decision(
        self,
        decision_id: str,
        agent: str,
        decision_type: str,
        data: Any
    ) -> None:
        """Record a decision made by an agent.

        Args:
            decision_id: Unique decision identifier
            agent: Agent that made the decision
            decision_type: Type of decision
            data: Decision data
        """
        decision = Decision(
            decision_id=decision_id,
            agent=agent,
            decision_type=decision_type,
            data=data,
            timestamp=datetime.utcnow()
        )
        self._decisions[decision_id] = decision

    async def update_outcome(self, decision_id: str, outcome: str) -> bool:
        """Update the outcome of a decision.

        Args:
            decision_id: Decision identifier
            outcome: Outcome description

        Returns:
            True if updated, False if decision not found
        """
        if decision_id in self._decisions:
            self._decisions[decision_id].outcome = outcome
            return True
        return False

    async def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Get a decision by ID.

        Args:
            decision_id: Decision identifier

        Returns:
            Decision dict or None if not found
        """
        decision = self._decisions.get(decision_id)
        if decision:
            result = asdict(decision)
            result["timestamp"] = decision.timestamp.isoformat()
            return result
        return None

    async def list_decisions(
        self,
        agent: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List recent decisions.

        Args:
            agent: Optional agent filter
            limit: Maximum number of decisions to return

        Returns:
            List of decision dicts
        """
        decisions = list(self._decisions.values())
        if agent:
            decisions = [d for d in decisions if d.agent == agent]

        # Sort by timestamp descending
        decisions.sort(key=lambda d: d.timestamp, reverse=True)
        decisions = decisions[:limit]

        return [
            {**asdict(d), "timestamp": d.timestamp.isoformat()}
            for d in decisions
        ]

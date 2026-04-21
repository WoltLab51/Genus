"""Functional Agent Registry — GENUS-2.0

Central registry that maps agent IDs to :class:`FunctionalAgent` instances.

Agents are registered at application startup (``lifespan.py``) via
:meth:`FunctionalAgentRegistry.register`.  The API layer uses
:meth:`FunctionalAgentRegistry.get` to resolve ``agent_id`` path
parameters to concrete agent instances.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from genus.functional_agents.base import FunctionalAgent


class FunctionalAgentRegistry:
    """Registry that maps agent IDs to :class:`FunctionalAgent` instances.

    Usage::

        registry = FunctionalAgentRegistry()
        registry.register(HomeAgent())
        registry.register(FamilyAgent())

        agent = registry.get("home")   # → HomeAgent instance
        agents = registry.list_all()   # → [HomeAgent, FamilyAgent]
    """

    def __init__(self) -> None:
        self._agents: Dict[str, FunctionalAgent] = {}

    def register(self, agent: FunctionalAgent) -> None:
        """Register a functional agent.

        Args:
            agent: Agent instance to register. Must have a non-empty
                   ``agent_id`` class attribute.

        Raises:
            ValueError: If ``agent.agent_id`` is empty or not set.
        """
        agent_id = getattr(agent, "agent_id", None)
        if not agent_id:
            raise ValueError(
                f"FunctionalAgent {type(agent).__name__!r} must have a non-empty agent_id"
            )
        self._agents[agent_id] = agent

    def get(self, agent_id: str) -> Optional[FunctionalAgent]:
        """Return the agent for *agent_id*, or ``None`` if not found.

        Args:
            agent_id: The agent identifier string.

        Returns:
            :class:`FunctionalAgent` instance, or ``None``.
        """
        return self._agents.get(agent_id)

    def list_all(self) -> List[FunctionalAgent]:
        """Return all registered agents in insertion order.

        Returns:
            List of :class:`FunctionalAgent` instances.
        """
        return list(self._agents.values())

    def agent_ids(self) -> List[str]:
        """Return all registered agent IDs in sorted order.

        Returns:
            Sorted list of agent ID strings.
        """
        return sorted(self._agents.keys())

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._agents

"""Lifecycle Management - Coordinated agent startup and shutdown."""

from typing import List, Optional
from genus.core.agent import Agent, AgentState
import asyncio


class Lifecycle:
    """
    Manages the lifecycle of multiple agents.

    Provides coordinated:
    - Registration of agents
    - Sequential initialization and startup
    - Graceful shutdown
    - State monitoring

    Follows Single Responsibility Principle.
    """

    def __init__(self):
        """Initialize the lifecycle manager."""
        self._agents: List[Agent] = []
        self._running = False

    def register_agent(self, agent: Agent) -> None:
        """
        Register an agent for lifecycle management.

        Args:
            agent: The agent to register
        """
        if agent not in self._agents:
            self._agents.append(agent)

    def unregister_agent(self, agent: Agent) -> None:
        """
        Unregister an agent from lifecycle management.

        Args:
            agent: The agent to unregister
        """
        if agent in self._agents:
            self._agents.remove(agent)

    async def start_all(self) -> None:
        """
        Initialize and start all registered agents.

        Phase 1: Initialize all agents (parallel)
        Phase 2: Start all agents (parallel)
        """
        self._running = True

        # Phase 1: Initialize all agents (subscribe to topics)
        init_tasks = [agent.initialize() for agent in self._agents]
        await asyncio.gather(*init_tasks, return_exceptions=True)

        # Phase 2: Start all agents
        start_tasks = [agent.start() for agent in self._agents]
        await asyncio.gather(*start_tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        """Stop all registered agents gracefully."""
        self._running = False

        stop_tasks = [agent.stop() for agent in self._agents]
        await asyncio.gather(*stop_tasks, return_exceptions=True)

    def get_agent_by_id(self, agent_id: str) -> Optional[Agent]:
        """
        Get an agent by its ID.

        Args:
            agent_id: The agent's unique identifier

        Returns:
            The agent if found, None otherwise
        """
        for agent in self._agents:
            if agent.id == agent_id:
                return agent
        return None

    def get_agents_by_state(self, state: AgentState) -> List[Agent]:
        """
        Get all agents in a specific state.

        Args:
            state: The state to filter by

        Returns:
            List of agents in the specified state
        """
        return [agent for agent in self._agents if agent.state == state]

    @property
    def agents(self) -> List[Agent]:
        """Return a copy of the registered agents list."""
        return self._agents.copy()

    @property
    def is_running(self) -> bool:
        """Return whether the lifecycle manager is running."""
        return self._running

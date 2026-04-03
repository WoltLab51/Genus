"""
Lifecycle Manager

Coordinates the startup and shutdown of multiple agents.
"""

from typing import List, Optional
import asyncio
import logging

from .agent import Agent, AgentState

logger = logging.getLogger("genus.lifecycle")


class Lifecycle:
    """Manage the lifecycle of a set of registered agents."""

    def __init__(self) -> None:
        self._agents: List[Agent] = []
        self._running = False

    def register(self, agent: Agent) -> None:
        if agent not in self._agents:
            self._agents.append(agent)

    def unregister(self, agent: Agent) -> None:
        if agent in self._agents:
            self._agents.remove(agent)

    async def start_all(self) -> None:
        """Initialize then start every registered agent."""
        self._running = True
        for agent in self._agents:
            await agent.initialize()
        await asyncio.gather(
            *(agent.start() for agent in self._agents),
            return_exceptions=True,
        )
        logger.info("All %d agent(s) started", len(self._agents))

    async def stop_all(self) -> None:
        """Stop every registered agent."""
        self._running = False
        await asyncio.gather(
            *(agent.stop() for agent in self._agents),
            return_exceptions=True,
        )
        logger.info("All %d agent(s) stopped", len(self._agents))

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        for agent in self._agents:
            if agent.id == agent_id:
                return agent
        return None

    def get_agents_by_state(self, state: AgentState) -> List[Agent]:
        return [a for a in self._agents if a.state == state]

    @property
    def agents(self) -> List[Agent]:
        return list(self._agents)

    @property
    def is_running(self) -> bool:
        return self._running

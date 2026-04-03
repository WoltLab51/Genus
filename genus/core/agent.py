"""Core agent abstraction with lifecycle management."""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any


class AgentState(Enum):
    """Agent lifecycle states."""
    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class Agent(ABC):
    """Abstract base class for all agents in GENUS.

    Agents follow a strict lifecycle:
    1. __init__ - Inject dependencies (MessageBus, stores)
    2. initialize() - Subscribe to topics, set up handlers
    3. start() - Transition to RUNNING state
    4. stop() - Unsubscribe, clean up, transition to STOPPED

    IMPORTANT: Subscriptions must NEVER happen in __init__.
    """

    def __init__(self, agent_id: str):
        """Initialize agent with ID.

        Args:
            agent_id: Unique identifier for this agent
        """
        self.agent_id = agent_id
        self.state = AgentState.CREATED

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize agent and subscribe to topics.

        This is where topic subscriptions should be set up.
        Must be called before start().
        """
        pass

    async def start(self) -> None:
        """Start the agent and transition to RUNNING state."""
        if self.state != AgentState.INITIALIZED:
            raise RuntimeError(
                f"Agent {self.agent_id} must be initialized before starting. "
                f"Current state: {self.state}"
            )
        self.state = AgentState.RUNNING

    async def stop(self) -> None:
        """Stop the agent and clean up resources."""
        await self._cleanup()
        self.state = AgentState.STOPPED

    @abstractmethod
    async def _cleanup(self) -> None:
        """Clean up resources (unsubscribe, close connections, etc.)."""
        pass

    def get_status(self) -> Dict[str, Any]:
        """Get current agent status.

        Returns:
            Dictionary with agent status information
        """
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
        }

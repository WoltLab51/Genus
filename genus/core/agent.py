"""Base agent abstraction and lifecycle management."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict


class AgentState(Enum):
    """Agent lifecycle states."""

    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class Agent(ABC):
    """
    Abstract base class for all agents.

    Agents follow a strict lifecycle:
    1. __init__: Inject dependencies (MessageBus, stores, etc.)
    2. initialize(): Subscribe to topics and prepare for work
    3. start(): Transition to RUNNING state
    4. stop(): Unsubscribe and transition to STOPPED state

    IMPORTANT: Subscriptions must NEVER happen in __init__.
    """

    def __init__(self, name: str):
        """
        Initialize agent with a name.

        Args:
            name: Unique identifier for this agent
        """
        self.name = name
        self.state = AgentState.IDLE

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the agent.

        Subscribe to message topics and prepare for work.
        This is called after __init__ but before start().
        """
        pass

    async def start(self) -> None:
        """
        Start the agent.

        Transition to RUNNING state and begin processing.
        """
        if self.state == AgentState.IDLE:
            self.state = AgentState.RUNNING

    async def stop(self) -> None:
        """
        Stop the agent.

        Unsubscribe from topics and transition to STOPPED state.
        """
        if self.state == AgentState.RUNNING:
            self.state = AgentState.STOPPED

    def get_state(self) -> AgentState:
        """Get current agent state."""
        return self.state

    @abstractmethod
    async def handle_message(self, topic: str, message: Dict[str, Any]) -> None:
        """
        Handle a message from the message bus.

        Args:
            topic: The topic the message was published to
            message: The message data
        """
        pass

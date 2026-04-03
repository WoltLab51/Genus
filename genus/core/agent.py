"""
Agent Base Classes

Provides abstract base classes for all agents in the GENUS system.
Follows clean architecture principles with clear separation of concerns.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime
import uuid


class AgentState(Enum):
    """Defines possible states for an agent."""
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class Agent(ABC):
    """
    Abstract base class for all agents.

    Agents are autonomous entities that can:
    - Process messages
    - Maintain their own state
    - Communicate with other agents via the message bus
    - Execute tasks independently

    This class enforces the Interface Segregation Principle by providing
    only the essential methods that all agents must implement.
    """

    def __init__(self, agent_id: Optional[str] = None, name: Optional[str] = None):
        """
        Initialize the agent.

        Args:
            agent_id: Unique identifier for the agent. Auto-generated if not provided.
            name: Human-readable name for the agent.
        """
        self._id = agent_id or str(uuid.uuid4())
        self._name = name or self.__class__.__name__
        self._state = AgentState.INITIALIZED
        self._created_at = datetime.utcnow()
        self._metadata: Dict[str, Any] = {}

    @property
    def id(self) -> str:
        """Return the agent's unique identifier."""
        return self._id

    @property
    def name(self) -> str:
        """Return the agent's name."""
        return self._name

    @property
    def state(self) -> AgentState:
        """Return the current state of the agent."""
        return self._state

    @property
    def metadata(self) -> Dict[str, Any]:
        """Return the agent's metadata."""
        return self._metadata.copy()

    def set_metadata(self, key: str, value: Any) -> None:
        """
        Set a metadata key-value pair.

        Args:
            key: Metadata key
            value: Metadata value
        """
        self._metadata[key] = value

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the agent's resources.

        This method should set up any resources the agent needs to operate.
        Must be called before start().
        """
        pass

    @abstractmethod
    async def start(self) -> None:
        """
        Start the agent's main execution loop.

        Transitions the agent from INITIALIZED to RUNNING state.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the agent gracefully.

        Should clean up resources and transition to STOPPED state.
        """
        pass

    @abstractmethod
    async def process_message(self, message: Any) -> None:
        """
        Process an incoming message.

        Args:
            message: The message to process
        """
        pass

    def _transition_state(self, new_state: AgentState) -> None:
        """
        Transition to a new state.

        Args:
            new_state: The state to transition to
        """
        old_state = self._state
        self._state = new_state
        self._on_state_changed(old_state, new_state)

    def _on_state_changed(self, old_state: AgentState, new_state: AgentState) -> None:
        """
        Hook called when state changes.

        Args:
            old_state: The previous state
            new_state: The new state
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self._id}, name={self._name}, state={self._state.value})"

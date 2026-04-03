"""Agent Base Classes - Clean architecture with explicit lifecycle."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import uuid


class AgentState(Enum):
    """Defines possible states for an agent."""
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class Agent(ABC):
    """
    Abstract base class for all GENUS agents.

    Agents are autonomous entities that:
    - Process messages via pub-sub communication
    - Maintain explicit state machines
    - Follow strict lifecycle: __init__ → initialize() → start() → stop()
    - Never communicate directly with other agents

    Design Principles:
    - Dependency Injection: All dependencies passed via constructor
    - Single Responsibility: One agent, one purpose
    - Interface Segregation: Minimal required methods
    """

    def __init__(self, agent_id: Optional[str] = None, name: Optional[str] = None):
        """
        Initialize the agent (NO subscriptions here).

        Args:
            agent_id: Unique identifier. Auto-generated if not provided.
            name: Human-readable name. Defaults to class name.
        """
        self._id = agent_id or str(uuid.uuid4())
        self._name = name or self.__class__.__name__
        self._state = AgentState.INITIALIZED
        self._created_at = datetime.now(timezone.utc)
        self._last_active: Optional[datetime] = None
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
    def last_active(self) -> Optional[datetime]:
        """Return the last activity timestamp."""
        return self._last_active

    @property
    def metadata(self) -> Dict[str, Any]:
        """Return a copy of the agent's metadata."""
        return self._metadata.copy()

    def set_metadata(self, key: str, value: Any) -> None:
        """Set a metadata key-value pair."""
        self._metadata[key] = value

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize agent resources and subscribe to topics.

        CRITICAL: All message bus subscriptions MUST happen here, NOT in __init__.
        This ensures proper dependency injection and testability.
        """
        pass

    @abstractmethod
    async def start(self) -> None:
        """
        Start the agent's execution.

        Transitions from INITIALIZED to RUNNING state.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the agent gracefully.

        Should unsubscribe from topics, clean up resources, and transition to STOPPED.
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
        Hook called when state changes (override for custom behavior).

        Args:
            old_state: The previous state
            new_state: The new state
        """
        pass

    def _update_last_active(self) -> None:
        """Update the last active timestamp."""
        self._last_active = datetime.now(timezone.utc)

    def get_status(self) -> Dict[str, Any]:
        """
        Get agent status for API/monitoring.

        Returns:
            Status dictionary with id, name, state, last_active
        """
        return {
            "agent_id": self.id,
            "name": self.name,
            "state": self.state.value,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self._id}, name={self._name}, state={self._state.value})"

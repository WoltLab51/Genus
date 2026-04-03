"""
Agent Base Class

Provides the abstract base class for all agents in the GENUS system.
Agents follow a clear lifecycle (initialize → start → stop) and receive
dependencies via constructor injection — no global singletons.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import uuid
import logging


class AgentState(Enum):
    """Possible states for an agent."""

    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class Agent(ABC):
    """
    Abstract base class for all GENUS agents.

    Lifecycle:
        1. ``__init__`` — constructor, receives injected dependencies.
        2. ``initialize()`` — set up subscriptions and resources.
        3. ``start()`` — begin processing; transitions state to RUNNING.
        4. ``stop()`` — clean up; transitions state to STOPPED.

    Agents must **not** subscribe to the message bus inside ``__init__``.
    Use ``initialize()`` instead so that wiring is explicit and testable.
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        self._id = agent_id or str(uuid.uuid4())
        self._name = name or self.__class__.__name__
        self._state = AgentState.INITIALIZED
        self._created_at = datetime.now(timezone.utc)
        self._metadata: Dict[str, Any] = {}
        self._logger = logging.getLogger(f"genus.agent.{self._id}")

    # -- read-only properties --------------------------------------------------

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def metadata(self) -> Dict[str, Any]:
        return self._metadata.copy()

    # -- public helpers --------------------------------------------------------

    def set_metadata(self, key: str, value: Any) -> None:
        self._metadata[key] = value

    def get_status(self) -> Dict[str, Any]:
        return {
            "agent_id": self._id,
            "name": self._name,
            "state": self._state.value,
            "created_at": self._created_at.isoformat(),
        }

    # -- lifecycle -------------------------------------------------------------

    @abstractmethod
    async def initialize(self) -> None:
        """Set up subscriptions and external resources.

        Called once before ``start()``.  This is the place to call
        ``message_bus.subscribe(...)`` — never do that in ``__init__``.
        """

    @abstractmethod
    async def start(self) -> None:
        """Begin processing.  Transition to RUNNING."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down.  Transition to STOPPED."""

    @abstractmethod
    async def execute(self, payload: Any = None) -> Any:
        """Run the agent's core logic with an optional *payload*."""

    # -- state management ------------------------------------------------------

    def _transition_state(self, new_state: AgentState) -> None:
        old = self._state
        self._state = new_state
        self._logger.debug("state %s → %s", old.value, new_state.value)

    # -- dunder ----------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f"(id={self._id!r}, name={self._name!r}, state={self._state.value!r})"
        )

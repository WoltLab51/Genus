"""Agent base class and lifecycle management."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime


class AgentState(Enum):
    """Agent lifecycle states."""
    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class Agent(ABC):
    """Base class for all GENUS agents.

    Agents follow a strict lifecycle:
    1. __init__ - inject dependencies
    2. initialize() - subscribe to topics
    3. start() - transition to RUNNING
    4. stop() - unsubscribe, transition to STOPPED

    Subscriptions must NEVER happen in __init__.
    """

    def __init__(self, name: str):
        """Initialize agent with name.

        Args:
            name: Unique identifier for this agent
        """
        self.name = name
        self.state = AgentState.CREATED
        self.last_error: Optional[str] = None
        self.last_success: Optional[datetime] = None
        self.error_count: int = 0
        self.execution_count: int = 0

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize agent and subscribe to topics.

        This is where agents should set up their message bus subscriptions.
        Must be called before start().
        """
        pass

    async def start(self) -> None:
        """Start the agent and transition to RUNNING state."""
        if self.state != AgentState.INITIALIZED:
            raise RuntimeError(f"Agent must be initialized before starting. Current state: {self.state}")
        self.state = AgentState.RUNNING

    async def stop(self) -> None:
        """Stop the agent and unsubscribe from topics."""
        self.state = AgentState.STOPPED

    def get_status(self) -> Dict[str, Any]:
        """Get current agent status for health monitoring.

        Returns:
            Dict containing agent state, error info, and execution metrics
        """
        return {
            "name": self.name,
            "state": self.state.value,
            "error_count": self.error_count,
            "execution_count": self.execution_count,
            "last_error": self.last_error,
            "last_success": self.last_success.isoformat() if self.last_success else None,
        }

    def record_success(self) -> None:
        """Record successful execution."""
        self.execution_count += 1
        self.last_success = datetime.utcnow()

    def record_error(self, error: str) -> None:
        """Record execution error.

        Args:
            error: Error message or description
        """
        self.error_count += 1
        self.last_error = error
        if self.error_count >= 10:  # Threshold for failed state
            self.state = AgentState.FAILED

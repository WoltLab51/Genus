"""
Core Agent abstraction for GENUS system.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict


class AgentState(Enum):
    """Agent lifecycle states."""
    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"


class Agent(ABC):
    """
    Base Agent class following strict lifecycle:
    __init__ -> initialize() -> start() -> stop()

    Subscriptions must NEVER happen in __init__.
    """

    def __init__(self, name: str):
        """
        Initialize agent with name. Dependencies should be injected here.
        DO NOT subscribe to topics here.
        """
        self.name = name
        self.state = AgentState.CREATED

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize agent and subscribe to topics.
        Called after __init__ but before start().
        """
        self.state = AgentState.INITIALIZED

    @abstractmethod
    async def start(self) -> None:
        """
        Start agent execution.
        Transition to RUNNING state.
        """
        if self.state != AgentState.INITIALIZED:
            raise RuntimeError(f"Cannot start agent in state {self.state}")
        self.state = AgentState.RUNNING

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop agent execution and unsubscribe from topics.
        Transition to STOPPED state.
        """
        self.state = AgentState.STOPPED

    def is_running(self) -> bool:
        """Check if agent is running."""
        return self.state == AgentState.RUNNING

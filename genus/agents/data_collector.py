"""
DataCollector Agent Implementation

Simple agent that collects and publishes mock data.
"""

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message, MessagePriority
from genus.utils.logger import get_logger
from typing import Optional
import asyncio


class DataCollectorAgent(Agent):
    """
    DataCollector agent that generates and publishes mock data.

    Demonstrates:
    - Data collection
    - Publishing data messages
    - Simple data generation
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        message_bus: Optional[MessageBus] = None
    ):
        """
        Initialize the data collector agent.

        Args:
            agent_id: Unique identifier for the agent
            name: Human-readable name
            message_bus: Message bus for communication
        """
        super().__init__(agent_id, name)
        self._message_bus = message_bus
        self._logger = get_logger(f"{self.__class__.__name__}.{self.id}")
        self._running = False
        self._data_count = 0

    async def initialize(self) -> None:
        """Initialize the data collector agent."""
        self._logger.info(f"Initializing {self.name}")
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Start the data collector agent."""
        self._logger.info(f"Starting {self.name}")
        self._running = True
        self._transition_state(AgentState.RUNNING)

        # Collect and publish data
        await self._collect_data()

    async def stop(self) -> None:
        """Stop the data collector agent."""
        self._logger.info(f"Stopping {self.name}")
        self._running = False

        if self._message_bus:
            self._message_bus.unsubscribe_all(self.id)

        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message: Message) -> None:
        """
        Process an incoming message.

        Args:
            message: The message to process
        """
        self._logger.info(f"DataCollector received message: {message.topic}")

    async def _collect_data(self) -> None:
        """Collect and publish mock data."""
        if not self._message_bus:
            self._logger.warning("No message bus configured")
            return

        # Generate mock data
        mock_data = {
            "temperature": 23.5,
            "humidity": 65.0,
            "pressure": 1013.25,
            "timestamp": "2026-04-04T09:38:00Z"
        }

        self._data_count += 1
        self._logger.info(f"Collecting data #{self._data_count}: {mock_data}")

        # Publish data.collected message
        message = Message(
            topic="data.collected",
            payload=mock_data,
            sender_id=self.id,
            priority=MessagePriority.NORMAL,
        )

        await self._message_bus.publish(message)
        self._logger.info(f"Published data.collected message")

    def get_stats(self) -> dict:
        """
        Get data collector statistics.

        Returns:
            Dictionary of statistics
        """
        return {
            "data_count": self._data_count,
            "state": self.state.value,
        }

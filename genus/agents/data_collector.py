"""
Data Collector Agent - collects and processes incoming data.
"""
from genus.core.agent import Agent
from genus.communication.message_bus import MessageBus, Message
from typing import Any
import logging

logger = logging.getLogger(__name__)


class DataCollectorAgent(Agent):
    """Agent responsible for collecting data and publishing to analysis."""

    def __init__(self, name: str, message_bus: MessageBus):
        super().__init__(name)
        self.message_bus = message_bus
        self._callbacks = []

    async def initialize(self) -> None:
        """Initialize and subscribe to data input topics."""
        await super().initialize()
        # Subscribe to data input
        callback = self._handle_data_input
        self.message_bus.subscribe("data.input", callback)
        self._callbacks.append(("data.input", callback))
        logger.info(f"{self.name} initialized and subscribed to 'data.input'")

    async def start(self) -> None:
        """Start the agent."""
        await super().start()
        logger.info(f"{self.name} started")

    async def stop(self) -> None:
        """Stop the agent and unsubscribe."""
        for topic, callback in self._callbacks:
            self.message_bus.unsubscribe(topic, callback)
        await super().stop()
        logger.info(f"{self.name} stopped")

    async def _handle_data_input(self, message: Message) -> None:
        """Handle incoming data."""
        logger.info(f"{self.name} received data: {message.data}")

        # Process and publish to analysis
        processed_data = {
            "raw_data": message.data,
            "source": message.sender,
            "status": "processed",
        }

        await self.message_bus.publish(
            "data.processed", processed_data, sender=self.name
        )
        logger.debug(f"{self.name} published processed data to 'data.processed'")

    async def collect_data(self, data: Any) -> None:
        """Public method to collect data."""
        await self.message_bus.publish("data.input", data, sender=self.name)

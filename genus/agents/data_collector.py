"""Data collection agent."""

import logging
from typing import Any, Dict

from genus.core.agent import Agent
from genus.communication.message_bus import MessageBus
from genus.storage.memory_store import MemoryStore

logger = logging.getLogger(__name__)


class DataCollectorAgent(Agent):
    """
    Agent responsible for collecting and storing data.

    Subscribes to data collection topics and stores observations
    in the memory store.
    """

    def __init__(self, message_bus: MessageBus, memory_store: MemoryStore):
        """
        Initialize the data collector agent.

        Args:
            message_bus: Message bus for communication
            memory_store: Store for persisting collected data
        """
        super().__init__("DataCollector")
        self._message_bus = message_bus
        self._memory_store = memory_store

    async def initialize(self) -> None:
        """Subscribe to data collection topics."""
        self._message_bus.subscribe("data.collect", self.handle_message)
        logger.info(f"Agent {self.name} initialized and subscribed to topics")

    async def stop(self) -> None:
        """Unsubscribe from topics and stop."""
        self._message_bus.unsubscribe("data.collect", self.handle_message)
        await super().stop()
        logger.info(f"Agent {self.name} stopped")

    async def handle_message(self, topic: str, message: Dict[str, Any]) -> None:
        """
        Handle incoming data collection messages.

        Args:
            topic: The topic the message was published to
            message: The message data
        """
        logger.debug(f"Agent {self.name} handling message from topic {topic}")

        # Store the data in memory
        memory_id = await self._memory_store.store(message)

        # Notify that data has been collected
        await self._message_bus.publish("data.collected", {
            "memory_id": memory_id,
            "source": message.get("source", "unknown"),
            "data": message
        })

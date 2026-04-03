"""Data collection agent."""

from typing import Any
from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message
from genus.storage.memory_store import MemoryStore


class DataCollectorAgent(Agent):
    """Agent responsible for collecting and preprocessing data.

    Subscribes to: data.raw
    Publishes to: data.processed
    """

    def __init__(self, message_bus: MessageBus, memory_store: MemoryStore):
        """Initialize the data collector agent.

        Args:
            message_bus: MessageBus for communication
            memory_store: MemoryStore for data persistence
        """
        super().__init__("data_collector")
        self.message_bus = message_bus
        self.memory_store = memory_store

    async def initialize(self) -> None:
        """Initialize and subscribe to topics."""
        self.message_bus.subscribe("data.raw", self._handle_raw_data)
        self.state = AgentState.INITIALIZED

    async def stop(self) -> None:
        """Stop and unsubscribe from topics."""
        self.message_bus.unsubscribe("data.raw", self._handle_raw_data)
        await super().stop()

    async def _handle_raw_data(self, message: Message) -> None:
        """Process raw data messages.

        Args:
            message: Raw data message
        """
        try:
            # Simulate data processing
            raw_data = message.data
            processed_data = {
                "original": raw_data,
                "processed": True,
                "source": self.name,
            }

            # Store in memory
            await self.memory_store.store(
                f"processed_data_{message.timestamp.timestamp()}",
                processed_data
            )

            # Publish processed data
            await self.message_bus.publish(
                "data.processed",
                processed_data,
                source=self.name
            )

            # Record success
            self.record_success()

        except Exception as e:
            # Record error
            error_msg = f"Failed to process data: {str(e)}"
            self.record_error(error_msg)
            raise

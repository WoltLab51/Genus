"""Analysis agent."""

from typing import Any
from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message
from genus.storage.memory_store import MemoryStore


class AnalysisAgent(Agent):
    """Agent responsible for analyzing processed data.

    Subscribes to: data.processed
    Publishes to: analysis.complete
    """

    def __init__(self, message_bus: MessageBus, memory_store: MemoryStore):
        """Initialize the analysis agent.

        Args:
            message_bus: MessageBus for communication
            memory_store: MemoryStore for data access
        """
        super().__init__("analysis")
        self.message_bus = message_bus
        self.memory_store = memory_store

    async def initialize(self) -> None:
        """Initialize and subscribe to topics."""
        self.message_bus.subscribe("data.processed", self._handle_processed_data)
        self.state = AgentState.INITIALIZED

    async def stop(self) -> None:
        """Stop and unsubscribe from topics."""
        self.message_bus.unsubscribe("data.processed", self._handle_processed_data)
        await super().stop()

    async def _handle_processed_data(self, message: Message) -> None:
        """Analyze processed data.

        Args:
            message: Processed data message
        """
        try:
            # Simulate analysis
            data = message.data
            analysis_result = {
                "data": data,
                "insights": ["insight_1", "insight_2"],
                "confidence": 0.85,
                "analyzer": self.name,
            }

            # Store analysis result
            await self.memory_store.store(
                f"analysis_{message.timestamp.timestamp()}",
                analysis_result
            )

            # Publish analysis result
            await self.message_bus.publish(
                "analysis.complete",
                analysis_result,
                source=self.name
            )

            # Record success
            self.record_success()

        except Exception as e:
            # Record error
            error_msg = f"Failed to analyze data: {str(e)}"
            self.record_error(error_msg)
            raise

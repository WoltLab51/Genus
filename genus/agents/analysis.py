"""
Analysis Agent - analyzes data and generates insights.
"""
from genus.core.agent import Agent
from genus.communication.message_bus import MessageBus, Message
from genus.storage.stores import MemoryStore
import logging

logger = logging.getLogger(__name__)


class AnalysisAgent(Agent):
    """Agent responsible for analyzing data."""

    def __init__(self, name: str, message_bus: MessageBus, memory_store: MemoryStore):
        super().__init__(name)
        self.message_bus = message_bus
        self.memory_store = memory_store
        self._callbacks = []

    async def initialize(self) -> None:
        """Initialize and subscribe to processed data."""
        await super().initialize()
        callback = self._handle_processed_data
        self.message_bus.subscribe("data.processed", callback)
        self._callbacks.append(("data.processed", callback))
        logger.info(f"{self.name} initialized and subscribed to 'data.processed'")

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

    async def _handle_processed_data(self, message: Message) -> None:
        """Handle processed data and perform analysis."""
        logger.info(f"{self.name} analyzing data from {message.sender}")

        data = message.data
        # Simple analysis: extract insights from data
        analysis_result = {
            "data": data,
            "insights": f"Analyzed data from {data.get('source')}",
            "needs_decision": True,
            "context": f"Data analysis for {data.get('raw_data')}",
        }

        # Store analysis in memory
        await self.memory_store.set(f"analysis_{message.timestamp}", analysis_result)

        # Publish to decision topic
        await self.message_bus.publish(
            "analysis.complete", analysis_result, sender=self.name
        )
        logger.debug(f"{self.name} published analysis to 'analysis.complete'")

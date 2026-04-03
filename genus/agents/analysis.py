"""Analysis Agent - Processes and interprets collected data."""

import logging
from typing import Any, Dict, List, Optional

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message, MessagePriority
from genus.storage.memory import MemoryStore
from genus.storage.models import DataItem, AnalysisResult


class AnalysisAgent(Agent):
    """
    Analyzes collected data and extracts insights.

    Responsibilities:
    - Subscribe to 'data.collected' events
    - Process data items and extract insights
    - Calculate confidence scores
    - Publish 'data.analyzed' events

    Clean Architecture:
    - Listens to MessageBus, never calls other agents directly
    - Subscriptions in initialize()
    - All state stored in injected MemoryStore
    """

    def __init__(
        self,
        message_bus: MessageBus,
        memory_store: MemoryStore,
        agent_id: str = "analysis",
        name: str = "Analysis Agent"
    ):
        """
        Initialize the Analysis agent.

        Args:
            message_bus: Message bus for communication
            memory_store: Memory store for state
            agent_id: Unique identifier
            name: Human-readable name
        """
        super().__init__(agent_id, name)
        self._message_bus = message_bus
        self._memory_store = memory_store
        self._logger = logging.getLogger(f"genus.agent.{self.id}")
        self._results: List[AnalysisResult] = []

    async def initialize(self) -> None:
        """Initialize agent and subscribe to topics."""
        self._logger.info(f"Initializing {self.name}")

        # CRITICAL: Subscribe to 'data.collected' events
        # This happens in initialize(), NOT __init__
        self._message_bus.subscribe(
            topic="data.collected",
            subscriber_id=self.id,
            callback=self._on_data_collected
        )
        self._logger.info("Subscribed to 'data.collected' topic")

        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Start the agent."""
        self._logger.info(f"Starting {self.name}")
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        """Stop the agent."""
        self._logger.info(f"Stopping {self.name}")
        self._message_bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    async def _on_data_collected(self, message: Message) -> None:
        """
        Handle data.collected events.

        Args:
            message: Message containing collected data
        """
        self._logger.info(f"Received data.collected event from {message.sender_id}")
        items_raw = message.payload.get("items", [])
        if items_raw:
            items = [DataItem(**i) for i in items_raw]
            await self.analyze(items)

    async def analyze(self, items: List[DataItem]) -> AnalysisResult:
        """
        Analyze data items.

        Args:
            items: List of data items to analyze

        Returns:
            Analysis result
        """
        self._update_last_active()

        if not items:
            summary = "No data available for analysis."
            insights = []
            confidence = 0.0
        else:
            summary = f"Analyzed {len(items)} data item(s) from sources: {', '.join(set(i.source for i in items))}."
            insights = self._extract_insights(items)
            # Simple confidence calculation
            confidence = min(0.5 + len(items) * 0.1, 0.95)

        result = AnalysisResult(
            input_data={"item_count": len(items)},
            summary=summary,
            insights=insights,
            confidence=confidence,
        )

        self._results.append(result)

        # Store in memory
        self._memory_store.set(self.id, "last_result", result.model_dump())

        # Publish event for downstream agents
        message = Message(
            topic="data.analyzed",
            payload={"result": result.model_dump()},
            sender_id=self.id,
            priority=MessagePriority.NORMAL,
        )
        await self._message_bus.publish(message)

        self._logger.info(f"Analysis complete: {len(insights)} insights, confidence={confidence:.2f}")
        return result

    def _extract_insights(self, items: List[DataItem]) -> List[str]:
        """
        Extract insights from data items.

        Args:
            items: Data items to process

        Returns:
            List of insight strings
        """
        insights = []
        for item in items:
            content = item.content
            if isinstance(content, dict):
                for k, v in content.items():
                    insights.append(f"Key '{k}' has value: {v}")
            else:
                insights.append(f"Data from '{item.source}': {str(content)[:100]}")
        return insights[:10]  # Limit to 10 insights

    def get_results(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent analysis results.

        Args:
            limit: Maximum number of results to return

        Returns:
            List of results as dictionaries
        """
        return [r.model_dump() for r in self._results[-limit:]]

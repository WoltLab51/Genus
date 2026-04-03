"""Decision-making agent."""

import logging
from typing import Any, Dict

from genus.core.agent import Agent
from genus.communication.message_bus import MessageBus
from genus.storage.decision_store import DecisionStore

logger = logging.getLogger(__name__)


class DecisionAgent(Agent):
    """
    Agent responsible for making decisions based on analysis.

    Subscribes to analysis results and makes decisions,
    storing them for future reference.
    """

    def __init__(self, message_bus: MessageBus, decision_store: DecisionStore):
        """
        Initialize the decision agent.

        Args:
            message_bus: Message bus for communication
            decision_store: Store for persisting decisions
        """
        super().__init__("Decision")
        self._message_bus = message_bus
        self._decision_store = decision_store

    async def initialize(self) -> None:
        """Subscribe to analysis topics."""
        self._message_bus.subscribe("analysis.complete", self.handle_message)
        logger.info(f"Agent {self.name} initialized and subscribed to topics")

    async def stop(self) -> None:
        """Unsubscribe from topics and stop."""
        self._message_bus.unsubscribe("analysis.complete", self.handle_message)
        await super().stop()
        logger.info(f"Agent {self.name} stopped")

    async def handle_message(self, topic: str, message: Dict[str, Any]) -> None:
        """
        Handle incoming analysis messages and make decisions.

        Args:
            topic: The topic the message was published to
            message: The message data
        """
        logger.debug(f"Agent {self.name} handling message from topic {topic}")

        # Make a decision based on analysis
        analysis = message.get("analysis", {})
        decision = f"Process {analysis.get('data_type', 'data')} from {message.get('source', 'unknown')}"

        # Store the decision
        decision_id = await self._decision_store.store_decision(
            agent=self.name,
            decision=decision,
            context=message,
            reasoning="Based on automated analysis of incoming data"
        )

        # Publish decision
        await self._message_bus.publish("decision.made", {
            "decision_id": decision_id,
            "decision": decision,
            "context": message
        })

"""Decision-making agent."""

from typing import Any
from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message
from genus.storage.decision_store import DecisionStore
import uuid


class DecisionAgent(Agent):
    """Agent responsible for making decisions based on analysis.

    Subscribes to: analysis.complete
    Publishes to: decision.made
    """

    def __init__(self, message_bus: MessageBus, decision_store: DecisionStore):
        """Initialize the decision agent.

        Args:
            message_bus: MessageBus for communication
            decision_store: DecisionStore for decision tracking
        """
        super().__init__("decision")
        self.message_bus = message_bus
        self.decision_store = decision_store

    async def initialize(self) -> None:
        """Initialize and subscribe to topics."""
        self.message_bus.subscribe("analysis.complete", self._handle_analysis)
        self.state = AgentState.INITIALIZED

    async def stop(self) -> None:
        """Stop and unsubscribe from topics."""
        self.message_bus.unsubscribe("analysis.complete", self._handle_analysis)
        await super().stop()

    async def _handle_analysis(self, message: Message) -> None:
        """Make decisions based on analysis.

        Args:
            message: Analysis result message
        """
        try:
            # Simulate decision making
            analysis = message.data
            decision_id = str(uuid.uuid4())

            decision_data = {
                "action": "approve" if analysis.get("confidence", 0) > 0.8 else "review",
                "reasoning": f"Based on {len(analysis.get('insights', []))} insights",
                "analysis": analysis,
            }

            # Record decision
            await self.decision_store.record_decision(
                decision_id=decision_id,
                agent=self.name,
                decision_type="approval",
                data=decision_data
            )

            # Publish decision
            await self.message_bus.publish(
                "decision.made",
                {"decision_id": decision_id, **decision_data},
                source=self.name
            )

            # Record success
            self.record_success()

        except Exception as e:
            # Record error
            error_msg = f"Failed to make decision: {str(e)}"
            self.record_error(error_msg)
            raise

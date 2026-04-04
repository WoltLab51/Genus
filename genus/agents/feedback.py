"""
Feedback Agent Implementation

Simple agent that simulates feedback for decisions.
"""

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message, MessagePriority
from genus.utils.logger import get_logger
from typing import Optional
import random


class FeedbackAgent(Agent):
    """
    Feedback agent that simulates feedback for decisions.

    Demonstrates:
    - Subscribing to decision topics
    - Generating simulated feedback
    - Publishing feedback messages
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        message_bus: Optional[MessageBus] = None,
        success_rate: float = 0.7
    ):
        """
        Initialize the feedback agent.

        Args:
            agent_id: Unique identifier for the agent
            name: Human-readable name
            message_bus: Message bus for communication
            success_rate: Probability of success feedback (0.0 to 1.0)
        """
        super().__init__(agent_id, name)
        self._message_bus = message_bus
        self._logger = get_logger(f"{self.__class__.__name__}.{self.id}")
        self._running = False
        self._feedback_count = 0
        self._success_rate = success_rate

    async def initialize(self) -> None:
        """Initialize the feedback agent."""
        self._logger.info(f"Initializing {self.name}")

        if self._message_bus:
            # Subscribe to decision.made topic
            self._message_bus.subscribe(
                "decision.made",
                self.id,
                self.process_message
            )
            self._logger.info(f"Subscribed to 'decision.made'")

        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Start the feedback agent."""
        self._logger.info(f"Starting {self.name}")
        self._running = True
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        """Stop the feedback agent."""
        self._logger.info(f"Stopping {self.name}")
        self._running = False

        if self._message_bus:
            self._message_bus.unsubscribe_all(self.id)

        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message: Message) -> None:
        """
        Process a decision message and generate feedback.

        Args:
            message: The decision message to process
        """
        decision = message.payload
        decision_id = decision.get("decision_id")
        action = decision.get("action")

        self._logger.info(f"Generating feedback for decision {decision_id[:8]}... (action: {action})")

        # Simulate feedback based on action
        outcome = self._simulate_feedback(action)

        feedback = {
            "decision_id": decision_id,
            "outcome": outcome,
            "feedback_by": self.id
        }

        self._feedback_count += 1
        self._logger.info(f"Feedback #{self._feedback_count}: decision {decision_id[:8]}... -> {outcome}")

        # Publish feedback
        if self._message_bus:
            feedback_message = Message(
                topic="decision.feedback",
                payload=feedback,
                sender_id=self.id,
                priority=MessagePriority.NORMAL,
            )
            await self._message_bus.publish(feedback_message)
            self._logger.info(f"Published decision.feedback message")

    def _simulate_feedback(self, action: str) -> str:
        """
        Simulate feedback outcome based on action.

        Args:
            action: The action that was taken

        Returns:
            Outcome: 'success' or 'failure'
        """
        # Simple rule-based + random simulation
        # Actions that maintain settings have higher success rate
        if action == "maintain_current_settings":
            success_probability = 0.9
        else:
            success_probability = self._success_rate

        # Random outcome based on probability
        if random.random() < success_probability:
            return "success"
        else:
            return "failure"

    def get_stats(self) -> dict:
        """
        Get feedback agent statistics.

        Returns:
            Dictionary of statistics
        """
        return {
            "feedback_count": self._feedback_count,
            "state": self.state.value,
            "success_rate": self._success_rate,
        }

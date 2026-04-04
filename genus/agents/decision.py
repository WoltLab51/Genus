"""
Decision Agent Implementation

Simple agent that makes decisions based on analyzed data.
"""

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message, MessagePriority
from genus.utils.logger import get_logger
from typing import Optional, Dict
import uuid


class DecisionAgent(Agent):
    """
    Decision agent that makes simple decisions based on analyzed data.

    Demonstrates:
    - Subscribing to analysis topics
    - Making decisions
    - Publishing decision results
    - Tracking decisions and feedback
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        message_bus: Optional[MessageBus] = None
    ):
        """
        Initialize the decision agent.

        Args:
            agent_id: Unique identifier for the agent
            name: Human-readable name
            message_bus: Message bus for communication
        """
        super().__init__(agent_id, name)
        self._message_bus = message_bus
        self._logger = get_logger(f"{self.__class__.__name__}.{self.id}")
        self._running = False
        self._decision_count = 0
        self._decisions: Dict[str, dict] = {}  # decision_id -> decision data
        self._feedback: Dict[str, dict] = {}  # decision_id -> feedback data

    async def initialize(self) -> None:
        """Initialize the decision agent."""
        self._logger.info(f"Initializing {self.name}")

        if self._message_bus:
            # Subscribe to data.analyzed topic
            self._message_bus.subscribe(
                "data.analyzed",
                self.id,
                self.process_message
            )
            self._logger.info(f"Subscribed to 'data.analyzed'")

            # Subscribe to decision.feedback topic
            self._message_bus.subscribe(
                "decision.feedback",
                self.id,
                self.process_feedback
            )
            self._logger.info(f"Subscribed to 'decision.feedback'")

        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Start the decision agent."""
        self._logger.info(f"Starting {self.name}")
        self._running = True
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        """Stop the decision agent."""
        self._logger.info(f"Stopping {self.name}")
        self._running = False

        if self._message_bus:
            self._message_bus.unsubscribe_all(self.id)

        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message: Message) -> None:
        """
        Process an analyzed data message and make a decision.

        Args:
            message: The message to process
        """
        self._logger.info(f"Making decision based on analysis from {message.sender_id}")

        # Extract analysis from payload
        analysis = message.payload.get("analysis", {})

        # Generate unique decision ID
        decision_id = str(uuid.uuid4())

        # Make a simple decision based on the analysis
        decision = {
            "decision_id": decision_id,
            "analysis_summary": analysis.get("summary"),
            "temperature_status": analysis.get("temperature_status"),
            "humidity_status": analysis.get("humidity_status"),
            "action": self._determine_action(analysis),
            "decided_by": self.id
        }

        self._decision_count += 1
        self._decisions[decision_id] = decision
        self._logger.info(f"Decision #{self._decision_count} (ID: {decision_id[:8]}...) made: {decision['action']}")

        # Publish decision
        if self._message_bus:
            decision_message = Message(
                topic="decision.made",
                payload=decision,
                sender_id=self.id,
                priority=MessagePriority.NORMAL,
            )
            await self._message_bus.publish(decision_message)
            self._logger.info(f"Published decision.made message")

    def _determine_action(self, analysis: dict) -> str:
        """
        Determine action based on analysis.

        Args:
            analysis: The analysis data

        Returns:
            Action to take
        """
        temp_status = analysis.get("temperature_status", "unknown")
        humidity_status = analysis.get("humidity_status", "unknown")

        if temp_status == "cold":
            return "increase_heating"
        elif temp_status == "warm":
            return "increase_cooling"
        elif humidity_status == "dry":
            return "increase_humidifier"
        elif humidity_status == "humid":
            return "increase_dehumidifier"
        else:
            return "maintain_current_settings"

    async def process_feedback(self, message: Message) -> None:
        """
        Process feedback for a decision.

        Args:
            message: The feedback message
        """
        feedback_data = message.payload
        decision_id = feedback_data.get("decision_id")
        outcome = feedback_data.get("outcome")

        if decision_id in self._decisions:
            self._feedback[decision_id] = feedback_data
            decision = self._decisions[decision_id]
            self._logger.info(
                f"Received feedback for decision {decision_id[:8]}...: "
                f"action='{decision['action']}', outcome='{outcome}'"
            )
        else:
            self._logger.warning(f"Received feedback for unknown decision {decision_id}")

    def get_stats(self) -> dict:
        """
        Get decision agent statistics.

        Returns:
            Dictionary of statistics
        """
        # Get last decision
        last_decision = None
        if self._decisions:
            last_decision_id = list(self._decisions.keys())[-1]
            last_decision = self._decisions[last_decision_id].copy()
            # Add feedback if available
            if last_decision_id in self._feedback:
                last_decision["feedback"] = self._feedback[last_decision_id]

        return {
            "decision_count": self._decision_count,
            "feedback_count": len(self._feedback),
            "state": self.state.value,
            "last_decision": last_decision,
        }

    def get_decisions_with_feedback(self) -> list:
        """
        Get all decisions with their feedback.

        Returns:
            List of decisions with feedback
        """
        result = []
        for decision_id, decision in self._decisions.items():
            entry = decision.copy()
            if decision_id in self._feedback:
                entry["feedback"] = self._feedback[decision_id]
            else:
                entry["feedback"] = None
            result.append(entry)
        return result

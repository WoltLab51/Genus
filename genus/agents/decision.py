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
        self._action_stats: Dict[str, Dict[str, int]] = {}  # action -> {success: n, failure: n}

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
        Determine action based on analysis and past feedback.

        Args:
            analysis: The analysis data

        Returns:
            Action to take
        """
        temp_status = analysis.get("temperature_status", "unknown")
        humidity_status = analysis.get("humidity_status", "unknown")

        # Determine candidate actions based on current conditions
        candidate_actions = []

        if temp_status == "cold":
            candidate_actions.append("increase_heating")
        elif temp_status == "warm":
            candidate_actions.append("increase_cooling")

        if humidity_status == "dry":
            candidate_actions.append("increase_humidifier")
        elif humidity_status == "humid":
            candidate_actions.append("increase_dehumidifier")

        # Always consider maintaining current settings as an option
        candidate_actions.append("maintain_current_settings")

        # If we have feedback history, use it to select the best action
        if self._action_stats:
            selected_action = self._select_action_by_success_rate(candidate_actions)
            return selected_action
        else:
            # No feedback yet, use default logic (first candidate)
            return candidate_actions[0]

    def _select_action_by_success_rate(self, candidate_actions: list) -> str:
        """
        Select the best action from candidates based on success rates.

        Args:
            candidate_actions: List of possible actions

        Returns:
            Selected action
        """
        best_action = None
        best_score = -1
        feedback_influenced = False

        for action in candidate_actions:
            if action in self._action_stats:
                stats = self._action_stats[action]
                total = stats["success"] + stats["failure"]
                if total > 0:
                    # Success rate with a slight bonus for more data (confidence)
                    success_rate = stats["success"] / total
                    # Add small confidence bonus (up to 0.1) for more samples
                    confidence_bonus = min(0.1, total / 100)
                    score = success_rate + confidence_bonus
                    feedback_influenced = True
                else:
                    score = 0.5  # Neutral score for untried actions
            else:
                score = 0.5  # Neutral score for untried actions

            if score > best_score:
                best_score = score
                best_action = action

        # If no action was found (shouldn't happen), default to first
        if best_action is None:
            best_action = candidate_actions[0]

        # Log when feedback influences the decision
        if feedback_influenced:
            action_rates = []
            for action in candidate_actions:
                if action in self._action_stats:
                    stats = self._action_stats[action]
                    total = stats["success"] + stats["failure"]
                    if total > 0:
                        rate = stats["success"] / total
                        action_rates.append(f"{action}={rate:.2%}")

            self._logger.info(
                f"Decision influenced by feedback: selected '{best_action}' "
                f"(rates: {', '.join(action_rates)})"
            )

        return best_action

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
            action = decision["action"]

            # Update action statistics
            if action not in self._action_stats:
                self._action_stats[action] = {"success": 0, "failure": 0}

            if outcome == "success":
                self._action_stats[action]["success"] += 1
            else:
                self._action_stats[action]["failure"] += 1

            # Calculate success rate
            total = self._action_stats[action]["success"] + self._action_stats[action]["failure"]
            success_rate = self._action_stats[action]["success"] / total if total > 0 else 0

            self._logger.info(
                f"Received feedback for decision {decision_id[:8]}...: "
                f"action='{action}', outcome='{outcome}', "
                f"success_rate={success_rate:.2%} ({self._action_stats[action]['success']}/{total})"
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

        # Calculate action success rates
        action_success_rates = {}
        for action, stats in self._action_stats.items():
            total = stats["success"] + stats["failure"]
            if total > 0:
                success_rate = stats["success"] / total
                action_success_rates[action] = {
                    "success_rate": success_rate,
                    "success": stats["success"],
                    "failure": stats["failure"],
                    "total": total
                }

        return {
            "decision_count": self._decision_count,
            "feedback_count": len(self._feedback),
            "state": self.state.value,
            "last_decision": last_decision,
            "action_success_rates": action_success_rates,
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

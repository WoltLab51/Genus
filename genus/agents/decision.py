"""Decision Agent - Makes decisions based on analysis results."""

import logging
from typing import Any, Dict, List, Optional

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message, MessagePriority
from genus.storage.memory import MemoryStore
from genus.storage.decisions import DecisionStore
from genus.storage.models import AnalysisResult, Decision


class DecisionAgent(Agent):
    """
    Makes decisions based on analysis results.

    Responsibilities:
    - Subscribe to 'data.analyzed' events
    - Generate recommendations based on confidence
    - Calculate priority levels
    - Store decisions
    - Publish 'decision.made' events

    Clean Architecture:
    - Event-driven via MessageBus
    - Dependencies injected
    - Subscriptions in initialize()
    """

    def __init__(
        self,
        message_bus: MessageBus,
        memory_store: MemoryStore,
        decision_store: DecisionStore,
        agent_id: str = "decision",
        name: str = "Decision Agent"
    ):
        """
        Initialize the Decision agent.

        Args:
            message_bus: Message bus for communication
            memory_store: Memory store for state
            decision_store: Decision store for persistence
            agent_id: Unique identifier
            name: Human-readable name
        """
        super().__init__(agent_id, name)
        self._message_bus = message_bus
        self._memory_store = memory_store
        self._decision_store = decision_store
        self._logger = logging.getLogger(f"genus.agent.{self.id}")

    async def initialize(self) -> None:
        """Initialize agent and subscribe to topics."""
        self._logger.info(f"Initializing {self.name}")

        # CRITICAL: Subscribe to 'data.analyzed' events
        self._message_bus.subscribe(
            topic="data.analyzed",
            subscriber_id=self.id,
            callback=self._on_data_analyzed
        )
        self._logger.info("Subscribed to 'data.analyzed' topic")

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

    async def _on_data_analyzed(self, message: Message) -> None:
        """
        Handle data.analyzed events.

        Args:
            message: Message containing analysis result
        """
        self._logger.info(f"Received data.analyzed event from {message.sender_id}")
        result_raw = message.payload.get("result", {})
        if result_raw:
            result = AnalysisResult(**result_raw)
            await self.decide(result)

    async def decide(self, analysis_result: AnalysisResult) -> Decision:
        """
        Make a decision based on analysis result.

        Args:
            analysis_result: The analysis to base decision on

        Returns:
            Decision object
        """
        self._update_last_active()

        recommendation = self._generate_recommendation(analysis_result)
        priority = self._calculate_priority(analysis_result)

        decision = Decision(
            analysis_result=analysis_result,
            recommendation=recommendation,
            priority=priority,
        )

        # Store decision
        self._decision_store.add(decision)

        # Store in memory
        self._memory_store.set(self.id, "last_decision", decision.model_dump())

        # Publish event
        message = Message(
            topic="decision.made",
            payload={"decision": decision.model_dump()},
            sender_id=self.id,
            priority=MessagePriority.HIGH if priority <= 2 else MessagePriority.NORMAL,
        )
        await self._message_bus.publish(message)

        self._logger.info(f"Decision made: priority={priority}, confidence={analysis_result.confidence:.2f}")
        return decision

    def _generate_recommendation(self, result: AnalysisResult) -> str:
        """
        Generate recommendation based on confidence.

        Args:
            result: Analysis result

        Returns:
            Recommendation string
        """
        if result.confidence >= 0.8:
            return f"High confidence ({result.confidence:.0%}): {result.summary} Act on these insights."
        elif result.confidence >= 0.5:
            return f"Moderate confidence ({result.confidence:.0%}): {result.summary} Review insights before acting."
        else:
            return "Low confidence: Insufficient data. Collect more data before making decisions."

    def _calculate_priority(self, result: AnalysisResult) -> int:
        """
        Calculate priority based on confidence.

        Args:
            result: Analysis result

        Returns:
            Priority (1=highest, 5=lowest)
        """
        if result.confidence >= 0.8:
            return 1
        elif result.confidence >= 0.6:
            return 2
        elif result.confidence >= 0.4:
            return 3
        else:
            return 4

    def get_decisions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent decisions.

        Args:
            limit: Maximum number of decisions to return

        Returns:
            List of decisions as dictionaries
        """
        return [d.model_dump() for d in self._decision_store.get_recent(limit)]

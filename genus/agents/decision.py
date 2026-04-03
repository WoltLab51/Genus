"""
Decision Agent - makes decisions based on analysis with learning capability.
"""
from genus.core.agent import Agent
from genus.communication.message_bus import MessageBus, Message
from genus.storage.stores import DecisionStore, FeedbackStore
from genus.storage.learning import LearningEngine
import uuid
import logging

logger = logging.getLogger(__name__)


class DecisionAgent(Agent):
    """
    Agent responsible for making decisions based on analysis.
    Integrates learning from past feedback to improve recommendations.
    """

    def __init__(
        self,
        name: str,
        message_bus: MessageBus,
        decision_store: DecisionStore,
        feedback_store: FeedbackStore,
    ):
        super().__init__(name)
        self.message_bus = message_bus
        self.decision_store = decision_store
        self.feedback_store = feedback_store
        self.learning_engine = LearningEngine(feedback_store, decision_store)
        self._callbacks = []

    async def initialize(self) -> None:
        """Initialize and subscribe to analysis results."""
        await super().initialize()
        callback = self._handle_analysis
        self.message_bus.subscribe("analysis.complete", callback)
        self._callbacks.append(("analysis.complete", callback))
        logger.info(f"{self.name} initialized and subscribed to 'analysis.complete'")

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

    async def _handle_analysis(self, message: Message) -> None:
        """Handle analysis results and make decisions with learning."""
        logger.info(f"{self.name} processing analysis from {message.sender}")

        analysis = message.data
        context = analysis.get("context", "No context provided")

        # Generate initial recommendation
        recommendation = self._generate_recommendation(analysis)
        initial_confidence = 0.75  # Base confidence

        # Query similar past decisions
        similar_decisions = await self.learning_engine.query_similar_decisions(
            context, recommendation
        )

        if similar_decisions:
            logger.info(
                f"Found {len(similar_decisions)} similar past decisions, applying learning"
            )

        # Adjust decision based on past learning
        (
            adjusted_recommendation,
            adjusted_confidence,
            learning_info,
        ) = await self.learning_engine.adjust_decision(
            context, recommendation, initial_confidence
        )

        # Log when past feedback influences a decision (Observability requirement)
        if learning_info["learning_applied"]:
            logger.info(
                f"🎓 LEARNING APPLIED: {learning_info['adjustment_reason']} "
                f"(confidence: {initial_confidence:.2f} -> {adjusted_confidence:.2f})"
            )
        else:
            logger.info(f"No learning data available for this decision pattern")

        # Store decision
        decision_id = str(uuid.uuid4())
        reasoning = (
            f"Based on analysis: {analysis.get('insights')}. "
            f"Learning: {learning_info.get('adjustment_reason', 'No past data')}"
        )

        await self.decision_store.store_decision(
            decision_id=decision_id,
            context=context,
            recommendation=adjusted_recommendation,
            confidence=adjusted_confidence,
            reasoning=reasoning,
        )

        # Publish decision
        decision_result = {
            "decision_id": decision_id,
            "context": context,
            "recommendation": adjusted_recommendation,
            "confidence": adjusted_confidence,
            "reasoning": reasoning,
            "learning_info": learning_info,
            "similar_decisions_count": len(similar_decisions),
        }

        await self.message_bus.publish(
            "decision.made", decision_result, sender=self.name
        )
        logger.info(
            f"{self.name} made decision {decision_id}: "
            f"{adjusted_recommendation} (confidence: {adjusted_confidence:.2f})"
        )

    def _generate_recommendation(self, analysis: dict) -> str:
        """Generate a recommendation based on analysis."""
        # Simple recommendation logic
        insights = analysis.get("insights", "")
        if "analyzed" in insights.lower():
            return f"Proceed with action based on {insights}"
        return "Review and evaluate further"

    async def submit_feedback(
        self, decision_id: str, score: float, label: str, comment: str = None
    ) -> None:
        """
        Submit feedback for a decision.
        This is called externally (e.g., via API) to provide feedback.

        Args:
            decision_id: ID of the decision to provide feedback for
            score: Numeric score (0.0 to 1.0)
            label: "success" or "failure"
            comment: Optional comment
        """
        feedback_id = str(uuid.uuid4())

        await self.feedback_store.store_feedback(
            feedback_id=feedback_id,
            decision_id=decision_id,
            score=score,
            label=label,
            comment=comment,
        )

        # Invalidate learning cache to incorporate new feedback
        self.learning_engine.invalidate_cache()

        logger.info(
            f"📝 Feedback received: {label} (score: {score}) for decision {decision_id}"
        )

        # Publish feedback event
        await self.message_bus.publish(
            "feedback.submitted",
            {
                "feedback_id": feedback_id,
                "decision_id": decision_id,
                "score": score,
                "label": label,
            },
            sender=self.name,
        )

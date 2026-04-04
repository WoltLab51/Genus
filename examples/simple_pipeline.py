"""
Simple Pipeline Example

Demonstrates a minimal working pipeline using the GENUS architecture:
- DataCollector generates mock data
- Analysis processes the data
- Decision makes a simple decision based on the analysis
- Feedback simulates feedback for the decision (success/failure)
"""

import asyncio
from genus.core.lifecycle import Lifecycle
from genus.communication.message_bus import MessageBus
from genus.agents import DataCollectorAgent, AnalysisAgent, DecisionAgent, FeedbackAgent
from genus.config import Config
from genus.utils.logger import setup_logging, get_logger


async def main():
    """Run the simple pipeline."""
    # Setup
    config = Config()
    setup_logging(level="INFO")
    logger = get_logger(__name__)

    logger.info("=" * 60)
    logger.info("Starting GENUS Simple Pipeline")
    logger.info("=" * 60)

    # Create message bus
    message_bus = MessageBus(max_queue_size=1000)

    # Create agents
    data_collector = DataCollectorAgent(
        name="DataCollector",
        message_bus=message_bus
    )

    analysis = AnalysisAgent(
        name="AnalysisAgent",
        message_bus=message_bus
    )

    decision = DecisionAgent(
        name="DecisionAgent",
        message_bus=message_bus
    )

    feedback = FeedbackAgent(
        name="FeedbackAgent",
        message_bus=message_bus,
        success_rate=0.7
    )

    # Create lifecycle manager
    lifecycle = Lifecycle()
    lifecycle.register_agent(analysis)  # Register analysis first (subscriber)
    lifecycle.register_agent(decision)   # Register decision second (subscriber)
    lifecycle.register_agent(feedback)   # Register feedback third (subscriber)
    lifecycle.register_agent(data_collector)  # Register data collector last (publisher)

    # Initialize all agents (this sets up subscriptions)
    logger.info("\n--- Initializing Agents ---")
    await lifecycle.start_all()

    # Wait a moment to ensure all agents are running and message processing completes
    logger.info("\n--- Running Pipeline ---")
    await asyncio.sleep(2)

    # Print statistics
    logger.info("\n" + "=" * 60)
    logger.info("Pipeline Statistics")
    logger.info("=" * 60)
    logger.info(f"DataCollector: {data_collector.get_stats()}")
    logger.info(f"AnalysisAgent: {analysis.get_stats()}")
    logger.info(f"DecisionAgent: {decision.get_stats()}")
    logger.info(f"FeedbackAgent: {feedback.get_stats()}")

    # Print message history
    logger.info("\n--- Message Flow ---")
    messages = message_bus.get_message_history()
    for i, msg in enumerate(messages, 1):
        logger.info(f"{i}. Topic: {msg.topic}, Sender: {msg.sender_id[:8]}...")

    # Print decisions with feedback
    logger.info("\n--- Decisions with Feedback ---")
    decisions_with_feedback = decision.get_decisions_with_feedback()
    for i, dec in enumerate(decisions_with_feedback, 1):
        logger.info(f"{i}. Decision ID: {dec['decision_id'][:8]}...")
        logger.info(f"   Action: {dec['action']}")
        logger.info(f"   Feedback: {dec.get('feedback', {}).get('outcome', 'N/A')}")

    # Cleanup
    logger.info("\n--- Stopping Agents ---")
    await lifecycle.stop_all()

    logger.info("\n" + "=" * 60)
    logger.info("Pipeline completed successfully!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

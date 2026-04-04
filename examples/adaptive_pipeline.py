"""
Adaptive Pipeline Example

Demonstrates adaptive decision-making based on feedback:
- DecisionAgent learns from feedback over multiple iterations
- Actions with higher success rates are preferred
- Success rates are tracked and logged
"""

import asyncio
from genus.core.lifecycle import Lifecycle
from genus.communication.message_bus import MessageBus
from genus.agents import DataCollectorAgent, AnalysisAgent, DecisionAgent, FeedbackAgent
from genus.config import Config
from genus.utils.logger import setup_logging, get_logger


async def main():
    """Run the adaptive pipeline with multiple iterations."""
    # Setup
    config = Config()
    setup_logging(level="INFO")
    logger = get_logger(__name__)

    logger.info("=" * 60)
    logger.info("Starting GENUS Adaptive Pipeline")
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
        success_rate=0.5  # Lower success rate to see adaptation
    )

    # Create lifecycle manager
    lifecycle = Lifecycle()
    lifecycle.register_agent(analysis)
    lifecycle.register_agent(decision)
    lifecycle.register_agent(feedback)

    # Initialize all agents (this sets up subscriptions)
    logger.info("\n--- Initializing Agents ---")
    await lifecycle.start_all()

    # Run multiple iterations to demonstrate learning
    num_iterations = 5
    logger.info(f"\n--- Running {num_iterations} Iterations ---")

    for iteration in range(1, num_iterations + 1):
        logger.info(f"\n=== Iteration {iteration}/{num_iterations} ===")

        # Manually trigger data collection for each iteration
        await data_collector.start()

        # Wait for messages to process
        await asyncio.sleep(1)

    # Wait a bit more to ensure all feedback is processed
    await asyncio.sleep(1)

    # Print statistics
    logger.info("\n" + "=" * 60)
    logger.info("Final Pipeline Statistics")
    logger.info("=" * 60)
    logger.info(f"DataCollector: {data_collector.get_stats()}")
    logger.info(f"AnalysisAgent: {analysis.get_stats()}")

    decision_stats = decision.get_stats()
    logger.info(f"DecisionAgent: decision_count={decision_stats['decision_count']}, "
                f"feedback_count={decision_stats['feedback_count']}")

    # Print action success rates
    if decision_stats.get('action_success_rates'):
        logger.info("\n--- Action Success Rates ---")
        for action, stats in decision_stats['action_success_rates'].items():
            logger.info(
                f"  {action}: {stats['success_rate']:.2%} "
                f"({stats['success']}/{stats['total']} successful)"
            )

    logger.info(f"\nFeedbackAgent: {feedback.get_stats()}")

    # Print decisions with feedback
    logger.info("\n--- All Decisions with Feedback ---")
    decisions_with_feedback = decision.get_decisions_with_feedback()
    for i, dec in enumerate(decisions_with_feedback, 1):
        feedback_outcome = dec.get('feedback', {}).get('outcome', 'N/A')
        logger.info(f"{i}. Action: {dec['action']}, Feedback: {feedback_outcome}")

    # Cleanup
    logger.info("\n--- Stopping Agents ---")
    await lifecycle.stop_all()

    logger.info("\n" + "=" * 60)
    logger.info("Adaptive pipeline completed successfully!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

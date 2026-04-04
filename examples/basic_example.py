"""
Example GENUS Application

Demonstrates how to use the GENUS framework to create and coordinate agents.
"""

import asyncio
from genus.core.lifecycle import Lifecycle
from genus.communication.message_bus import MessageBus
from genus.agents import WorkerAgent, CoordinatorAgent
from genus.config import Config
from genus.utils.logger import setup_logging, get_logger


async def main():
    """Run the example application."""
    # Setup
    config = Config()
    setup_logging(level="INFO")
    logger = get_logger(__name__)

    logger.info("Starting GENUS Example Application")
    logger.info(f"Environment: {config.get('system.environment')}")

    # Create message bus
    message_bus = MessageBus(max_queue_size=1000)

    # Create agents
    coordinator = CoordinatorAgent(
        name="MainCoordinator",
        message_bus=message_bus
    )

    worker1 = WorkerAgent(
        name="Worker-1",
        message_bus=message_bus
    )

    worker2 = WorkerAgent(
        name="Worker-2",
        message_bus=message_bus
    )

    # Create lifecycle manager
    lifecycle = Lifecycle()
    lifecycle.register_agent(coordinator)
    lifecycle.register_agent(worker1)
    lifecycle.register_agent(worker2)

    # Start all agents
    logger.info("Starting all agents...")
    await lifecycle.start_all()

    # Run for a limited time (for demo purposes)
    logger.info("Running for 10 seconds...")
    await asyncio.sleep(10)

    # Print statistics
    logger.info("\n=== Statistics ===")
    logger.info(f"Coordinator: {coordinator.get_stats()}")
    logger.info(f"Worker 1: {worker1.get_stats()}")
    logger.info(f"Worker 2: {worker2.get_stats()}")

    # Cleanup
    logger.info("\nStopping all agents...")
    await lifecycle.stop_all()

    logger.info("Example application completed")


if __name__ == "__main__":
    asyncio.run(main())

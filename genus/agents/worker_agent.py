"""
Worker Agent Implementation

Example agent that performs work tasks and communicates results.
"""

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message, MessagePriority
from genus.utils.logger import get_logger
from typing import Optional
import asyncio


class WorkerAgent(Agent):
    """
    Worker agent that processes tasks and reports results.

    Demonstrates:
    - Subscribing to topics
    - Processing messages
    - Publishing results
    - State management
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        message_bus: Optional[MessageBus] = None
    ):
        """
        Initialize the worker agent.

        Args:
            agent_id: Unique identifier for the agent
            name: Human-readable name
            message_bus: Message bus for communication
        """
        super().__init__(agent_id, name)
        self._message_bus = message_bus
        self._logger = get_logger(f"{self.__class__.__name__}.{self.id}")
        self._running = False
        self._task_count = 0

    async def initialize(self) -> None:
        """Initialize the worker agent."""
        self._logger.info(f"Initializing {self.name}")

        if self._message_bus:
            # Subscribe to task topics
            self._message_bus.subscribe(
                "tasks.work",
                self.id,
                self.process_message
            )
            self._logger.info(f"Subscribed to 'tasks.work'")

        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Start the worker agent."""
        self._logger.info(f"Starting {self.name}")
        self._running = True
        self._transition_state(AgentState.RUNNING)

        # Run main loop
        await self._run_loop()

    async def stop(self) -> None:
        """Stop the worker agent."""
        self._logger.info(f"Stopping {self.name}")
        self._running = False

        if self._message_bus:
            self._message_bus.unsubscribe_all(self.id)

        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message: Message) -> None:
        """
        Process an incoming message.

        Args:
            message: The message to process
        """
        self._logger.info(f"Processing message from {message.sender_id}: {message.payload}")

        # Simulate work
        await asyncio.sleep(0.1)
        self._task_count += 1

        # Send result back
        if self._message_bus:
            result_message = Message(
                topic="tasks.results",
                payload={
                    "status": "completed",
                    "task": message.payload,
                    "worker_id": self.id,
                    "task_count": self._task_count,
                },
                sender_id=self.id,
                priority=MessagePriority.NORMAL,
            )
            await self._message_bus.publish(result_message)
            self._logger.info(f"Task completed: {self._task_count} total tasks processed")

    async def _run_loop(self) -> None:
        """Main execution loop."""
        while self._running:
            # Worker agents are message-driven, so just wait
            await asyncio.sleep(1)

    def get_stats(self) -> dict:
        """
        Get worker statistics.

        Returns:
            Dictionary of statistics
        """
        return {
            "task_count": self._task_count,
            "state": self.state.value,
        }

"""
Coordinator Agent Implementation

Example agent that coordinates work across multiple worker agents.
"""

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message, MessagePriority
from genus.utils.logger import get_logger
from typing import Optional, List
import asyncio


class CoordinatorAgent(Agent):
    """
    Coordinator agent that distributes tasks to workers.

    Demonstrates:
    - Publishing tasks
    - Collecting results
    - Coordinating multiple agents
    - Monitoring system health
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        message_bus: Optional[MessageBus] = None
    ):
        """
        Initialize the coordinator agent.

        Args:
            agent_id: Unique identifier for the agent
            name: Human-readable name
            message_bus: Message bus for communication
        """
        super().__init__(agent_id, name)
        self._message_bus = message_bus
        self._logger = get_logger(f"{self.__class__.__name__}.{self.id}")
        self._running = False
        self._tasks_sent = 0
        self._results_received = 0
        self._pending_tasks: List[str] = []

    async def initialize(self) -> None:
        """Initialize the coordinator agent."""
        self._logger.info(f"Initializing {self.name}")

        if self._message_bus:
            # Subscribe to result topics
            self._message_bus.subscribe(
                "tasks.results",
                self.id,
                self.process_message
            )
            self._logger.info(f"Subscribed to 'tasks.results'")

        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Start the coordinator agent."""
        self._logger.info(f"Starting {self.name}")
        self._running = True
        self._transition_state(AgentState.RUNNING)

        # Run main loop
        await self._run_loop()

    async def stop(self) -> None:
        """Stop the coordinator agent."""
        self._logger.info(f"Stopping {self.name}")
        self._running = False

        if self._message_bus:
            self._message_bus.unsubscribe_all(self.id)

        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message: Message) -> None:
        """
        Process an incoming message (result from worker).

        Args:
            message: The message to process
        """
        self._logger.info(f"Received result from {message.sender_id}")
        self._results_received += 1

        # Remove from pending tasks
        task_id = message.payload.get("task", {}).get("task_id")
        if task_id in self._pending_tasks:
            self._pending_tasks.remove(task_id)

        self._logger.info(
            f"Progress: {self._results_received}/{self._tasks_sent} tasks completed, "
            f"{len(self._pending_tasks)} pending"
        )

    async def send_task(self, task_data: dict) -> None:
        """
        Send a task to workers.

        Args:
            task_data: Task data to send
        """
        if not self._message_bus:
            self._logger.warning("No message bus configured")
            return

        task_id = f"task_{self._tasks_sent + 1}"
        task_data["task_id"] = task_id

        message = Message(
            topic="tasks.work",
            payload=task_data,
            sender_id=self.id,
            priority=MessagePriority.NORMAL,
        )

        await self._message_bus.publish(message)
        self._tasks_sent += 1
        self._pending_tasks.append(task_id)
        self._logger.info(f"Sent task {task_id}")

    async def _run_loop(self) -> None:
        """Main execution loop - send periodic tasks."""
        task_interval = 2  # seconds

        while self._running:
            # Send a sample task
            await self.send_task({
                "type": "example_work",
                "description": f"Task {self._tasks_sent + 1}",
            })

            await asyncio.sleep(task_interval)

    def get_stats(self) -> dict:
        """
        Get coordinator statistics.

        Returns:
            Dictionary of statistics
        """
        return {
            "tasks_sent": self._tasks_sent,
            "results_received": self._results_received,
            "pending_tasks": len(self._pending_tasks),
            "state": self.state.value,
        }

"""Worker agent for executing tasks."""
from genus.core import Agent, Message
from genus.storage import MemoryStore
from genus.communication import EventBus
from typing import Optional
import asyncio


class WorkerAgent(Agent):
    """Worker agent that executes assigned tasks."""

    def __init__(
        self,
        agent_id: str,
        message_bus,
        memory_store: Optional[MemoryStore] = None,
        event_bus: Optional[EventBus] = None
    ):
        super().__init__(agent_id, message_bus)
        self.memory_store = memory_store
        self.event_bus = event_bus

    async def start(self):
        """Start the worker agent."""
        self.subscribe("task.assigned")
        if self.event_bus:
            await self.event_bus.emit_event(
                event_type="agent.started",
                data={"agent_id": self.agent_id, "type": "worker"},
                source=self.agent_id
            )

    async def handle_message(self, message: Message):
        """Handle incoming messages."""
        if message.topic == "task.assigned":
            await self._handle_task_assigned(message)

    async def _handle_task_assigned(self, message: Message):
        """Handle assigned task."""
        task_data = message.payload.get("task_data", {})
        decision_id = message.payload.get("decision_id")

        # Simulate task processing
        await asyncio.sleep(0.1)  # Simulate work

        # Make decision about how to execute task
        result = {
            "status": "completed",
            "task_type": task_data.get("type", "unknown"),
            "output": f"Processed: {task_data.get('input', 'N/A')}"
        }

        # Store worker's decision if memory store is available
        worker_decision_id = None
        if self.memory_store:
            worker_decision_id = await self.memory_store.store_decision(
                agent_id=self.agent_id,
                decision_type="task_execution",
                input_data=task_data,
                output_data=result,
                metadata={"parent_decision_id": decision_id}
            )

        # Emit event
        if self.event_bus:
            await self.event_bus.emit_event(
                event_type="decision.made",
                data={
                    "decision_id": worker_decision_id,
                    "agent_id": self.agent_id,
                    "decision_type": "task_execution"
                },
                source=self.agent_id
            )

        # Notify completion
        await self.publish("task.completed", {
            "result": result,
            "decision_id": decision_id,
            "worker_decision_id": worker_decision_id
        })

"""Coordinator agent for managing workflows."""
from genus.core import Agent, Message
from genus.storage import MemoryStore
from genus.communication import EventBus
from typing import Optional
import json


class CoordinatorAgent(Agent):
    """Coordinator agent that manages tasks and delegates to workers."""

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
        """Start the coordinator agent."""
        self.subscribe("task.request")
        self.subscribe("task.completed")
        if self.event_bus:
            await self.event_bus.emit_event(
                event_type="agent.started",
                data={"agent_id": self.agent_id, "type": "coordinator"},
                source=self.agent_id
            )

    async def handle_message(self, message: Message):
        """Handle incoming messages."""
        if message.topic == "task.request":
            await self._handle_task_request(message)
        elif message.topic == "task.completed":
            await self._handle_task_completed(message)

    async def _handle_task_request(self, message: Message):
        """Handle task request by delegating to workers."""
        task_data = message.payload.get("task_data", {})

        # Make decision about how to handle the task
        decision_data = {
            "action": "delegate",
            "task_type": task_data.get("type", "unknown"),
            "worker_assigned": "worker-001"
        }

        # Store decision if memory store is available
        decision_id = None
        if self.memory_store:
            decision_id = await self.memory_store.store_decision(
                agent_id=self.agent_id,
                decision_type="task_delegation",
                input_data=task_data,
                output_data=decision_data
            )

        # Emit event
        if self.event_bus:
            await self.event_bus.emit_event(
                event_type="decision.made",
                data={
                    "decision_id": decision_id,
                    "agent_id": self.agent_id,
                    "decision_type": "task_delegation"
                },
                source=self.agent_id
            )

        # Delegate to worker
        await self.publish("task.assigned", {
            "task_data": task_data,
            "decision_id": decision_id,
            "assigned_to": "worker-001"
        })

    async def _handle_task_completed(self, message: Message):
        """Handle task completion notification."""
        result = message.payload.get("result", {})
        decision_id = message.payload.get("decision_id")

        # Emit event
        if self.event_bus:
            await self.event_bus.emit_event(
                event_type="task.completed",
                data={
                    "decision_id": decision_id,
                    "agent_id": self.agent_id,
                    "result": result
                },
                source=self.agent_id
            )

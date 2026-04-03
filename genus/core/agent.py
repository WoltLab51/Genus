"""Core abstractions for GENUS agent system."""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime
import uuid


class Message:
    """Message for agent communication."""

    def __init__(
        self,
        topic: str,
        payload: Dict[str, Any],
        sender: Optional[str] = None,
        message_id: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ):
        self.topic = topic
        self.payload = payload
        self.sender = sender
        self.message_id = message_id or str(uuid.uuid4())
        self.timestamp = timestamp or datetime.utcnow()

    def __repr__(self):
        return f"Message(topic={self.topic}, sender={self.sender}, id={self.message_id})"


class Agent(ABC):
    """Base class for all GENUS agents."""

    def __init__(self, agent_id: str, message_bus: 'MessageBus'):
        self.agent_id = agent_id
        self.message_bus = message_bus
        self.subscriptions = []

    def subscribe(self, topic: str):
        """Subscribe to a message topic."""
        self.subscriptions.append(topic)
        self.message_bus.subscribe(topic, self.handle_message)

    @abstractmethod
    async def handle_message(self, message: Message):
        """Handle incoming messages."""
        pass

    async def publish(self, topic: str, payload: Dict[str, Any]):
        """Publish a message to a topic."""
        message = Message(topic=topic, payload=payload, sender=self.agent_id)
        await self.message_bus.publish(message)

    async def start(self):
        """Start the agent."""
        pass

    async def stop(self):
        """Stop the agent."""
        pass

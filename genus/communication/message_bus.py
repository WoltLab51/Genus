"""Message bus for agent communication using publish-subscribe pattern."""
from typing import Dict, List, Callable, Any, Optional
from datetime import datetime, timezone
import asyncio
from dataclasses import dataclass, field


@dataclass
class Message:
    """Message sent through the message bus."""
    topic: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sender: Optional[str] = None


class MessageBus:
    """Unified message bus for agent communication.

    All agent communication goes through this bus using publish-subscribe pattern.
    Agents never communicate directly with each other.
    The MessageBus also serves as an observability log (message history).
    """

    def __init__(self):
        """Initialize message bus."""
        self._subscribers: Dict[str, List[Callable]] = {}
        self._message_history: List[Message] = []
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, data: Dict[str, Any], sender: Optional[str] = None) -> None:
        """Publish a message to a topic.

        Args:
            topic: Topic to publish to
            data: Message data
            sender: Optional sender identifier
        """
        message = Message(topic=topic, data=data, sender=sender)

        async with self._lock:
            self._message_history.append(message)

        # Notify all subscribers
        if topic in self._subscribers:
            for handler in self._subscribers[topic]:
                try:
                    await handler(message)
                except Exception as e:
                    # Log error but continue notifying other subscribers
                    print(f"Error in message handler for topic '{topic}': {e}")

    def subscribe(self, topic: str, handler: Callable) -> None:
        """Subscribe to a topic.

        Args:
            topic: Topic to subscribe to
            handler: Async function to call when message is published
        """
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable) -> None:
        """Unsubscribe from a topic.

        Args:
            topic: Topic to unsubscribe from
            handler: Handler to remove
        """
        if topic in self._subscribers and handler in self._subscribers[topic]:
            self._subscribers[topic].remove(handler)

    def get_message_history(self, topic: Optional[str] = None, limit: int = 100) -> List[Message]:
        """Get message history for observability.

        Args:
            topic: Optional topic filter
            limit: Maximum number of messages to return

        Returns:
            List of messages
        """
        if topic:
            messages = [m for m in self._message_history if m.topic == topic]
        else:
            messages = self._message_history

        return messages[-limit:]

    def clear_history(self) -> None:
        """Clear message history."""
        self._message_history.clear()

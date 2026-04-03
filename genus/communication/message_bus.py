"""Message bus for publish-subscribe communication between agents."""

from typing import Any, Callable, Dict, List, Awaitable, Optional
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class Message:
    """Message exchanged via the message bus."""
    topic: str
    data: Any
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: Optional[str] = None


class MessageBus:
    """Unified message bus using publish-subscribe pattern.

    All agent communication goes through the MessageBus.
    Agents never communicate directly with each other.
    The MessageBus also serves as an observability log.
    """

    def __init__(self, state_tracker: Optional[Any] = None):
        """Initialize the message bus.

        Args:
            state_tracker: Optional SystemStateTracker for failure reporting
        """
        self._subscribers: Dict[str, List[Callable[[Message], Awaitable[None]]]] = {}
        self._message_history: List[Message] = []
        self._state_tracker = state_tracker

    def subscribe(self, topic: str, handler: Callable[[Message], Awaitable[None]]) -> None:
        """Subscribe to a topic.

        Args:
            topic: Topic to subscribe to
            handler: Async callback function to handle messages
        """
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable[[Message], Awaitable[None]]) -> None:
        """Unsubscribe from a topic.

        Args:
            topic: Topic to unsubscribe from
            handler: Handler to remove
        """
        if topic in self._subscribers:
            self._subscribers[topic] = [h for h in self._subscribers[topic] if h != handler]

    async def publish(self, topic: str, data: Any, source: Optional[str] = None) -> None:
        """Publish a message to a topic.

        Args:
            topic: Topic to publish to
            data: Message data
            source: Optional source identifier (agent name)
        """
        message = Message(topic=topic, data=data, source=source)
        self._message_history.append(message)

        # Keep only last 1000 messages
        if len(self._message_history) > 1000:
            self._message_history = self._message_history[-1000:]

        # Deliver to subscribers
        if topic in self._subscribers:
            for handler in self._subscribers[topic]:
                try:
                    await handler(message)
                except Exception as e:
                    # Report failure to state tracker if available
                    error_msg = f"Handler failed for topic '{topic}': {str(e)}"
                    if self._state_tracker:
                        self._state_tracker.record_message_bus_error(topic, error_msg)
                    # Continue delivering to other subscribers
                    print(f"MessageBus error: {error_msg}")

    def get_message_history(self, topic: Optional[str] = None, limit: int = 100) -> List[Message]:
        """Get message history for observability.

        Args:
            topic: Optional topic filter
            limit: Maximum number of messages to return

        Returns:
            List of recent messages
        """
        messages = self._message_history
        if topic:
            messages = [m for m in messages if m.topic == topic]
        return messages[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """Get message bus statistics.

        Returns:
            Dict containing subscriber counts and message counts by topic
        """
        topic_counts = {}
        for msg in self._message_history:
            topic_counts[msg.topic] = topic_counts.get(msg.topic, 0) + 1

        return {
            "total_messages": len(self._message_history),
            "topics": list(self._subscribers.keys()),
            "subscriber_counts": {topic: len(handlers) for topic, handlers in self._subscribers.items()},
            "message_counts": topic_counts,
        }

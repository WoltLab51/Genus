"""
Message Bus for agent communication using publish-subscribe pattern.
All agent communication must go through MessageBus. Agents never communicate directly.
"""
from typing import Any, Callable, Dict, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Message:
    """Message structure for agent communication."""

    def __init__(self, topic: str, data: Any, sender: str):
        self.topic = topic
        self.data = data
        self.sender = sender
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "topic": self.topic,
            "data": self.data,
            "sender": self.sender,
            "timestamp": self.timestamp.isoformat(),
        }


class MessageBus:
    """
    Unified MessageBus using publish-subscribe pattern.
    Also serves as observability log (message history).
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._message_history: List[Message] = []

    async def publish(self, topic: str, data: Any, sender: str) -> None:
        """
        Publish a message to a topic.

        Args:
            topic: Topic to publish to
            data: Message data
            sender: Sender identification
        """
        message = Message(topic, data, sender)
        self._message_history.append(message)

        logger.info(f"MessageBus: [{sender}] published to '{topic}'")

        if topic in self._subscribers:
            for callback in self._subscribers[topic]:
                try:
                    await callback(message)
                except Exception as e:
                    logger.error(f"Error in subscriber callback for topic '{topic}': {e}")

    def subscribe(self, topic: str, callback: Callable) -> None:
        """
        Subscribe to a topic.

        Args:
            topic: Topic to subscribe to
            callback: Async callback function to handle messages
        """
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(callback)
        logger.debug(f"New subscription to topic '{topic}'")

    def unsubscribe(self, topic: str, callback: Callable) -> None:
        """
        Unsubscribe from a topic.

        Args:
            topic: Topic to unsubscribe from
            callback: Callback function to remove
        """
        if topic in self._subscribers and callback in self._subscribers[topic]:
            self._subscribers[topic].remove(callback)
            logger.debug(f"Unsubscribed from topic '{topic}'")

    def get_message_history(self) -> List[Dict[str, Any]]:
        """Get message history for observability."""
        return [msg.to_dict() for msg in self._message_history]

    def clear_history(self) -> None:
        """Clear message history."""
        self._message_history.clear()

"""Message bus for agent communication."""

import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class MessageBus:
    """
    Central message bus for agent communication.

    All agent communication goes through this bus using publish-subscribe pattern.
    Agents never communicate directly. The MessageBus also serves as an
    observability log (message history).
    """

    def __init__(self):
        """Initialize the message bus."""
        self._subscriptions: Dict[str, List[Callable]] = defaultdict(list)
        self._message_history: List[Dict[str, Any]] = []

    def subscribe(self, topic: str, callback: Callable) -> None:
        """
        Subscribe to a topic.

        Args:
            topic: Topic name to subscribe to
            callback: Async callback function to handle messages
        """
        if callback not in self._subscriptions[topic]:
            self._subscriptions[topic].append(callback)
            logger.debug(f"Subscribed to topic: {topic}")

    def unsubscribe(self, topic: str, callback: Callable) -> None:
        """
        Unsubscribe from a topic.

        Args:
            topic: Topic name to unsubscribe from
            callback: Callback function to remove
        """
        if callback in self._subscriptions[topic]:
            self._subscriptions[topic].remove(callback)
            logger.debug(f"Unsubscribed from topic: {topic}")

    async def publish(self, topic: str, message: Dict[str, Any]) -> None:
        """
        Publish a message to a topic.

        Args:
            topic: Topic name to publish to
            message: Message data to publish
        """
        # Record in message history for observability
        self._message_history.append({
            "topic": topic,
            "message": message,
        })

        logger.info(f"Publishing message to topic '{topic}': {message}")

        # Notify all subscribers
        callbacks = self._subscriptions.get(topic, [])
        for callback in callbacks:
            try:
                await callback(topic, message)
            except Exception as e:
                logger.error(
                    f"Error in message handler for topic '{topic}': {e}",
                    exc_info=True
                )

    def get_history(self) -> List[Dict[str, Any]]:
        """
        Get message history for observability.

        Returns:
            List of all published messages
        """
        return self._message_history.copy()

    def clear_history(self) -> None:
        """Clear message history."""
        self._message_history.clear()
        logger.debug("Message history cleared")

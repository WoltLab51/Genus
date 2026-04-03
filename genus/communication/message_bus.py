"""Message Bus - Publish-subscribe communication with observability."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from collections import defaultdict
import asyncio
import uuid


class MessagePriority(Enum):
    """Message priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Message:
    """
    Represents a message in the system.

    Messages are the ONLY means of agent-to-agent communication.
    Each message contains:
    - topic: routing key for pub-sub
    - payload: arbitrary data
    - sender_id: originating agent ID
    - metadata: extensible attributes
    """
    topic: str
    payload: Any
    sender_id: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    priority: MessagePriority = MessagePriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)


class MessageBus:
    """
    Central message bus for agent communication.

    Implements publish-subscribe pattern with:
    - Topic-based routing with wildcard support ('agent.*')
    - Message history for observability
    - Async delivery to all subscribers
    - Error isolation (one subscriber failure doesn't affect others)

    Design Principles:
    - No direct agent coupling (agents never reference each other)
    - Message history serves as observability log
    - Dependency Inversion: agents depend on abstract MessageBus
    """

    def __init__(self, max_queue_size: int = 1000, max_history: int = 1000):
        """
        Initialize the message bus.

        Args:
            max_queue_size: Maximum messages per subscriber queue
            max_history: Maximum messages to retain in history
        """
        self._subscribers: Dict[str, Set[str]] = defaultdict(set)
        self._callbacks: Dict[str, Callable] = {}
        self._message_queues: Dict[str, asyncio.Queue] = {}
        self._max_queue_size = max_queue_size
        self._message_history: List[Message] = []
        self._max_history = max_history

    def subscribe(self, topic: str, subscriber_id: str, callback: Callable[[Message], None]) -> None:
        """
        Subscribe to a topic.

        Args:
            topic: Topic to subscribe to (supports wildcards like 'agent.*')
            subscriber_id: Unique identifier of the subscriber
            callback: Async function to call when a message arrives
        """
        self._subscribers[topic].add(subscriber_id)
        callback_key = f"{subscriber_id}:{topic}"
        self._callbacks[callback_key] = callback

        # Create message queue if it doesn't exist
        if subscriber_id not in self._message_queues:
            self._message_queues[subscriber_id] = asyncio.Queue(maxsize=self._max_queue_size)

    def unsubscribe(self, topic: str, subscriber_id: str) -> None:
        """
        Unsubscribe from a topic.

        Args:
            topic: Topic to unsubscribe from
            subscriber_id: Unique identifier of the subscriber
        """
        if topic in self._subscribers:
            self._subscribers[topic].discard(subscriber_id)
            callback_key = f"{subscriber_id}:{topic}"
            if callback_key in self._callbacks:
                del self._callbacks[callback_key]

    def unsubscribe_all(self, subscriber_id: str) -> None:
        """
        Unsubscribe from all topics.

        Args:
            subscriber_id: Unique identifier of the subscriber
        """
        topics_to_remove = []
        for topic, subscribers in self._subscribers.items():
            if subscriber_id in subscribers:
                subscribers.discard(subscriber_id)
                callback_key = f"{subscriber_id}:{topic}"
                if callback_key in self._callbacks:
                    del self._callbacks[callback_key]
            if not subscribers:
                topics_to_remove.append(topic)

        # Clean up empty topic subscriptions
        for topic in topics_to_remove:
            del self._subscribers[topic]

        # Clean up message queue
        if subscriber_id in self._message_queues:
            del self._message_queues[subscriber_id]

    async def publish(self, message: Message) -> None:
        """
        Publish a message to a topic.

        Message is:
        1. Stored in history (observability)
        2. Delivered to all matching subscribers (async, parallel)

        Args:
            message: The message to publish
        """
        # Store in history for observability
        self._message_history.append(message)
        if len(self._message_history) > self._max_history:
            self._message_history.pop(0)

        # Find matching subscribers (including wildcards)
        matching_subscribers = self._get_matching_subscribers(message.topic)

        # Deliver to all matching subscribers (error-isolated)
        tasks = []
        for subscriber_id in matching_subscribers:
            callback_key = f"{subscriber_id}:{message.topic}"
            if callback_key in self._callbacks:
                callback = self._callbacks[callback_key]
                tasks.append(self._deliver_message(callback, message))

        # Execute all deliveries concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _deliver_message(self, callback: Callable, message: Message) -> None:
        """
        Deliver a message to a subscriber's callback.

        Errors are caught and logged to prevent one subscriber from affecting others.

        Args:
            callback: The callback function to invoke
            message: The message to deliver
        """
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(message)
            else:
                callback(message)
        except Exception as e:
            # Log error but don't crash the bus
            # In production, use proper logging
            print(f"Error delivering message to callback: {e}")

    def _get_matching_subscribers(self, topic: str) -> Set[str]:
        """
        Get all subscribers matching a topic (including wildcards).

        Args:
            topic: The topic to match

        Returns:
            Set of subscriber IDs
        """
        matching = set()

        # Exact matches
        if topic in self._subscribers:
            matching.update(self._subscribers[topic])

        # Wildcard matches
        for sub_topic in self._subscribers.keys():
            if self._topic_matches(topic, sub_topic):
                matching.update(self._subscribers[sub_topic])

        return matching

    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """
        Check if a topic matches a pattern (supports * wildcard).

        Examples:
            'agent.data' matches 'agent.*'
            'agent.data.collected' does NOT match 'agent.*' (single-level wildcard)

        Args:
            topic: The actual topic
            pattern: The pattern to match against

        Returns:
            True if the topic matches the pattern
        """
        if pattern == topic:
            return True

        # Simple wildcard matching (single-level)
        if '*' in pattern:
            pattern_parts = pattern.split('.')
            topic_parts = topic.split('.')

            if len(pattern_parts) != len(topic_parts):
                return False

            for p_part, t_part in zip(pattern_parts, topic_parts):
                if p_part != '*' and p_part != t_part:
                    return False

            return True

        return False

    def get_message_history(self, topic: Optional[str] = None, limit: int = 100) -> List[Message]:
        """
        Get message history (observability feature).

        Args:
            topic: Optional topic filter
            limit: Maximum number of messages to return

        Returns:
            List of messages
        """
        if topic:
            filtered = [msg for msg in self._message_history if msg.topic == topic]
            return filtered[-limit:]
        return self._message_history[-limit:]

    def get_topics(self) -> List[str]:
        """
        Get all subscribed topics.

        Returns:
            List of topic names
        """
        return list(self._subscribers.keys())

    def get_subscriber_count(self, topic: str) -> int:
        """
        Get the number of subscribers for a topic.

        Args:
            topic: The topic to check

        Returns:
            Number of subscribers
        """
        return len(self._subscribers.get(topic, set()))

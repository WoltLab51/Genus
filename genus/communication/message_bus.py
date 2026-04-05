"""
Message Bus Implementation

Provides a publish-subscribe message bus for agent communication.
Implements the Observer pattern with decoupled communication.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set
from collections import defaultdict
import asyncio
import uuid

if TYPE_CHECKING:
    from genus.security.topic_acl import TopicAclPolicy
    from genus.security.kill_switch import KillSwitch


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

    Messages are the primary means of communication between agents.
    """
    topic: str
    payload: Any
    sender_id: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    priority: MessagePriority = MessagePriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure timestamp is set."""
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class MessageBus:
    """
    Central message bus for agent communication.

    Implements publish-subscribe pattern allowing agents to:
    - Publish messages to topics
    - Subscribe to topics of interest
    - Receive messages asynchronously

    This design follows the Dependency Inversion Principle - agents depend
    on the abstract MessageBus, not concrete implementations.
    """

    def __init__(
        self,
        max_queue_size: int = 1000,
        acl_policy: Optional["TopicAclPolicy"] = None,
        acl_enforced: bool = False,
        kill_switch: Optional["KillSwitch"] = None,
    ):
        """
        Initialize the message bus.

        Args:
            max_queue_size: Maximum number of messages per subscriber queue
            acl_policy: Optional :class:`~genus.security.topic_acl.TopicAclPolicy`
                instance.  When *acl_enforced* is ``True`` (or when a policy is
                provided and *acl_enforced* is not explicitly set to ``False``),
                every ``publish()`` call checks the ACL before delivering the
                message.  Default: ``None`` (no policy).
            acl_enforced: When ``True`` the ACL policy is enforced and
                :class:`~genus.security.topic_acl.TopicPermissionError` is raised
                for unauthorised sender/topic combinations.  When ``False``
                (default) the bus is fully permissive regardless of whether a
                policy is attached.
            kill_switch: Optional :class:`~genus.security.kill_switch.KillSwitch`
                instance.  When active, ``publish()`` raises
                :class:`~genus.security.kill_switch.KillSwitchActiveError` for
                every topic not on the kill-switch allowlist.
                Default: ``None`` (no kill-switch).
        """
        self._subscribers: Dict[str, Set[str]] = defaultdict(set)
        self._callbacks: Dict[str, Callable] = {}
        self._message_queues: Dict[str, asyncio.Queue] = {}
        self._max_queue_size = max_queue_size
        self._message_history: List[Message] = []
        self._max_history = 1000
        self._acl_policy: Optional["TopicAclPolicy"] = acl_policy
        self._acl_enforced: bool = acl_enforced
        self._kill_switch: Optional["KillSwitch"] = kill_switch

    def subscribe(self, topic: str, subscriber_id: str, callback: Callable[[Message], None]) -> None:
        """
        Subscribe to a topic.

        Args:
            topic: The topic to subscribe to (supports wildcards like 'agent.*')
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
            topic: The topic to unsubscribe from
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

        Security checks (in order):

        1. **Kill-switch**: If a :class:`~genus.security.kill_switch.KillSwitch`
           is attached and active, raises
           :class:`~genus.security.kill_switch.KillSwitchActiveError` unless the
           topic is on the kill-switch allowlist.
        2. **ACL**: If ``acl_enforced=True`` and an
           :class:`~genus.security.topic_acl.TopicAclPolicy` is attached, raises
           :class:`~genus.security.topic_acl.TopicPermissionError` when the
           sender is not allowed to publish on the topic.

        No additional events are published from within this method to avoid
        recursion.

        Args:
            message: The message to publish

        Raises:
            KillSwitchActiveError: When the kill-switch is active and the topic
                is not on the allowlist.
            TopicPermissionError: When ACL enforcement is active and the sender
                is not permitted to publish on the topic.
        """
        # 1) Kill-switch check (first, unconditional when configured)
        if self._kill_switch is not None:
            self._kill_switch.check(message.topic)

        # 2) ACL check (only when enforcement is explicitly enabled)
        if self._acl_enforced and self._acl_policy is not None:
            if not self._acl_policy.is_allowed(message.sender_id, message.topic):
                from genus.security.topic_acl import TopicPermissionError
                raise TopicPermissionError(
                    sender_id=message.sender_id, topic=message.topic
                )

        # Store in history
        self._message_history.append(message)
        if len(self._message_history) > self._max_history:
            self._message_history.pop(0)

        # Find matching subscribers
        matching_subscribers = self._get_matching_subscribers(message.topic)

        # Deliver to all matching subscribers
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
            print(f"Error delivering message: {e}")

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

        # Wildcard matches (simple implementation)
        for sub_topic in self._subscribers.keys():
            if self._topic_matches(topic, sub_topic):
                matching.update(self._subscribers[sub_topic])

        return matching

    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """
        Check if a topic matches a pattern (supports * wildcard).

        Args:
            topic: The actual topic
            pattern: The pattern to match against

        Returns:
            True if the topic matches the pattern
        """
        if pattern == topic:
            return True

        # Simple wildcard matching
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
        Get message history.

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

"""
Redis-backed MessageBus

A :class:`RedisMessageBus` that mirrors the API of the in-memory
:class:`~genus.communication.message_bus.MessageBus` but routes published
messages through Redis Pub/Sub so that multiple processes can communicate.

Differences from the in-memory bus
------------------------------------
- **Wildcard subscriptions are not supported.**  Passing a topic that
  contains ``"*"`` to :meth:`subscribe` raises :class:`ValueError`.
  Subscribe to each explicit topic separately (or use
  :class:`~genus.communication.secure_bus.SecureMessageBus` on top of an
  in-memory bus for wildcard needs).
- Kill-switch and ACL enforcement are **not** implemented at this layer;
  wrap this bus with :class:`~genus.communication.secure_bus.SecureMessageBus`
  to enforce them (see ``genus/cli/orchestrator.py`` and
  ``genus/cli/tool_executor.py`` for usage examples).
- Message history is **local only** – it is not shared across processes.
- :meth:`connect` and :meth:`close` must be called to manage the Redis
  connection.  :meth:`connect` must be called inside a running asyncio event
  loop (i.e. from within an ``async`` function or ``asyncio.run``).

Subscription wildcards
-----------------------
Wildcard topic patterns (e.g. ``"tool.call.*"``) are **not** supported by
:meth:`subscribe`.  A :class:`ValueError` is raised immediately so the caller
is aware rather than silently receiving no messages.  Subscribe to each
concrete topic explicitly instead.

Usage::

    bus = RedisMessageBus(redis_url="redis://localhost:6379/0")
    await bus.connect()

    bus.subscribe("tool.call.requested", "MyAgent", my_handler)
    await bus.publish(some_message)

    await bus.close()
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set

from genus.communication.message_bus import Message
from genus.communication.transports.redis_pubsub import RedisPubSubTransport

logger = logging.getLogger(__name__)


class RedisMessageBus:
    """Redis-backed publish-subscribe message bus.

    Exposes the same core interface as
    :class:`~genus.communication.message_bus.MessageBus`:

    - :meth:`subscribe`
    - :meth:`unsubscribe`
    - :meth:`unsubscribe_all`
    - :meth:`publish` (async)

    Args:
        redis_url: Redis connection URL (default: ``redis://localhost:6379/0``).
                   Override via the ``GENUS_REDIS_URL`` environment variable
                   when using :class:`~genus.cli.tool_executor` or
                   :class:`~genus.cli.orchestrator`.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self._transport = RedisPubSubTransport(redis_url=redis_url)
        # topic -> set of subscriber_ids
        self._subscribers: Dict[str, Set[str]] = defaultdict(set)
        # "subscriber_id:topic" -> callback
        self._callbacks: Dict[str, Callable] = {}
        # Local message history (this process only)
        self._message_history: List[Message] = []
        self._max_history = 1000

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to Redis.  Must be called before :meth:`publish`."""
        await self._transport.connect()

    async def close(self) -> None:
        """Disconnect from Redis and stop the listener."""
        await self._transport.close()

    # ------------------------------------------------------------------
    # Subscribe / Unsubscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        topic: str,
        subscriber_id: str,
        callback: Callable[[Message], Any],
    ) -> None:
        """Subscribe *callback* to *topic*.

        The subscription is registered synchronously; the underlying Redis
        channel subscription is kicked off as an async task.  :meth:`connect`
        must have been awaited before calling this method so that the task
        runs inside a live event loop.

        Args:
            topic:         Exact topic string.  **Wildcard patterns are not
                           supported** – a :class:`ValueError` is raised if
                           ``topic`` contains ``"*"``.  Subscribe to each
                           concrete topic explicitly.
            subscriber_id: Unique subscriber identifier.
            callback:      Async or sync callable invoked with the
                           :class:`~genus.communication.message_bus.Message`.

        Raises:
            ValueError: If *topic* contains a wildcard character ``"*"``.
        """
        if "*" in topic:
            raise ValueError(
                "RedisMessageBus does not support wildcard subscriptions; "
                "subscribe to explicit topics instead.  "
                f"Got topic: {topic!r}"
            )
        self._subscribers[topic].add(subscriber_id)
        callback_key = f"{subscriber_id}:{topic}"
        self._callbacks[callback_key] = callback

        # Subscribe to the exact Redis channel for this topic.
        asyncio.ensure_future(
            self._ensure_channel_subscribed(topic)
        )

    async def _ensure_channel_subscribed(self, channel: str) -> None:
        """Subscribe to *channel* on the transport (idempotent)."""
        try:
            await self._transport.subscribe(channel, self._on_redis_message)
        except Exception as exc:
            logger.warning("Failed to subscribe to Redis channel %r: %s", channel, exc)

    def unsubscribe(self, topic: str, subscriber_id: str) -> None:
        """Unsubscribe *subscriber_id* from *topic*."""
        if topic in self._subscribers:
            self._subscribers[topic].discard(subscriber_id)
            callback_key = f"{subscriber_id}:{topic}"
            self._callbacks.pop(callback_key, None)

    def unsubscribe_all(self, subscriber_id: str) -> None:
        """Unsubscribe *subscriber_id* from all topics."""
        topics_to_check = list(self._subscribers.keys())
        for topic in topics_to_check:
            self._subscribers[topic].discard(subscriber_id)
            callback_key = f"{subscriber_id}:{topic}"
            self._callbacks.pop(callback_key, None)

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(self, message: Message) -> None:
        """Publish *message* to Redis and store it in local history.

        Args:
            message: The :class:`~genus.communication.message_bus.Message` to
                     publish.
        """
        # Store locally for observability
        self._message_history.append(message)
        if len(self._message_history) > self._max_history:
            self._message_history.pop(0)

        await self._transport.publish(message.topic, message)

    # ------------------------------------------------------------------
    # Incoming message dispatch
    # ------------------------------------------------------------------

    async def _on_redis_message(self, message: Message) -> None:
        """Called by the transport for every message received from Redis."""
        # Store in local history too
        self._message_history.append(message)
        if len(self._message_history) > self._max_history:
            self._message_history.pop(0)

        matching = self._get_matching_subscribers(message.topic)
        tasks = []
        for subscriber_id in matching:
            # Try exact topic key first, then wildcard patterns
            callback = None
            exact_key = f"{subscriber_id}:{message.topic}"
            if exact_key in self._callbacks:
                callback = self._callbacks[exact_key]
            else:
                # Check wildcard subscriptions for this subscriber
                for sub_topic, subs in self._subscribers.items():
                    if subscriber_id in subs and self._topic_matches(message.topic, sub_topic):
                        wc_key = f"{subscriber_id}:{sub_topic}"
                        if wc_key in self._callbacks:
                            callback = self._callbacks[wc_key]
                            break
            if callback is not None:
                tasks.append(self._deliver(callback, message))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _deliver(self, callback: Callable, message: Message) -> None:
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(message)
            else:
                callback(message)
        except Exception as exc:
            logger.warning("Error delivering Redis message: %s", exc)

    # ------------------------------------------------------------------
    # Wildcard matching (same logic as in-memory bus)
    # ------------------------------------------------------------------

    def _get_matching_subscribers(self, topic: str) -> Set[str]:
        matching: Set[str] = set()
        if topic in self._subscribers:
            matching.update(self._subscribers[topic])
        for sub_topic in self._subscribers.keys():
            if self._topic_matches(topic, sub_topic):
                matching.update(self._subscribers[sub_topic])
        return matching

    def _topic_matches(self, topic: str, pattern: str) -> bool:
        if pattern == topic:
            return True
        if "*" in pattern:
            pattern_parts = pattern.split(".")
            topic_parts = topic.split(".")
            if len(pattern_parts) != len(topic_parts):
                return False
            return all(
                p == "*" or p == t for p, t in zip(pattern_parts, topic_parts)
            )
        return False

    # ------------------------------------------------------------------
    # History (local only)
    # ------------------------------------------------------------------

    def get_message_history(
        self, topic: Optional[str] = None, limit: int = 100
    ) -> List[Message]:
        """Return local message history (this process only)."""
        if topic:
            filtered = [m for m in self._message_history if m.topic == topic]
            return filtered[-limit:]
        return self._message_history[-limit:]

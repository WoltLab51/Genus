"""
Redis Pub/Sub Transport

Low-level adapter that bridges GENUS :class:`~genus.communication.message_bus.Message`
objects to Redis Pub/Sub channels.

Design notes
------------
- Each GENUS topic string maps 1-to-1 to a Redis channel name.
- Wildcard subscriptions are **not** supported at the Redis transport level.
  Exact-match only.  Document this limitation and handle it in the
  caller (:class:`~genus.communication.redis_message_bus.RedisMessageBus`).
- Messages are serialized to JSON via
  :mod:`genus.communication.serialization` before publishing.
- A single background asyncio task drives the Redis subscriber loop per
  :class:`RedisPubSubTransport` instance.

Usage (inside an async context)::

    transport = RedisPubSubTransport(redis_url="redis://localhost:6379/0")
    await transport.connect()
    await transport.subscribe("tool.call.requested", my_callback)
    await transport.publish("tool.call.requested", message)
    await transport.close()
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from genus.communication.message_bus import Message
from genus.communication.serialization import message_from_dict, message_to_dict

logger = logging.getLogger(__name__)


class RedisPubSubTransport:
    """Redis Pub/Sub adapter for GENUS messages.

    Args:
        redis_url: Redis connection URL, e.g. ``redis://localhost:6379/0``.
                   Passed directly to :func:`redis.asyncio.from_url`.

    Limitation:
        Topic wildcards are **not** supported; only exact-match subscriptions
        are delivered.  The higher-level
        :class:`~genus.communication.redis_message_bus.RedisMessageBus` applies
        in-memory wildcard filtering on top of exact-channel subscriptions.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self._redis_url = redis_url
        self._publish_client: Any = None
        self._subscribe_client: Any = None
        self._pubsub: Any = None
        # channel -> list of callbacks
        self._channel_callbacks: Dict[str, List[Callable]] = {}
        self._listener_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._connected = False

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to Redis and start the subscriber listener loop.

        Raises:
            ImportError: If the ``redis`` package (``redis[asyncio]``) is not
                         installed.
        """
        try:
            import redis.asyncio as aioredis  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "The 'redis' package is required for the Redis transport.  "
                "Install it with: pip install 'redis[asyncio]'"
            ) from exc

        self._publish_client = aioredis.from_url(
            self._redis_url, decode_responses=True
        )
        self._subscribe_client = aioredis.from_url(
            self._redis_url, decode_responses=True
        )
        self._pubsub = self._subscribe_client.pubsub()
        self._connected = True

        # Start listener
        self._listener_task = asyncio.ensure_future(self._listener_loop())
        logger.debug("RedisPubSubTransport connected to %s", self._redis_url)

    async def close(self) -> None:
        """Stop the listener and close both Redis connections."""
        self._connected = False
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            except Exception as _exc:
                logger.warning("RedisPubSubTransport: listener task raised: %s", _exc)
            self._listener_task = None

        if self._pubsub is not None:
            try:
                await self._pubsub.close()
            except Exception as _exc:
                logger.warning("RedisPubSubTransport: close failed: %s", _exc)

        if self._subscribe_client is not None:
            try:
                await self._subscribe_client.aclose()
            except Exception as _exc:
                logger.warning("RedisPubSubTransport: close failed: %s", _exc)

        if self._publish_client is not None:
            try:
                await self._publish_client.aclose()
            except Exception as _exc:
                logger.warning("RedisPubSubTransport: close failed: %s", _exc)

        logger.debug("RedisPubSubTransport closed")

    # ------------------------------------------------------------------
    # Pub/Sub
    # ------------------------------------------------------------------

    async def subscribe(self, channel: str, callback: Callable[[Message], Any]) -> None:
        """Subscribe *callback* to exact-match *channel*.

        Args:
            channel:  The Redis channel name (= GENUS topic string).
            callback: Async (or sync) callable that receives a
                      :class:`~genus.communication.message_bus.Message`.
        """
        if channel not in self._channel_callbacks:
            self._channel_callbacks[channel] = []
            if self._pubsub is not None:
                await self._pubsub.subscribe(channel)
        self._channel_callbacks[channel].append(callback)
        logger.debug("Subscribed to Redis channel %r", channel)

    async def unsubscribe(self, channel: str, callback: Callable) -> None:
        """Remove *callback* from *channel*.  Unsubscribes from Redis when the
        last callback is removed.
        """
        callbacks = self._channel_callbacks.get(channel)
        if callbacks is None:
            return
        try:
            callbacks.remove(callback)
        except ValueError:
            pass
        if not callbacks:
            del self._channel_callbacks[channel]
            if self._pubsub is not None:
                try:
                    await self._pubsub.unsubscribe(channel)
                except Exception as _exc:
                    logger.warning(
                        "RedisPubSubTransport: unsubscribe failed for channel %s: %s",
                        channel, _exc,
                    )

    async def unsubscribe_all(self) -> None:
        """Remove all channel subscriptions."""
        for channel in list(self._channel_callbacks.keys()):
            if self._pubsub is not None:
                try:
                    await self._pubsub.unsubscribe(channel)
                except Exception as _exc:
                    logger.warning(
                        "RedisPubSubTransport: unsubscribe failed for channel %s: %s",
                        channel, _exc,
                    )
        self._channel_callbacks.clear()

    async def publish(self, channel: str, message: Message) -> None:
        """Serialize *message* to JSON and publish it to Redis *channel*.

        Args:
            channel: The Redis channel name (= GENUS topic string).
            message: The :class:`~genus.communication.message_bus.Message` to
                     publish.
        """
        if self._publish_client is None:
            raise RuntimeError(
                "Transport is not connected. Call connect() before publish()."
            )
        data = json.dumps(message_to_dict(message))
        await self._publish_client.publish(channel, data)

    # ------------------------------------------------------------------
    # Internal listener
    # ------------------------------------------------------------------

    async def _listener_loop(self) -> None:
        """Background task: read messages from Redis and dispatch callbacks."""
        while self._connected:
            try:
                if self._pubsub is None:
                    await asyncio.sleep(0.05)
                    continue
                raw = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=0.1
                )
                if raw is None:
                    await asyncio.sleep(0.01)
                    continue

                channel = raw.get("channel", "")
                data = raw.get("data")
                if not isinstance(data, str):
                    continue

                try:
                    d = json.loads(data)
                    message = message_from_dict(d)
                except Exception as exc:
                    logger.warning("Failed to deserialize Redis message: %s", exc)
                    continue

                callbacks = list(self._channel_callbacks.get(channel, []))
                for cb in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(message)
                        else:
                            cb(message)
                    except Exception as exc:
                        logger.warning("Callback error on channel %r: %s", channel, exc)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Redis listener error: %s", exc)
                await asyncio.sleep(0.1)

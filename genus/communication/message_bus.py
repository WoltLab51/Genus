"""
Unified Message Bus

A single publish-subscribe message bus that handles both agent communication
and observability event logging.  This replaces the duplicated ``EventBus`` /
``MessageBus`` split that existed in previous branches.

Design decisions
────────────────
* One bus, one ``Message`` type — agents and infrastructure share the same
  transport so that every interaction is automatically captured in the
  message history (useful for debugging, audit, and future replay).
* Callers may attach ``metadata`` to messages for observability without
  inventing a separate ``Event`` class.
* Async delivery via ``asyncio.gather`` with ``return_exceptions=True`` so
  one failing handler cannot break other subscribers.
"""

from __future__ import annotations

import asyncio
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("genus.message_bus")


@dataclass
class Message:
    """Immutable value object representing a message on the bus."""

    topic: str
    payload: Dict[str, Any]
    sender: Optional[str] = None
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "payload": self.payload,
            "sender": self.sender,
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class MessageBus:
    """Central pub-sub bus for the entire GENUS system.

    Parameters
    ----------
    max_history : int
        Maximum number of messages retained for observability queries.
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._subscribers: Dict[str, List[Callable]] = {}
        self._history: List[Message] = []
        self._max_history = max_history

    # -- subscribe / unsubscribe -----------------------------------------------

    def subscribe(self, topic: str, handler: Callable) -> None:
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)
        logger.debug("subscribed handler to '%s'", topic)

    def unsubscribe(self, topic: str, handler: Callable) -> None:
        if topic in self._subscribers:
            try:
                self._subscribers[topic].remove(handler)
            except ValueError:
                pass
            if not self._subscribers[topic]:
                del self._subscribers[topic]

    def unsubscribe_all(self, topic: str) -> None:
        self._subscribers.pop(topic, None)

    # -- publish ---------------------------------------------------------------

    async def publish(self, message: Message) -> None:
        """Publish *message* to all subscribers of its topic."""
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        handlers = self._subscribers.get(message.topic, [])[:]
        if handlers:
            await asyncio.gather(
                *(h(message) for h in handlers),
                return_exceptions=True,
            )
        logger.debug("published '%s' to %d handler(s)", message.topic, len(handlers))

    async def publish_event(
        self,
        topic: str,
        payload: Dict[str, Any],
        sender: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Convenience wrapper: build a ``Message`` and publish it."""
        msg = Message(
            topic=topic,
            payload=payload,
            sender=sender,
            metadata=metadata or {},
        )
        await self.publish(msg)

    # -- observability ---------------------------------------------------------

    def get_history(
        self,
        topic: Optional[str] = None,
        limit: int = 100,
    ) -> List[Message]:
        msgs = self._history[-limit:] if limit else list(self._history)
        if topic:
            msgs = [m for m in msgs if m.topic == topic]
        return msgs

    def get_topics(self) -> List[str]:
        return list(self._subscribers.keys())

    def get_subscriber_count(self, topic: str) -> int:
        return len(self._subscribers.get(topic, []))

    def clear_history(self) -> None:
        self._history.clear()

"""MessageBus for agent communication using publish-subscribe pattern."""
from typing import Callable, Dict, List
import asyncio
from genus.core.agent import Message


class MessageBus:
    """Central message bus for agent communication."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, topic: str, handler: Callable):
        """Subscribe to a topic with a handler function."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable):
        """Unsubscribe a handler from a topic."""
        if topic in self._subscribers:
            self._subscribers[topic].remove(handler)
            if not self._subscribers[topic]:
                del self._subscribers[topic]

    async def publish(self, message: Message):
        """Publish a message to all subscribers of its topic."""
        if message.topic in self._subscribers:
            handlers = self._subscribers[message.topic].copy()
            tasks = [handler(message) for handler in handlers]
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_topics(self) -> List[str]:
        """Get all registered topics."""
        return list(self._subscribers.keys())

"""
DevAgent Base Class

Provides a reusable base class for dev-loop agents with idempotent
subscription management and graceful lifecycle handling.
"""

from typing import List, Tuple
from genus.communication.message_bus import MessageBus


class DevAgentBase:
    """Base class for dev-loop agents.

    Handles subscription/unsubscription lifecycle with idempotent cleanup.
    Agents extend this class and override :meth:`_subscribe_topics` to
    register their specific topic handlers.

    Args:
        bus:      The MessageBus instance for pub/sub.
        agent_id: Unique identifier for this agent instance.

    Usage::

        class MyAgent(DevAgentBase):
            def _subscribe_topics(self) -> List[Tuple[str, Callable]]:
                return [
                    (topics.MY_TOPIC, self._handle_my_topic),
                ]

            async def _handle_my_topic(self, msg: Message):
                # Process message
                pass

        agent = MyAgent(bus, "my-agent-1")
        agent.start()
        # ... operate ...
        agent.stop()
    """

    def __init__(self, bus: MessageBus, agent_id: str) -> None:
        self._bus = bus
        self.agent_id = agent_id
        self._started = False
        self._subscriptions: List[Tuple[str, str]] = []

    def start(self) -> None:
        """Subscribe to all topics.

        Idempotent: calling multiple times has no additional effect.
        """
        if self._started:
            return

        # Get topic/callback pairs from subclass
        topics_and_callbacks = self._subscribe_topics()

        for topic, callback in topics_and_callbacks:
            subscriber_id = f"{self.agent_id}:{topic}"
            self._bus.subscribe(topic, subscriber_id, callback)
            self._subscriptions.append((topic, subscriber_id))

        self._started = True

    def stop(self) -> None:
        """Unsubscribe from all topics.

        Idempotent: calling multiple times has no additional effect.
        Safe to call even if :meth:`start` was never called.
        """
        if not self._started:
            return

        for topic, subscriber_id in self._subscriptions:
            self._bus.unsubscribe(topic, subscriber_id)

        self._subscriptions.clear()
        self._started = False

    def _subscribe_topics(self) -> List[Tuple[str, any]]:
        """Override in subclasses to register topic handlers.

        Returns:
            List of (topic, callback) tuples.
        """
        return []

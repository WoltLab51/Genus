import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Awaitable
from .logger import get_logger

logger = get_logger("messaging")


class EventBus:
    """Async event bus for inter-agent communication."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._event_log: list[dict] = []

    def subscribe(self, event_type: str, handler: Callable[..., Awaitable[Any]]) -> None:
        self._subscribers[event_type].append(handler)
        logger.info(f"Subscribed handler to event '{event_type}'")

    async def publish(self, event_type: str, payload: Any = None) -> None:
        event = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._event_log.append(event)
        logger.info(f"Publishing event '{event_type}'")
        handlers = self._subscribers.get(event_type, [])
        await asyncio.gather(*[handler(event) for handler in handlers], return_exceptions=True)

    def event_log(self, limit: int = 50) -> list[dict]:
        return self._event_log[-limit:]


# Global singleton event bus
event_bus = EventBus()

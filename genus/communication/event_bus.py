"""EventBus for observability and logging."""
from typing import Any, Callable, Dict, List
import asyncio
from datetime import datetime
import json


class Event:
    """Event for observability."""

    def __init__(self, event_type: str, data: Dict[str, Any], source: str = None):
        self.event_type = event_type
        self.data = data
        self.source = source
        self.timestamp = datetime.utcnow()

    def to_dict(self):
        """Convert event to dictionary."""
        return {
            "event_type": self.event_type,
            "data": self.data,
            "source": self.source,
            "timestamp": self.timestamp.isoformat()
        }

    def __repr__(self):
        return f"Event(type={self.event_type}, source={self.source})"


class EventBus:
    """EventBus for logging and observability."""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._event_log: List[Event] = []
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: str, listener: Callable):
        """Subscribe to an event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)

    def unsubscribe(self, event_type: str, listener: Callable):
        """Unsubscribe from an event type."""
        if event_type in self._listeners:
            self._listeners[event_type].remove(listener)
            if not self._listeners[event_type]:
                del self._listeners[event_type]

    async def emit(self, event: Event):
        """Emit an event to all listeners."""
        async with self._lock:
            self._event_log.append(event)

        if event.event_type in self._listeners:
            listeners = self._listeners[event.event_type].copy()
            tasks = [listener(event) for listener in listeners]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def emit_event(self, event_type: str, data: Dict[str, Any], source: str = None):
        """Convenience method to create and emit an event."""
        event = Event(event_type=event_type, data=data, source=source)
        await self.emit(event)

    def get_events(self, event_type: str = None, limit: int = 100) -> List[Event]:
        """Get recent events, optionally filtered by type."""
        events = self._event_log[-limit:]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events

    def clear_log(self):
        """Clear the event log."""
        self._event_log.clear()

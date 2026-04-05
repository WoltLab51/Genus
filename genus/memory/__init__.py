"""
Memory 2.0 – append-only EventStore for GENUS.

Public API::

    from genus.memory import EventEnvelope, EventStore, JsonlEventStore
"""

from genus.memory.event_store import EventStore
from genus.memory.jsonl_event_store import EventEnvelope, JsonlEventStore

__all__ = ["EventStore", "EventEnvelope", "JsonlEventStore"]

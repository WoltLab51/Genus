"""
Memory 2.0 – append-only EventStore and Run Journal Store for GENUS.

Public API::

    # EventStore (existing)
    from genus.memory import EventEnvelope, EventStore, JsonlEventStore

    # Run Journal Store v1 (new)
    from genus.memory import RunHeader, JournalEvent, ArtifactRecord
    from genus.memory import JsonlRunStore, RunJournal
"""

from genus.memory.event_store import EventStore
from genus.memory.jsonl_event_store import EventEnvelope, JsonlEventStore
from genus.memory.models import ArtifactRecord, JournalEvent, RunHeader
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore

__all__ = [
    # EventStore
    "EventStore",
    "EventEnvelope",
    "JsonlEventStore",
    # Run Journal Store v1
    "RunHeader",
    "JournalEvent",
    "ArtifactRecord",
    "JsonlRunStore",
    "RunJournal",
]

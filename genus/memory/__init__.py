"""
Memory 2.0 – append-only EventStore and Run Journal Store for GENUS.

Public API::

    # EventStore (existing)
    from genus.memory import EventEnvelope, EventStore, JsonlEventStore

    # Run Journal Store v1 (new)
    from genus.memory import RunHeader, JournalEvent, ArtifactRecord
    from genus.memory import JsonlRunStore, RunJournal

    # E2: Cross-Run Retrieval
    from genus.memory import query_runs

    # E2: Tool Memory
    from genus.memory import ToolMemoryIndex, ToolUsageStat

    # E2: Episodic Context Builder
    from genus.memory import build_run_summary, build_episodic_context, format_context_as_text
"""

from genus.memory.context_builder import (
    build_episodic_context,
    build_run_summary,
    format_context_as_text,
)
from genus.memory.event_store import EventStore
from genus.memory.jsonl_event_store import EventEnvelope, JsonlEventStore
from genus.memory.models import ArtifactRecord, JournalEvent, RunHeader
from genus.memory.query import query_runs
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore
from genus.memory.tool_memory import ToolMemoryIndex, ToolUsageStat

__all__ = [
    # EventStore (legacy)
    "EventStore",
    "EventEnvelope",
    "JsonlEventStore",
    # Run Journal Store v1
    "RunHeader",
    "JournalEvent",
    "ArtifactRecord",
    "JsonlRunStore",
    "RunJournal",
    # E2: Cross-Run Retrieval
    "query_runs",
    # E2: Tool Memory
    "ToolMemoryIndex",
    "ToolUsageStat",
    # E2: Episodic Context Builder
    "build_run_summary",
    "build_episodic_context",
    "format_context_as_text",
]

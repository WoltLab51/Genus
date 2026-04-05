"""
EventStore – abstract interface for the GENUS append-only event log.

All concrete implementations (e.g. :class:`~genus.memory.jsonl_event_store.JsonlEventStore`)
must satisfy this interface.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Iterator, List, Optional

if TYPE_CHECKING:
    from genus.memory.jsonl_event_store import EventEnvelope


class EventStore(ABC):
    """Minimal append-only event store interface.

    Events are persisted per ``run_id``.  Implementations must be safe to
    call from a single async context (no concurrent writers assumed for
    this milestone).
    """

    @abstractmethod
    def append(self, envelope: "EventEnvelope") -> None:
        """Persist *envelope* to the store.

        Args:
            envelope: The :class:`EventEnvelope` to append.
        """

    @abstractmethod
    def iter(self, run_id: str) -> Iterator["EventEnvelope"]:
        """Iterate over all events for *run_id* in insertion order.

        Args:
            run_id: The run identifier to query.

        Yields:
            :class:`EventEnvelope` objects in the order they were appended.
        """

    @abstractmethod
    def latest(
        self,
        run_id: str,
        topic: Optional[str] = None,
    ) -> Optional["EventEnvelope"]:
        """Return the most-recently appended event for *run_id*.

        Args:
            run_id: The run identifier to query.
            topic:  If given, only consider events with this topic.

        Returns:
            The latest :class:`EventEnvelope`, or ``None`` if no matching
            event exists.
        """

    def list(self, run_id: str) -> List["EventEnvelope"]:
        """Return all events for *run_id* as an in-memory list.

        This is a convenience wrapper around :meth:`iter`.

        Args:
            run_id: The run identifier to query.

        Returns:
            Ordered list of :class:`EventEnvelope` objects.
        """
        return list(self.iter(run_id))

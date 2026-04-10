"""
Topic Registry

Provides a central, in-memory registry of all named topics used by the GENUS
MessageBus.  The registry is intentionally separate from the MessageBus itself
so that topic governance (ownership, direction, stability) can be enforced at
the application layer without modifying the low-level pub/sub infrastructure.

In the GENUS flow this module sits between the individual domain-specific
topic constant files (e.g. ``genus/dev/topics.py``, ``genus/run/topics.py``)
and any component that wants to assert that a topic is known before using it.

Typical usage::

    from genus.communication.topic_registry import topic_registry
    topic_registry.assert_registered("quality.scored")   # raises if unknown

    # Or opt-in to allow dynamic / debug topics:
    topic_registry.assert_registered("debug.trace", allow_unregistered=True)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class UnknownTopicError(Exception):
    """Raised when a required topic is not present in the TopicRegistry."""


# ---------------------------------------------------------------------------
# TopicEntry
# ---------------------------------------------------------------------------


@dataclass
class TopicEntry:
    """Metadata record for a single registered topic.

    Attributes:
        topic: The fully-qualified topic string (e.g. ``"quality.scored"``).
        owner: The agent or module that "owns" (produces) this topic.
        direction: One of ``"publish"``, ``"subscribe"``, or ``"both"``.
        domain: High-level domain label.  Allowed values: ``"quality"``,
            ``"security"``, ``"growth"``, ``"dev"``, ``"feedback"``,
            ``"run"``, ``"tools"``, ``"meta"``.
        description: Human-readable summary of what this topic carries.
        stable: When ``True`` the topic string is considered API-stable and
            must not be renamed without a version bump.
        version: Monotonically increasing version counter for backward
            compatibility tracking.
    """

    topic: str
    owner: str
    direction: str
    domain: str
    description: str
    stable: bool = True
    version: int = 1


# ---------------------------------------------------------------------------
# TopicRegistry
# ---------------------------------------------------------------------------


class TopicRegistry:
    """In-memory registry of known GENUS topics.

    Provides lookup, filtering, and optional enforcement of topic registration.
    The ``MessageBus`` itself does *not* call ``assert_registered``; that check
    is opt-in for modules that require strict topic governance.

    Usage::

        registry = TopicRegistry()
        registry.register(TopicEntry(
            topic="quality.scored",
            owner="QualityAgent",
            direction="publish",
            domain="quality",
            description="Published after quality evaluation.",
        ))
        registry.assert_registered("quality.scored")   # passes
        registry.assert_registered("unknown.topic")    # raises UnknownTopicError
    """

    def __init__(self) -> None:
        self._entries: Dict[str, TopicEntry] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, entry: TopicEntry) -> None:
        """Register a topic entry.

        Args:
            entry: The ``TopicEntry`` to register.

        Raises:
            ValueError: If a topic with the same name is already registered.
        """
        if entry.topic in self._entries:
            raise ValueError(
                "Topic {!r} is already registered in this TopicRegistry.".format(
                    entry.topic
                )
            )
        self._entries[entry.topic] = entry

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def all_topics(self) -> List[TopicEntry]:
        """Return all registered topic entries (unordered)."""
        return list(self._entries.values())

    def topics_for_domain(self, domain: str) -> List[TopicEntry]:
        """Return all entries whose ``domain`` matches *domain*.

        Args:
            domain: The domain label to filter by.

        Returns:
            A list of matching ``TopicEntry`` objects.
        """
        return [e for e in self._entries.values() if e.domain == domain]

    def owner_of(self, topic: str) -> Optional[str]:
        """Return the owner of *topic*, or ``None`` if not registered.

        Args:
            topic: The topic string to look up.

        Returns:
            The ``owner`` field of the matching entry, or ``None``.
        """
        entry = self._entries.get(topic)
        return entry.owner if entry is not None else None

    def is_registered(self, topic: str) -> bool:
        """Return ``True`` if *topic* is present in the registry.

        Args:
            topic: The topic string to check.
        """
        return topic in self._entries

    def assert_registered(
        self,
        topic: str,
        *,
        allow_unregistered: bool = False,
    ) -> None:
        """Assert that *topic* is registered.

        Args:
            topic: The topic string to verify.
            allow_unregistered: When ``True`` this method is a no-op, even if
                the topic is not registered.  Useful for debug topics and
                dynamically generated topics.

        Raises:
            UnknownTopicError: If *topic* is not registered and
                ``allow_unregistered`` is ``False``.
        """
        if allow_unregistered:
            return
        if topic not in self._entries:
            raise UnknownTopicError(
                "Topic {!r} is not registered in the TopicRegistry. "
                "Register it or pass allow_unregistered=True to skip "
                "this check.".format(topic)
            )

    def get(self, topic: str) -> Optional[TopicEntry]:
        """Return the ``TopicEntry`` for *topic*, or ``None`` if not found.

        Args:
            topic: The topic string to look up.
        """
        return self._entries.get(topic)

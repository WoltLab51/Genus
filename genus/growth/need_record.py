"""
Need Record

Defines the ``NeedRecord`` dataclass that represents a single observed gap or
need within the GENUS ecosystem.  NeedRecords are created and maintained by the
``NeedObserver`` and consumed by the ``GrowthOrchestrator``.

In the GENUS growth flow this module sits between the observation layer
(``NeedObserver`` listens for signals on the MessageBus) and the orchestration
layer (``GrowthOrchestrator`` decides whether to commission a new agent build).

A NeedRecord accumulates ``trigger_count`` as the same need is observed
repeatedly.  Once ``trigger_count >= StabilityRules.min_trigger_count_before_build``
the record is promoted to status ``"queued"`` and the ``GrowthOrchestrator``
receives a ``need.identified`` event to act on.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


def _utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class NeedRecord:
    """A single observed need or capability gap within GENUS.

    Attributes:
        need_id: UUID uniquely identifying this need.  Auto-generated if empty.
        domain: The ``AgentDomain`` value as a plain string (e.g. ``"family"``).
        need_description: Human-readable description of the gap.
        trigger_count: How many times this need has been observed.
        first_seen_at: ISO 8601 UTC timestamp when the need was first observed.
            Set automatically on creation if empty.
        last_seen_at: ISO 8601 UTC timestamp of the most recent observation.
            Updated on every call to :meth:`increment_trigger`.
        status: Lifecycle status of this need.  One of
            ``"observed"`` | ``"queued"`` | ``"building"`` | ``"fulfilled"``
            | ``"rejected"`` | ``"quality_blocked"``.
        source_topics: The MessageBus topics that triggered this need.  Each
            topic is listed at most once.
        metadata: Arbitrary additional data attached by the observer.
    """

    need_id: str = field(default_factory=lambda: "")
    domain: str = ""
    need_description: str = ""
    trigger_count: int = 0
    first_seen_at: str = ""
    last_seen_at: str = ""
    status: str = "observed"
    source_topics: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.need_id:
            self.need_id = str(uuid.uuid4())
        now = _utc_now()
        if not self.first_seen_at:
            self.first_seen_at = now
        if not self.last_seen_at:
            self.last_seen_at = now

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def increment_trigger(self, source_topic: str) -> None:
        """Increment the trigger count and record the source topic.

        Args:
            source_topic: The MessageBus topic that caused this trigger.
        """
        self.trigger_count += 1
        self.last_seen_at = _utc_now()
        if source_topic not in self.source_topics:
            self.source_topics.append(source_topic)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_ready_for_build(self, min_trigger_count: int) -> bool:
        """Return ``True`` when this need is ready to trigger a build.

        A need is ready when its trigger count has reached the minimum
        threshold **and** its status is still ``"observed"``.  Once promoted
        to ``"queued"`` or any other terminal state, this method returns
        ``False`` to prevent duplicate builds.

        Args:
            min_trigger_count: The minimum number of triggers required.

        Returns:
            ``True`` when both conditions are met; ``False`` otherwise.
        """
        return self.trigger_count >= min_trigger_count and self.status == "observed"

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_payload(self) -> Dict[str, Any]:
        """Serialise this record to a plain dict suitable for a MessageBus payload.

        Returns:
            A dict containing all fields of this NeedRecord.
        """
        return {
            "need_id": self.need_id,
            "domain": self.domain,
            "need_description": self.need_description,
            "trigger_count": self.trigger_count,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "status": self.status,
            "source_topics": list(self.source_topics),
            "metadata": dict(self.metadata),
        }

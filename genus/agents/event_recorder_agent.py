"""
EventRecorderAgent – persists whitelisted message-bus events to the EventStore.

Default whitelisted topics:
- ``analysis.completed``
- ``quality.scored``
- ``decision.made``
- ``outcome.recorded``

Raw data topics (e.g. ``data.collected``) are intentionally **not** in the
default whitelist to avoid persisting sensitive or large payloads.

``data.sanitized`` is **not** in the default whitelist either.  Operators can
opt in by passing it via the ``record_topics`` constructor argument or via
the ``GENUS_RECORD_TOPICS`` environment variable:

    .. code-block:: python

        from genus.agents.event_recorder_agent import DEFAULT_RECORD_TOPICS, EventRecorderAgent

        recorder = EventRecorderAgent(
            message_bus=bus,
            event_store=store,
            record_topics=[*DEFAULT_RECORD_TOPICS, "data.sanitized"],
        )

    Or via environment variable (comma-separated, no spaces)::

        GENUS_RECORD_TOPICS=analysis.completed,quality.scored,decision.made,outcome.recorded,data.sanitized

Missing ``run_id`` handling:
    If ``run_id`` is absent from ``message.metadata``, the event is
    recorded under run_id ``"unknown"`` and the envelope metadata will
    contain ``{"run_id_missing": True}``.  A warning is also logged so
    that operators can detect and fix missing run tracking.
"""

import logging
import os
from typing import List, Optional

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.core.run import get_run_id
from genus.memory.event_store import EventStore
from genus.memory.jsonl_event_store import EventEnvelope

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_RECORD_TOPICS: List[str] = [
    "analysis.completed",
    "quality.scored",
    "decision.made",
    "outcome.recorded",
]

#: Environment variable name for overriding the recorder whitelist at runtime.
#: Value must be a comma-separated list of topic strings with no spaces.
#: Example: ``analysis.completed,quality.scored,decision.made,outcome.recorded,data.sanitized``
_ENV_RECORD_TOPICS = "GENUS_RECORD_TOPICS"


def _resolve_record_topics(record_topics: Optional[List[str]]) -> List[str]:
    """Return the effective whitelist for this recorder instance.

    Priority (highest first):

    1. Explicit *record_topics* constructor argument.
    2. ``GENUS_RECORD_TOPICS`` environment variable (comma-separated).
    3. :data:`DEFAULT_RECORD_TOPICS`.

    Args:
        record_topics: The value passed to the constructor, or ``None``.

    Returns:
        Deduplicated list of topic strings preserving order.
    """
    if record_topics is not None:
        return list(record_topics)

    env_value = os.environ.get(_ENV_RECORD_TOPICS, "").strip()
    if env_value:
        return [t.strip() for t in env_value.split(",") if t.strip()]

    return list(DEFAULT_RECORD_TOPICS)


# ---------------------------------------------------------------------------
# EventRecorderAgent
# ---------------------------------------------------------------------------

class EventRecorderAgent(Agent):
    """Subscribes to whitelisted topics and appends every received message
    as an :class:`~genus.memory.jsonl_event_store.EventEnvelope` into the
    :class:`~genus.memory.event_store.EventStore`.

    Args:
        message_bus:    The :class:`~genus.communication.message_bus.MessageBus`
                        to subscribe to.
        event_store:    The :class:`~genus.memory.event_store.EventStore`
                        implementation to write to.
        record_topics:  Whitelist of topics to record.  Defaults to
                        :data:`DEFAULT_RECORD_TOPICS`.
        agent_id:       Optional explicit agent identifier.
        name:           Optional human-readable agent name.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        event_store: EventStore,
        record_topics: Optional[List[str]] = None,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name or "EventRecorderAgent")
        self._bus = message_bus
        self._store = event_store
        self._record_topics: List[str] = _resolve_record_topics(record_topics)

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Subscribe to all whitelisted topics."""
        for topic in self._record_topics:
            self._bus.subscribe(topic, self.id, self.process_message)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        self._bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def process_message(self, message: Message) -> None:
        """Record *message* as an :class:`EventEnvelope` in the event store.

        If ``run_id`` is missing from ``message.metadata``, the envelope
        is stored under run_id ``"unknown"`` and ``metadata["run_id_missing"]``
        is set to ``True``.
        """
        run_id = get_run_id(message)
        extra_metadata: dict = {}

        if run_id is None:
            logger.warning(
                "EventRecorderAgent received message without run_id "
                "(topic=%s, message_id=%s); recording under run_id='unknown'",
                message.topic,
                message.message_id,
            )
            run_id = "unknown"
            extra_metadata["run_id_missing"] = True

        envelope = EventEnvelope.from_message(
            message,
            run_id=run_id,
            extra_metadata=extra_metadata,
        )
        self._store.append(envelope)

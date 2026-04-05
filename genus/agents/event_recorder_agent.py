"""
EventRecorderAgent – persists whitelisted message-bus events to the EventStore.

Default whitelisted topics:
- ``analysis.completed``
- ``quality.scored``
- ``decision.made``
- ``outcome.recorded``

Raw data topics (e.g. ``data.collected``) are intentionally **not** in the
default whitelist to avoid persisting sensitive or large payloads.

Missing ``run_id`` handling:
    If ``run_id`` is absent from ``message.metadata``, the event is
    recorded under run_id ``"unknown"`` and the envelope metadata will
    contain ``{"run_id_missing": True}``.  A warning is also logged so
    that operators can detect and fix missing run tracking.
"""

import logging
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
        self._record_topics: List[str] = (
            list(record_topics) if record_topics is not None else list(DEFAULT_RECORD_TOPICS)
        )

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

"""
Need Observer

Monitors the GENUS MessageBus for recurring failure and quality signals and
maintains an internal ledger of ``NeedRecord`` objects.  When a need has been
observed often enough (as governed by ``StabilityRules.min_trigger_count_before_build``)
the observer publishes a ``need.identified`` event exactly **once** and
transitions the record to status ``"queued"``.

In the GENUS growth flow the NeedObserver sits between the raw event stream
(MessageBus) and the GrowthOrchestrator.  It abstracts away the noise of
transient errors and surfaces only those patterns that are stable enough to
justify commissioning a new agent.

Topics subscribed:
    - ``feedback.received``: When ``outcome == "failure"`` a need is recorded
      in domain ``"system"`` with description ``"repeated_failure"``.
    - ``run.failed``: Records a need in domain ``"system"`` with description
      ``"run_failure"``.
    - ``quality.scored``: When ``quality_score < 0.55`` records a need in
      domain ``"quality"`` with description ``"low_quality_score"``.

Topics published:
    - ``need.identified``: Emitted once per need when the trigger threshold
      is reached.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.growth.identity_profile import StabilityRules
from genus.growth.need_record import NeedRecord

# Topic constants
_TOPIC_FEEDBACK = "feedback.received"
_TOPIC_RUN_FAILED = "run.failed"
_TOPIC_QUALITY_SCORED = "quality.scored"
_TOPIC_NEED_IDENTIFIED = "need.identified"

# Low-quality threshold for publishing a quality need
_LOW_QUALITY_THRESHOLD = 0.55


class NeedObserver(Agent):
    """Observes MessageBus events and identifies recurring needs.

    The observer maintains a dictionary of :class:`~genus.growth.need_record.NeedRecord`
    instances keyed by ``(domain, need_description)`` tuples.  Each incoming
    relevant event increments the appropriate record.  When the record's
    ``trigger_count`` reaches the ``min_trigger_count_before_build`` threshold
    the record is published as a ``need.identified`` event and its status is
    set to ``"queued"`` so that no further events are emitted for the same need.

    Args:
        message_bus: The MessageBus to subscribe to and publish on.
        stability_rules: The :class:`~genus.growth.identity_profile.StabilityRules`
            governing the minimum trigger count before a build is initiated.
        agent_id: Optional custom agent ID.  Auto-generated if not provided.
        name: Optional human-readable agent name.  Defaults to
            ``"NeedObserver"``.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        stability_rules: StabilityRules,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name or "NeedObserver")
        self._bus = message_bus
        self._stability_rules = stability_rules
        self._needs: Dict[Tuple[str, str], NeedRecord] = {}

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Subscribe to all relevant topics."""
        self._bus.subscribe(_TOPIC_FEEDBACK, self.id, self.process_message)
        self._bus.subscribe(_TOPIC_RUN_FAILED, self.id, self.process_message)
        self._bus.subscribe(_TOPIC_QUALITY_SCORED, self.id, self.process_message)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Transition to RUNNING state."""
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        """Unsubscribe from all topics and transition to STOPPED state."""
        self._bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def process_message(self, message: Message) -> None:
        """Route an incoming message to the correct handler.

        Args:
            message: The incoming MessageBus message.
        """
        topic = message.topic

        if topic == _TOPIC_FEEDBACK:
            outcome = message.payload.get("outcome", "") if isinstance(message.payload, dict) else ""
            if outcome == "failure":
                await self._handle_event(
                    message,
                    domain="system",
                    need_description="repeated_failure",
                    source_topic=topic,
                )

        elif topic == _TOPIC_RUN_FAILED:
            await self._handle_event(
                message,
                domain="system",
                need_description="run_failure",
                source_topic=topic,
            )

        elif topic == _TOPIC_QUALITY_SCORED:
            score = message.payload.get("quality_score", 1.0) if isinstance(message.payload, dict) else 1.0
            if score < _LOW_QUALITY_THRESHOLD:
                await self._handle_event(
                    message,
                    domain="quality",
                    need_description="low_quality_score",
                    source_topic=topic,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_need(self, domain: str, need_description: str) -> NeedRecord:
        """Return the existing NeedRecord for this key or create a new one.

        Args:
            domain: The domain string.
            need_description: The human-readable need description.

        Returns:
            The existing or newly created :class:`~genus.growth.need_record.NeedRecord`.
        """
        key = (domain, need_description)
        if key not in self._needs:
            self._needs[key] = NeedRecord(domain=domain, need_description=need_description)
        return self._needs[key]

    async def _handle_event(
        self,
        message: Message,
        domain: str,
        need_description: str,
        source_topic: str,
    ) -> None:
        """Increment a need and publish ``need.identified`` when the threshold is reached.

        The need is published at most once: after the first publish the status
        is set to ``"queued"`` so subsequent triggers are silently accumulated
        without re-publishing.

        Args:
            message: The originating MessageBus message (used for context).
            domain: The domain of the need.
            need_description: Human-readable description of the need.
            source_topic: The topic that triggered this event.
        """
        need = self._get_or_create_need(domain, need_description)
        need.increment_trigger(source_topic)
        if need.is_ready_for_build(self._stability_rules.min_trigger_count_before_build):
            need.status = "queued"
            await self._publish_need_identified(need)

    async def _publish_need_identified(self, need: NeedRecord) -> None:
        """Publish a ``need.identified`` event for the given NeedRecord.

        Args:
            need: The NeedRecord that has reached the build threshold.
        """
        await self._bus.publish(
            Message(
                topic=_TOPIC_NEED_IDENTIFIED,
                payload=need.to_payload(),
                sender_id=self.id,
            )
        )

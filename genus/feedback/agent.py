"""
FeedbackAgent

Subscribes to ``outcome.recorded`` and writes the feedback signal
into the RunJournal as an event and artifact.

Design principles (GENUS-2.0)
------------------------------
- **Signal only**: Feedback is recorded, not acted upon directly.
  No strategy weights are changed here.
- **Fail-closed logging**: If the journal write fails, a warning is
  logged but the agent continues; the EventRecorderAgent still
  persists the raw event independently.
- **run_id propagation**: The run_id from message metadata is used
  to find the correct journal. If run_id is absent, the message is
  dropped with a warning — no journal write under run_id "unknown".
- **No IO outside journal**: Pure transformation, MessageBus, and
  RunJournal only.

Output
------
For each valid ``outcome.recorded`` message:
1. ``run_journal.log_event(phase="feedback", event_type="feedback.received", ...)``
2. ``run_journal.save_artifact(phase="feedback", artifact_type="feedback_record", ...)``
3. Publish ``feedback.received`` on MessageBus
"""

import logging
from typing import Callable, Optional

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.core.run import get_run_id
from genus.feedback.outcome import validate_outcome_payload
from genus.feedback.topics import FEEDBACK_RECEIVED, OUTCOME_RECORDED
from genus.memory.run_journal import RunJournal

logger = logging.getLogger(__name__)


class FeedbackAgent(Agent):
    """Bridges ``outcome.recorded`` events into the RunJournal.

    Args:
        message_bus:      The shared MessageBus.
        journal_factory:  Callable that takes a run_id (str) and returns
                          a RunJournal for that run. If the factory returns
                          None, the feedback is dropped with a warning.
        agent_id:         Optional explicit agent identifier.
        name:             Optional human-readable name.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        journal_factory: Callable[[str], Optional[RunJournal]],
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name or "FeedbackAgent")
        self._bus = message_bus
        self._journal_factory = journal_factory

    async def initialize(self) -> None:
        self._bus.subscribe(OUTCOME_RECORDED, self.id, self.process_message)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        self._bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message: Message) -> None:
        """Handle an ``outcome.recorded`` message."""
        # 1. Extract and validate run_id
        run_id = get_run_id(message)
        if not run_id or run_id == "unknown":
            logger.warning(
                "FeedbackAgent: dropping outcome.recorded — run_id missing in metadata"
            )
            return

        # 2. Validate payload
        try:
            outcome = validate_outcome_payload(message.payload)
        except (ValueError, TypeError) as exc:
            logger.warning(
                "FeedbackAgent: invalid outcome.recorded payload for run %s: %s",
                run_id, exc,
            )
            return

        # 3. Get journal for this run
        journal = self._journal_factory(run_id)
        if journal is None:
            logger.warning(
                "FeedbackAgent: no journal found for run_id %s — feedback dropped",
                run_id,
            )
            return

        # 4. Write to journal — log_event
        try:
            journal.log_event(
                phase="feedback",
                event_type="feedback.received",
                summary=f"Feedback received: outcome={outcome.outcome}, score_delta={outcome.score_delta}",
                data={
                    "outcome": outcome.outcome,
                    "score_delta": outcome.score_delta,
                    "source": outcome.source,
                    "notes": outcome.notes,
                    "timestamp": outcome.timestamp,
                },
            )
        except Exception as exc:
            logger.warning(
                "FeedbackAgent: journal log_event failed for run %s: %s", run_id, exc
            )

        # 5. Write to journal — save_artifact
        try:
            journal.save_artifact(
                phase="feedback",
                artifact_type="feedback_record",
                payload=outcome.to_message_payload(),
            )
        except Exception as exc:
            logger.warning(
                "FeedbackAgent: journal save_artifact failed for run %s: %s", run_id, exc
            )

        # 6. Publish feedback.received (observability — no side effects)
        await self._bus.publish(
            Message(
                topic=FEEDBACK_RECEIVED,
                payload={
                    "run_id": run_id,
                    "outcome": outcome.outcome,
                    "score_delta": outcome.score_delta,
                    "source": outcome.source,
                },
                sender_id=self.id,
                metadata={"run_id": run_id},
            )
        )

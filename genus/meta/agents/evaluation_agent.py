"""
Evaluation Agent

Subscribes to dev.loop.completed and dev.loop.failed events.
On either event, loads run data from RunJournal, evaluates the run,
and publishes meta.evaluation.completed event.

This agent is read-only except for:
- Writing evaluation artifacts to RunJournal (allowed)
- Publishing messages to MessageBus (allowed)

No file system modifications, no network calls, no external services.
"""

from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from genus.communication.message_bus import Message, MessageBus
from genus.core.run import get_run_id
from genus.dev import topics as dev_topics
from genus.dev.agents.base import DevAgentBase
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore
from genus.meta import events as meta_events
from genus.meta.evaluation_models import EvaluationInput
from genus.meta.evaluator import RunEvaluator


class EvaluationAgent(DevAgentBase):
    """Agent that evaluates runs and publishes evaluation insights.

    Subscribes to dev.loop.completed and dev.loop.failed events.
    For each run completion/failure:
    1. Load run data from RunJournal (header, events, artifacts)
    2. Build EvaluationInput from run data
    3. Evaluate using RunEvaluator
    4. Save EvaluationArtifact to RunJournal
    5. Publish meta.evaluation.completed event

    Args:
        bus: MessageBus instance for pub/sub.
        agent_id: Unique identifier for this agent.
        store: JsonlRunStore for accessing run journals.
        evaluator: Optional RunEvaluator instance (uses default if not provided).

    Example::

        store = JsonlRunStore()
        agent = EvaluationAgent(bus, "evaluation-agent-1", store)
        agent.start()
        # Agent now listens for dev.loop.completed/failed events
    """

    def __init__(
        self,
        bus: MessageBus,
        agent_id: str = "EvaluationAgent",
        store: Optional[JsonlRunStore] = None,
        evaluator: Optional[RunEvaluator] = None,
    ) -> None:
        super().__init__(bus, agent_id)
        self._store = store or JsonlRunStore()
        self._evaluator = evaluator or RunEvaluator()

    def _subscribe_topics(self) -> List[Tuple[str, Callable[[Message], Awaitable[None]]]]:
        """Register handlers for dev loop completion events."""
        return [
            (dev_topics.DEV_LOOP_COMPLETED, self._handle_loop_event),
            (dev_topics.DEV_LOOP_FAILED, self._handle_loop_event),
        ]

    async def _handle_loop_event(self, msg: Message) -> None:
        """Handle dev.loop.completed or dev.loop.failed events.

        Args:
            msg: The dev loop completion/failure message.
        """
        # Extract run_id from message metadata
        run_id = get_run_id(msg)
        if not run_id:
            # Cannot evaluate without run_id
            return

        # Load run data from journal
        journal = RunJournal(run_id, self._store)

        if not journal.exists():
            # Run journal doesn't exist, nothing to evaluate
            return

        try:
            # Build evaluation input from run data
            eval_input = self._build_evaluation_input(journal, msg)

            # Evaluate the run
            artifact = self._evaluator.evaluate(eval_input)

            # Save evaluation artifact to journal
            # Convert dataclass to dict for storage
            artifact_dict = {
                "run_id": artifact.run_id,
                "created_at": artifact.created_at,
                "score": artifact.score,
                "final_status": artifact.final_status,
                "failure_class": artifact.failure_class,
                "root_cause_hint": artifact.root_cause_hint,
                "highlights": artifact.highlights,
                "issues": artifact.issues,
                "recommendations": artifact.recommendations,
                "strategy_recommendations": artifact.strategy_recommendations,
                "evidence": artifact.evidence,
            }

            journal.save_artifact(
                phase="meta",
                artifact_type="evaluation",
                payload=artifact_dict,
            )

            # Log journal event for evaluation completion
            journal.log_event(
                phase="meta",
                event_type="evaluation_completed",
                summary=f"Evaluation completed: score={artifact.score}, "
                        f"failure_class={artifact.failure_class or 'none'}",
                data={
                    "score": artifact.score,
                    "failure_class": artifact.failure_class,
                    "recommendations_count": len(artifact.recommendations),
                },
            )

            # Publish meta.evaluation.completed event
            await self._bus.publish(
                meta_events.meta_evaluation_completed_message(
                    run_id=run_id,
                    sender_id=self.agent_id,
                    score=artifact.score,
                    failure_class=artifact.failure_class,
                    summary=f"Score: {artifact.score}/100",
                )
            )

        except Exception as e:
            # Log error but don't fail - evaluation is best-effort
            # In production, might want to log this to journal
            pass

    def _build_evaluation_input(
        self,
        journal: RunJournal,
        trigger_msg: Message,
    ) -> EvaluationInput:
        """Build EvaluationInput from run journal data.

        Args:
            journal: The RunJournal for the run.
            trigger_msg: The message that triggered evaluation.

        Returns:
            EvaluationInput with run data.
        """
        # Load header for goal
        header = journal.get_header()
        goal = header.goal if header else None

        # Determine final status from trigger message topic
        final_status = "completed" if trigger_msg.topic == dev_topics.DEV_LOOP_COMPLETED else "failed"

        # Count iterations from fix events
        fix_events = journal.get_events(event_type="started", phase="fix")
        iterations_used = len(fix_events)

        # Load test report artifacts
        test_artifact_ids = journal.list_artifacts(artifact_type="test_report")
        test_reports = []
        for artifact_id in test_artifact_ids:
            artifact = journal.load_artifact(artifact_id)
            if artifact:
                test_reports.append(artifact.payload)

        # Build evaluation input
        eval_input = EvaluationInput(
            run_id=journal.run_id,
            final_status=final_status,
            iterations_used=iterations_used,
            test_reports=test_reports,
            goal=goal,
            github=None,  # TODO: Add GitHub context when available
            events=[],  # Could add subset of events if needed
        )

        return eval_input

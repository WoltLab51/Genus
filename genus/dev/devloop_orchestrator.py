"""
DevLoop Orchestrator

Coordinates autonomous dev-loop execution by publishing ``*.requested``
events and awaiting ``*.completed`` or ``*.failed`` responses with
deterministic correlation via ``phase_id``.

**This orchestrator now uses real await logic with timeout handling.**
Builder and Reviewer agents must respond on the appropriate topics with
matching ``run_id`` (in metadata) and ``phase_id`` (in payload).

Usage::

    orchestrator = DevLoopOrchestrator(bus, timeout_s=30.0)
    await orchestrator.run(run_id, goal="implement feature X")

Typical flow::

    dev.loop.started
      └─► dev.plan.requested (with phase_id)
            └─► await dev.plan.completed (matching phase_id)
                  └─► dev.implement.requested (with phase_id)
                        └─► await dev.implement.completed (matching phase_id)
                              └─► dev.test.requested (with phase_id)
                                    └─► await dev.test.completed (matching phase_id)
                                          └─► dev.review.requested (with phase_id)
                                                └─► await dev.review.completed (matching phase_id)
                                                      └─► [ask user?]
                                                            └─► dev.fix.requested (if fixes needed)
                                                                  └─► await dev.fix.completed
                                                                        └─► dev.loop.completed

If any phase fails or times out, the orchestrator publishes ``dev.loop.failed``
and terminates.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from genus.communication.message_bus import MessageBus
from genus.dev import events, topics
from genus.dev.policy import should_ask_user
from genus.dev.runtime import (
    listen_for_dev_response,
    DevResponseFailedError,
    DevResponseTimeoutError,
)
from genus.memory.run_journal import RunJournal

if TYPE_CHECKING:
    from genus.strategy.selector import StrategySelector

logger = logging.getLogger(__name__)


def _derive_recommendations(test_report: dict) -> list:
    """Derive strategy recommendations from a test report.

    Args:
        test_report: Test phase report dict (may include ``failing_tests``,
                     ``timed_out``, etc.).

    Returns:
        List of strategy recommendation strings.
    """
    if test_report.get("failing_tests"):
        return ["target_failing_test_first"]
    if test_report.get("timed_out"):
        return ["increase_timeout_once"]
    return []


class DevLoopOrchestrator:
    """Orchestrator that coordinates dev-loop phases with real await logic.

    Publishes ``*.requested`` events for each phase and awaits responses
    using :func:`~genus.dev.runtime.await_dev_response`. Each phase is
    correlated by a unique ``phase_id`` to ensure deterministic matching.

    The public entrypoint is the async :meth:`run` coroutine.  There is no
    synchronous wrapper: callers must ``await`` this method inside their own
    event loop.

    Args:
        bus:                   The shared :class:`~genus.communication.message_bus.MessageBus`
                               instance used to publish and subscribe.
        sender_id:             Identifier of this orchestrator (included in every message).
        timeout_s:             Default timeout in seconds for awaiting phase responses.
        max_iterations:        Maximum number of fix iterations if tests fail (default: 3).
        commit_each_iteration: Whether to commit after each fix iteration (default: True).
        run_journal:           Required :class:`~genus.memory.run_journal.RunJournal` instance.
                               All phase events and artifacts are written here.
                               This is the single source of truth for this run.
        strategy_selector:     Optional :class:`~genus.strategy.selector.StrategySelector`
                               instance. When provided, ``select_strategy()`` is called
                               before each fix iteration and the decision is embedded in
                               the ``dev.fix.requested`` payload.  When ``None`` (default)
                               the orchestrator behaves exactly as before (backwards-
                               compatible).
    """

    def __init__(
        self,
        bus: MessageBus,
        sender_id: str = "DevLoopOrchestrator",
        timeout_s: float = 30.0,
        max_iterations: int = 3,
        commit_each_iteration: bool = True,
        *,
        run_journal: RunJournal,
        strategy_selector: "Optional[StrategySelector]" = None,
    ) -> None:
        self._bus = bus
        self._sender_id = sender_id
        self._timeout_s = timeout_s
        self._max_iterations = max_iterations
        self._commit_each_iteration = commit_each_iteration
        self._strategy_selector = strategy_selector
        self._run_journal = run_journal

    # ------------------------------------------------------------------
    # Public async entrypoint
    # ------------------------------------------------------------------

    async def run(
        self,
        run_id: str,
        goal: str,
        requirements: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Execute the full dev-loop with real await logic.

        Publishes ``*.requested`` events and awaits responses for each phase.
        Uses ``phase_id`` correlation to match request/response pairs.
        Applies the Ask/Stop policy after review and terminates if necessary.

        Args:
            run_id:       Unique run identifier for this loop.
            goal:         Human-readable goal/objective.
            requirements: Optional list of acceptance requirements.
            constraints:  Optional list of constraints.
            context:      Optional context dict (e.g. repo, branch); always
                          normalised to an empty dict if ``None``.

        Raises:
            DevResponseFailedError: If any phase fails.
            DevResponseTimeoutError: If any phase times out.
        """
        try:
            # Publish loop started
            await self._bus.publish(
                events.dev_loop_started_message(
                    run_id, self._sender_id, goal, context=context
                )
            )
            try:
                self._run_journal.log_event(
                    phase="loop",
                    event_type="started",
                    summary=f"Dev loop started: {goal}",
                    data={"goal": goal, "context": context or {}},
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("journal write failed: %s", exc)

            # -- Planning phase --
            plan_req = events.dev_plan_requested_message(
                run_id,
                self._sender_id,
                requirements=requirements,
                constraints=constraints,
            )
            plan_phase_id = plan_req.payload["phase_id"]

            listener = listen_for_dev_response(
                self._bus,
                run_id=run_id,
                phase_id=plan_phase_id,
                completed_topic=topics.DEV_PLAN_COMPLETED,
                failed_topic=topics.DEV_PLAN_FAILED,
            )
            try:
                await self._bus.publish(plan_req)
                plan_resp = await listener.wait(self._timeout_s)
            finally:
                listener.close()

            plan = plan_resp.payload["plan"]
            try:
                self._run_journal.save_artifact(
                    phase="plan",
                    artifact_type="plan",
                    payload=plan,
                    phase_id=plan_phase_id,
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("journal write failed: %s", exc)

            # -- Implementation phase (iteration 0) --
            iteration = 0
            impl_req = events.dev_implement_requested_message(
                run_id, self._sender_id, plan,
                payload={"iteration": iteration}
            )
            impl_phase_id = impl_req.payload["phase_id"]

            listener = listen_for_dev_response(
                self._bus,
                run_id=run_id,
                phase_id=impl_phase_id,
                completed_topic=topics.DEV_IMPLEMENT_COMPLETED,
                failed_topic=topics.DEV_IMPLEMENT_FAILED,
            )
            try:
                await self._bus.publish(impl_req)
                impl_resp = await listener.wait(self._timeout_s)
            finally:
                listener.close()

            # -- Iterative test-fix loop --
            while iteration <= self._max_iterations:
                # -- Testing phase --
                test_req = events.dev_test_requested_message(
                    run_id, self._sender_id,
                    payload={"iteration": iteration}
                )
                test_phase_id = test_req.payload["phase_id"]

                listener = listen_for_dev_response(
                    self._bus,
                    run_id=run_id,
                    phase_id=test_phase_id,
                    completed_topic=topics.DEV_TEST_COMPLETED,
                    failed_topic=topics.DEV_TEST_FAILED,
                )
                try:
                    await self._bus.publish(test_req)
                    test_resp = await listener.wait(self._timeout_s)
                finally:
                    listener.close()

                # Check if tests passed
                test_report = test_resp.payload.get("report", {})
                tests_passed = (
                    test_report.get("failed", 0) == 0
                    and len(test_report.get("failing_tests", [])) == 0
                )

                if tests_passed:
                    # Tests passed, continue to review
                    break

                # Tests failed - log to journal
                try:
                    self._run_journal.log_event(
                        phase="test",
                        event_type="test_failed",
                        summary=test_report.get("summary", "Tests failed"),
                        phase_id=test_phase_id,
                        data={"report": test_report, "iteration": iteration},
                    )
                except Exception as exc:  # pragma: no cover
                    logger.warning("journal write failed: %s", exc)

                # Tests failed - check if we can iterate
                if iteration >= self._max_iterations:
                    # Max iterations reached
                    reason = f"Max iterations ({self._max_iterations}) reached. Tests still failing: {test_report.get('summary', 'unknown')}"
                    await self._bus.publish(
                        events.dev_loop_failed_message(
                            run_id,
                            self._sender_id,
                            reason,
                        )
                    )
                    try:
                        self._run_journal.log_event(
                            phase="loop",
                            event_type="failed",
                            summary=reason,
                        )
                    except Exception as exc:  # pragma: no cover
                        logger.warning("journal write failed: %s", exc)
                    return

                # -- Fix phase --
                iteration += 1
                findings = [
                    {
                        "type": "test_failure",
                        "message": test_report.get("summary", "Tests failed"),
                        "failing_tests": test_report.get("failing_tests", []),
                        "report": test_report,
                    }
                ]

                # Strategy selection (optional — only when selector is provided)
                strategy_payload: Dict[str, Any] = {}
                if self._strategy_selector is not None:
                    failure_class = test_report.get("failure_class")
                    if failure_class is None:
                        failure_class = "test_failure"

                    evaluation_artifact = {
                        "failure_class": failure_class,
                        "strategy_recommendations": _derive_recommendations(test_report),
                        "score": 0,
                    }

                    strategy_decision = self._strategy_selector.select_strategy(
                        run_id=run_id,
                        phase="fix",
                        iteration=iteration,
                        evaluation_artifact=evaluation_artifact,
                    )
                    strategy_payload = {
                        "strategy": strategy_decision.selected_playbook,
                        "strategy_reason": strategy_decision.reason,
                    }

                    try:
                        from genus.strategy.journal_integration import log_strategy_decision
                        log_strategy_decision(self._run_journal, strategy_decision)
                    except Exception as exc:  # pragma: no cover
                        logger.warning("strategy decision could not be logged to journal: %s", exc)

                fix_req = events.dev_fix_requested_message(
                    run_id, self._sender_id, findings,
                    payload={"iteration": iteration, **strategy_payload}
                )
                fix_phase_id = fix_req.payload["phase_id"]

                listener = listen_for_dev_response(
                    self._bus,
                    run_id=run_id,
                    phase_id=fix_phase_id,
                    completed_topic=topics.DEV_FIX_COMPLETED,
                    failed_topic=topics.DEV_FIX_FAILED,
                )
                try:
                    await self._bus.publish(fix_req)
                    fix_resp = await listener.wait(self._timeout_s)
                finally:
                    listener.close()

                try:
                    self._run_journal.log_event(
                        phase="fix",
                        event_type="fix_completed",
                        summary="Fix iteration completed",
                        phase_id=fix_phase_id,
                        data={"iteration": iteration},
                    )
                except Exception as exc:  # pragma: no cover
                    logger.warning("journal write failed: %s", exc)

                # Fix completed, loop back to test

            # -- Review phase --
            review_req = events.dev_review_requested_message(run_id, self._sender_id)
            review_phase_id = review_req.payload["phase_id"]

            listener = listen_for_dev_response(
                self._bus,
                run_id=run_id,
                phase_id=review_phase_id,
                completed_topic=topics.DEV_REVIEW_COMPLETED,
                failed_topic=topics.DEV_REVIEW_FAILED,
            )
            try:
                await self._bus.publish(review_req)
                review_resp = await listener.wait(self._timeout_s)
            finally:
                listener.close()

            review = review_resp.payload["review"]
            try:
                self._run_journal.save_artifact(
                    phase="review",
                    artifact_type="review",
                    payload=review,
                    phase_id=review_phase_id,
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("journal write failed: %s", exc)

            # -- Ask/Stop policy gate --
            ask, reason = should_ask_user(
                findings=review.get("findings", []),
                risks=plan.get("risks", []),
                scope_change=False,
                security_impact=False,
            )
            if ask:
                fail_reason = f"Awaiting operator: {reason}"
                await self._bus.publish(
                    events.dev_loop_failed_message(
                        run_id, self._sender_id, fail_reason
                    )
                )
                try:
                    self._run_journal.log_event(
                        phase="loop",
                        event_type="failed",
                        summary=fail_reason,
                    )
                except Exception as exc:  # pragma: no cover
                    logger.warning("journal write failed: %s", exc)
                return

            # -- Loop completed --
            await self._bus.publish(
                events.dev_loop_completed_message(
                    run_id,
                    self._sender_id,
                    summary="Dev loop completed successfully.",
                )
            )
            try:
                self._run_journal.log_event(
                    phase="loop",
                    event_type="completed",
                    summary="Dev loop completed successfully.",
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("journal write failed: %s", exc)

        except (DevResponseFailedError, DevResponseTimeoutError) as exc:
            # Any phase failure or timeout -> publish loop failed
            await self._bus.publish(
                events.dev_loop_failed_message(
                    run_id, self._sender_id, str(exc)
                )
            )
            try:
                self._run_journal.log_event(
                    phase="loop",
                    event_type="failed",
                    summary=str(exc),
                )
            except Exception as journal_exc:  # pragma: no cover
                logger.warning("journal write failed: %s", journal_exc)
            raise

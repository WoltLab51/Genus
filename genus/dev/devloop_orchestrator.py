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
from typing import Any, Dict, List, Optional

from genus.communication.message_bus import MessageBus
from genus.dev import events, topics
from genus.dev.policy import should_ask_user
from genus.dev.runtime import (
    listen_for_dev_response,
    DevResponseFailedError,
    DevResponseTimeoutError,
)


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
        strategy_selector:     Optional :class:`~genus.strategy.selector.StrategySelector`
                               instance. When provided, ``select_strategy()`` is called
                               before each fix iteration and the decision is embedded in
                               the ``dev.fix.requested`` payload.  When ``None`` (default)
                               the orchestrator behaves exactly as before (backwards-
                               compatible).
        run_journal:           Optional RunJournal for logging strategy decisions.
                               Used only when ``strategy_selector`` is also provided.
    """

    def __init__(
        self,
        bus: MessageBus,
        sender_id: str = "DevLoopOrchestrator",
        timeout_s: float = 30.0,
        max_iterations: int = 3,
        commit_each_iteration: bool = True,
        strategy_selector: Optional[Any] = None,
        run_journal: Optional[Any] = None,
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

                # Tests failed - check if we can iterate
                if iteration >= self._max_iterations:
                    # Max iterations reached
                    await self._bus.publish(
                        events.dev_loop_failed_message(
                            run_id,
                            self._sender_id,
                            f"Max iterations ({self._max_iterations}) reached. Tests still failing: {test_report.get('summary', 'unknown')}",
                        )
                    )
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

                    if self._run_journal is not None:
                        try:
                            from genus.strategy.journal_integration import log_strategy_decision
                            log_strategy_decision(self._run_journal, strategy_decision)
                        except Exception:
                            pass

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

            # -- Ask/Stop policy gate --
            ask, reason = should_ask_user(
                findings=review.get("findings", []),
                risks=plan.get("risks", []),
                scope_change=False,
                security_impact=False,
            )
            if ask:
                await self._bus.publish(
                    events.dev_loop_failed_message(
                        run_id, self._sender_id, f"Awaiting operator: {reason}"
                    )
                )
                return

            # -- Loop completed --
            await self._bus.publish(
                events.dev_loop_completed_message(
                    run_id,
                    self._sender_id,
                    summary="Dev loop completed successfully.",
                )
            )

        except (DevResponseFailedError, DevResponseTimeoutError) as exc:
            # Any phase failure or timeout -> publish loop failed
            await self._bus.publish(
                events.dev_loop_failed_message(
                    run_id, self._sender_id, str(exc)
                )
            )
            raise

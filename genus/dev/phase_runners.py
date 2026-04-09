"""
PhaseRunners — one class per dev-loop phase.

Each runner handles:
- Publishing the *.requested message
- Subscribing and awaiting the *.completed / *.failed response
- Writing the result artifact to the journal
- Returning a structured result (or raising on failure/timeout)

All runners use the listen-before-publish pattern from genus.dev.runtime.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from genus.dev import events, topics
from genus.dev.run_context import RunContext
from genus.dev.runtime import listen_for_dev_response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _derive_recommendations(test_report: dict) -> list:
    """Derive strategy recommendations from a test report.

    Args:
        test_report: Test phase report dict.

    Returns:
        List of recommendation strings.
    """
    if test_report.get("failing_tests"):
        return ["target_failing_test_first"]
    if test_report.get("timed_out"):
        return ["increase_timeout_once"]
    return []


# ---------------------------------------------------------------------------
# PlanPhaseRunner
# ---------------------------------------------------------------------------

class PlanPhaseRunner:
    """Runs the planning phase.

    Publishes dev.plan.requested, awaits dev.plan.completed,
    saves the plan artifact to the journal.

    Returns:
        The plan dict from the planner agent's response.

    Raises:
        ValueError: If the plan payload is empty.
        DevResponseFailedError: If the agent signals failure.
        DevResponseTimeoutError: If the agent does not respond in time.
    """

    async def run(
        self,
        ctx: RunContext,
        requirements: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute the plan phase.

        Args:
            ctx:          The shared RunContext.
            requirements: Optional acceptance requirements.
            constraints:  Optional constraints.

        Returns:
            The plan dict from the planner agent's response.

        Raises:
            ValueError: If the planner returns an empty plan.
            DevResponseFailedError: If the agent signals failure.
            DevResponseTimeoutError: If the agent does not respond in time.
        """
        plan_payload: Optional[Dict[str, Any]] = None
        if ctx.episodic_context:
            plan_payload = {"episodic_context": ctx.episodic_context}

        plan_req = events.dev_plan_requested_message(
            ctx.run_id,
            ctx.sender_id,
            requirements=requirements,
            constraints=constraints,
            payload=plan_payload,
        )
        phase_id = plan_req.payload["phase_id"]

        listener = listen_for_dev_response(
            ctx.bus,
            run_id=ctx.run_id,
            phase_id=phase_id,
            completed_topic=topics.DEV_PLAN_COMPLETED,
            failed_topic=topics.DEV_PLAN_FAILED,
        )
        try:
            await ctx.bus.publish(plan_req)
            resp = await listener.wait(ctx.timeouts.plan)
        finally:
            listener.close()

        plan = resp.payload.get("plan") or {}
        if not plan:
            raise ValueError("Planning phase returned an empty plan — cannot proceed.")

        try:
            ctx.journal.save_artifact(
                phase="plan",
                artifact_type="plan",
                payload=plan,
                phase_id=phase_id,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("journal write failed (plan artifact): %s", exc)

        return plan


# ---------------------------------------------------------------------------
# ImplPhaseRunner
# ---------------------------------------------------------------------------

class ImplPhaseRunner:
    """Runs the implementation phase.

    Publishes dev.implement.requested, awaits dev.implement.completed.

    Returns:
        The implement response payload dict.

    Raises:
        DevResponseFailedError: If the agent signals failure.
        DevResponseTimeoutError: If the agent does not respond in time.
    """

    async def run(
        self,
        ctx: RunContext,
        plan: Dict[str, Any],
        iteration: int = 0,
    ) -> Dict[str, Any]:
        """Execute the implement phase.

        Args:
            ctx:       The shared RunContext.
            plan:      The plan dict from PlanPhaseRunner.
            iteration: The current iteration index (default 0).

        Returns:
            The implement response payload dict.
        """
        impl_req = events.dev_implement_requested_message(
            ctx.run_id,
            ctx.sender_id,
            plan,
            payload={"iteration": iteration},
        )
        phase_id = impl_req.payload["phase_id"]

        listener = listen_for_dev_response(
            ctx.bus,
            run_id=ctx.run_id,
            phase_id=phase_id,
            completed_topic=topics.DEV_IMPLEMENT_COMPLETED,
            failed_topic=topics.DEV_IMPLEMENT_FAILED,
        )
        try:
            await ctx.bus.publish(impl_req)
            resp = await listener.wait(ctx.timeouts.implement)
        finally:
            listener.close()

        return resp.payload


# ---------------------------------------------------------------------------
# TestPhaseRunner
# ---------------------------------------------------------------------------

class TestPhaseRunner:
    """Runs the test phase.

    Publishes dev.test.requested, awaits dev.test.completed,
    saves the test_report artifact, logs test_failed event if needed.

    Returns:
        Tuple of (test_report dict, tests_passed bool).

    Raises:
        DevResponseFailedError: If the agent signals failure.
        DevResponseTimeoutError: If the agent does not respond in time.
    """

    async def run(
        self,
        ctx: RunContext,
        iteration: int = 0,
    ) -> Tuple[Dict[str, Any], bool]:
        """Execute the test phase.

        Args:
            ctx:       The shared RunContext.
            iteration: The current iteration index.

        Returns:
            Tuple of (test_report dict, tests_passed bool).
        """
        test_req = events.dev_test_requested_message(
            ctx.run_id,
            ctx.sender_id,
            payload={"iteration": iteration},
        )
        phase_id = test_req.payload["phase_id"]

        listener = listen_for_dev_response(
            ctx.bus,
            run_id=ctx.run_id,
            phase_id=phase_id,
            completed_topic=topics.DEV_TEST_COMPLETED,
            failed_topic=topics.DEV_TEST_FAILED,
        )
        try:
            await ctx.bus.publish(test_req)
            resp = await listener.wait(ctx.timeouts.test)
        finally:
            listener.close()

        test_report = resp.payload.get("report", {})

        # Persist test_report as journal artifact
        try:
            ctx.journal.save_artifact(
                phase="test",
                artifact_type="test_report",
                payload=test_report,
                phase_id=phase_id,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("journal write failed (test_report): %s", exc)

        tests_passed = (
            test_report.get("failed", 0) == 0
            and len(test_report.get("failing_tests", [])) == 0
        )

        if not tests_passed:
            try:
                ctx.journal.log_event(
                    phase="test",
                    event_type="test_failed",
                    summary=test_report.get("summary", "Tests failed"),
                    phase_id=phase_id,
                    data={"report": test_report, "iteration": iteration},
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("journal write failed (test_failed event): %s", exc)

        return test_report, tests_passed


# ---------------------------------------------------------------------------
# FixPhaseRunner
# ---------------------------------------------------------------------------

class FixPhaseRunner:
    """Runs the fix phase.

    Publishes dev.fix.requested (with optional strategy payload),
    awaits dev.fix.completed, logs the fix_completed event.

    Returns:
        The fix response payload dict.

    Raises:
        DevResponseFailedError: If the agent signals failure.
        DevResponseTimeoutError: If the agent does not respond in time.
    """

    async def run(
        self,
        ctx: RunContext,
        test_report: Dict[str, Any],
        iteration: int,
    ) -> Dict[str, Any]:
        """Execute the fix phase.

        Args:
            ctx:         The shared RunContext.
            test_report: The failing test report from TestPhaseRunner.
            iteration:   The current fix iteration index (1-based).

        Returns:
            The fix response payload dict.
        """
        findings = [
            {
                "type": "test_failure",
                "message": test_report.get("summary", "Tests failed"),
                "failing_tests": test_report.get("failing_tests", []),
                "report": test_report,
            }
        ]

        strategy_payload: Dict[str, Any] = {}
        if ctx.strategy_selector is not None:
            failure_class = test_report.get("failure_class") or "test_failure"
            evaluation_artifact = {
                "failure_class": failure_class,
                "strategy_recommendations": _derive_recommendations(test_report),
                "score": 0,
            }
            strategy_decision = ctx.strategy_selector.select_strategy(
                run_id=ctx.run_id,
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
                log_strategy_decision(ctx.journal, strategy_decision)
            except Exception as exc:  # pragma: no cover
                logger.warning("strategy decision could not be logged: %s", exc)

        fix_req = events.dev_fix_requested_message(
            ctx.run_id,
            ctx.sender_id,
            findings,
            payload={"iteration": iteration, **strategy_payload},
        )
        phase_id = fix_req.payload["phase_id"]

        listener = listen_for_dev_response(
            ctx.bus,
            run_id=ctx.run_id,
            phase_id=phase_id,
            completed_topic=topics.DEV_FIX_COMPLETED,
            failed_topic=topics.DEV_FIX_FAILED,
        )
        try:
            await ctx.bus.publish(fix_req)
            resp = await listener.wait(ctx.timeouts.fix)
        finally:
            listener.close()

        try:
            ctx.journal.log_event(
                phase="fix",
                event_type="fix_completed",
                summary="Fix iteration completed",
                phase_id=phase_id,
                data={"iteration": iteration},
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("journal write failed (fix_completed event): %s", exc)

        return resp.payload


# ---------------------------------------------------------------------------
# ReviewPhaseRunner
# ---------------------------------------------------------------------------

class ReviewPhaseRunner:
    """Runs the review phase.

    Publishes dev.review.requested, awaits dev.review.completed,
    saves the review artifact to the journal.

    Returns:
        The review dict from the reviewer agent's response.

    Raises:
        DevResponseFailedError: If the agent signals failure.
        DevResponseTimeoutError: If the agent does not respond in time.
    """

    async def run(self, ctx: RunContext) -> Dict[str, Any]:
        """Execute the review phase.

        Args:
            ctx: The shared RunContext.

        Returns:
            The review dict from the reviewer agent's response.
        """
        review_req = events.dev_review_requested_message(ctx.run_id, ctx.sender_id)
        phase_id = review_req.payload["phase_id"]

        listener = listen_for_dev_response(
            ctx.bus,
            run_id=ctx.run_id,
            phase_id=phase_id,
            completed_topic=topics.DEV_REVIEW_COMPLETED,
            failed_topic=topics.DEV_REVIEW_FAILED,
        )
        try:
            await ctx.bus.publish(review_req)
            resp = await listener.wait(ctx.timeouts.review)
        finally:
            listener.close()

        review = resp.payload.get("review", {})

        try:
            ctx.journal.save_artifact(
                phase="review",
                artifact_type="review",
                payload=review,
                phase_id=phase_id,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("journal write failed (review artifact): %s", exc)

        return review

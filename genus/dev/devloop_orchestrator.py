"""
DevLoop Orchestrator Skeleton

Illustrates the message flow for a GENUS autonomous dev loop using the
topic constants and factory functions defined in this package.

**This module does not execute any tools, run subprocesses, or call
external APIs.**  It is a skeleton that shows how the Orchestrator
would publish phase events in sequence, and where the Ask/Stop policy
gate sits.

Usage::

    orchestrator = DevLoopOrchestrator(bus)
    await orchestrator.run(run_id, goal="implement feature X")

Typical flow::

    dev.loop.started
      └─► dev.plan.requested
            └─► dev.plan.completed
                  └─► dev.implement.requested
                        └─► dev.implement.completed
                              └─► dev.test.requested
                                    └─► dev.test.completed
                                          └─► dev.review.requested
                                                └─► dev.review.completed
                                                      └─► [ask user?]
                                                            └─► dev.fix.requested  (if fixes needed)
                                                                  └─► dev.fix.completed
                                                                        └─► dev.loop.completed

If any phase fails, the corresponding ``*.failed`` event is published
and the loop terminates with ``dev.loop.failed``.
"""

from typing import Any, Dict, List, Optional

from genus.communication.message_bus import MessageBus
from genus.dev import events
from genus.dev.policy import should_ask_user


class DevLoopOrchestrator:
    """Skeleton orchestrator that publishes dev-loop phase messages.

    The public entrypoint is the async :meth:`run` coroutine.  There is no
    synchronous wrapper: callers must ``await`` this method inside their own
    event loop.  This keeps the orchestrator side-effect-free when
    instantiated and avoids hidden loop creation.

    Args:
        bus:       The shared :class:`~genus.communication.message_bus.MessageBus`
                   instance used to publish messages.
        sender_id: Identifier of this orchestrator (included in every message).
    """

    def __init__(self, bus: MessageBus, sender_id: str = "DevLoopOrchestrator") -> None:
        self._bus = bus
        self._sender_id = sender_id

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
        """Publish the full dev-loop message sequence (no tool execution).

        This coroutine illustrates the expected message order.  In a real
        implementation each step would await a response from the Builder or
        Reviewer before proceeding.

        Args:
            run_id:       Unique run identifier for this loop.
            goal:         Human-readable goal/objective.
            requirements: Optional list of acceptance requirements.
            constraints:  Optional list of constraints.
            context:      Optional context dict (e.g. repo, branch); always
                          normalised to an empty dict if ``None``.
        """
        await self._bus.publish(
            events.dev_loop_started_message(
                run_id, self._sender_id, goal, context=context
            )
        )

        # -- Planning --
        await self._bus.publish(
            events.dev_plan_requested_message(
                run_id, self._sender_id,
                requirements=requirements,
                constraints=constraints,
            )
        )
        placeholder_plan: Dict[str, Any] = {
            "steps": [],
            "acceptance_criteria": [],
            "risks": [],
        }
        await self._bus.publish(
            events.dev_plan_completed_message(run_id, self._sender_id, placeholder_plan)
        )

        # -- Implementation --
        await self._bus.publish(
            events.dev_implement_requested_message(run_id, self._sender_id, placeholder_plan)
        )
        await self._bus.publish(
            events.dev_implement_completed_message(
                run_id, self._sender_id, "no-op skeleton", []
            )
        )

        # -- Testing --
        await self._bus.publish(
            events.dev_test_requested_message(run_id, self._sender_id)
        )
        placeholder_report: Dict[str, Any] = {
            "passed": 0,
            "failed": 0,
            "duration_s": 0.0,
            "summary": "skeleton – no tests run",
            "failing_tests": [],
        }
        await self._bus.publish(
            events.dev_test_completed_message(run_id, self._sender_id, placeholder_report)
        )

        # -- Review --
        await self._bus.publish(
            events.dev_review_requested_message(run_id, self._sender_id)
        )
        placeholder_review: Dict[str, Any] = {
            "findings": [],
            "severity": "none",
            "required_fixes": [],
        }
        await self._bus.publish(
            events.dev_review_completed_message(run_id, self._sender_id, placeholder_review)
        )

        # -- Ask/Stop policy gate --
        ask, reason = should_ask_user(
            findings=placeholder_review.get("findings", []),
            risks=placeholder_plan.get("risks", []),
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
                run_id, self._sender_id,
                summary="Skeleton loop completed without tool execution.",
            )
        )

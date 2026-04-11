"""
Stub Dev Agent — Phase 6 (Stub Mode)

Responds to all DevLoop phase events (``dev.plan.requested``,
``dev.implement.requested``, ``dev.test.requested``,
``dev.fix.requested``, ``dev.review.requested``) with minimal but
structurally correct payloads so that the
:class:`~genus.dev.devloop_orchestrator.DevLoopOrchestrator` can complete
the entire cycle without a real LLM or code-execution engine.

**Why this exists:**

Phase 6 validates the *signal flow* from ``growth.build.requested`` all
the way to ``agent.bootstrapped``.  A full LLM-backed builder is deferred
to Phase 7.  Until then, the StubDevAgent acts as a predictable stand-in
that always succeeds, never triggers the fix-loop (tests always pass), and
never triggers the Ask/Stop policy (review is always clean).

**What changes in Phase 7:**

This file will be retired and replaced by a real ``BuilderAgent`` that
calls an LLM to generate code, write tests, and perform an actual code
review.  The MessageBus interface (topics, payload shapes) will remain
identical.

Topics subscribed:
    - ``dev.plan.requested``
    - ``dev.implement.requested``
    - ``dev.test.requested``
    - ``dev.fix.requested``
    - ``dev.review.requested``

Topics published:
    - ``dev.plan.completed``
    - ``dev.implement.completed``
    - ``dev.test.completed``
    - ``dev.fix.completed``
    - ``dev.review.completed``
"""

from __future__ import annotations

import logging
from typing import Optional

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.dev import events

logger = logging.getLogger(__name__)

_PHASE_TOPICS = (
    "dev.plan.requested",
    "dev.implement.requested",
    "dev.test.requested",
    "dev.fix.requested",
    "dev.review.requested",
)


class StubDevAgent(Agent):
    """Stub agent that drives the DevLoop through all phases using hard-coded responses.

    Every phase response is approved/passing so the orchestrator reaches
    ``dev.loop.completed`` without entering any retry or fail path.

    Args:
        message_bus: The shared :class:`~genus.communication.message_bus.MessageBus`.
        agent_id:    Optional custom agent ID.  Auto-generated if omitted.
        name:        Optional human-readable agent name.  Defaults to
                     ``"StubDevAgent"``.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name or "StubDevAgent")
        self._bus = message_bus

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Subscribe to all DevLoop phase-requested topics."""
        for topic in _PHASE_TOPICS:
            self._bus.subscribe(topic, f"{self.id}:{topic}", self.process_message)
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
        """Dispatch an incoming DevLoop phase-requested event to its handler.

        Args:
            message: The incoming message.
        """
        handlers = {
            "dev.plan.requested": self._handle_plan,
            "dev.implement.requested": self._handle_implement,
            "dev.test.requested": self._handle_test,
            "dev.fix.requested": self._handle_fix,
            "dev.review.requested": self._handle_review,
        }
        handler = handlers.get(message.topic)
        if handler is not None:
            await handler(message)

    # ------------------------------------------------------------------
    # Phase handlers
    # ------------------------------------------------------------------

    async def _handle_plan(self, message: Message) -> None:
        """Respond to ``dev.plan.requested`` with a stub plan."""
        run_id = message.metadata.get("run_id")
        phase_id = message.payload.get("phase_id") if isinstance(message.payload, dict) else None
        if not run_id or not phase_id:
            return

        goal: str = (
            message.payload.get("goal", "")
            or message.metadata.get("goal", "stub goal")
        )

        plan = {
            "steps": [{"action": "stub_action", "description": f"Stub plan for: {goal}"}],
            "goal": goal,
            "risks": [],
            "stub": True,
        }
        await self._bus.publish(
            events.dev_plan_completed_message(
                run_id,
                self.id,
                plan,
                phase_id=phase_id,
            )
        )

    async def _handle_implement(self, message: Message) -> None:
        """Respond to ``dev.implement.requested`` with a stub implementation."""
        run_id = message.metadata.get("run_id")
        phase_id = message.payload.get("phase_id") if isinstance(message.payload, dict) else None
        if not run_id or not phase_id:
            return

        await self._bus.publish(
            events.dev_implement_completed_message(
                run_id,
                self.id,
                patch_summary="Stub implementation — no real code generated.",
                files_changed=[],
                phase_id=phase_id,
            )
        )

    async def _handle_test(self, message: Message) -> None:
        """Respond to ``dev.test.requested`` with a passing stub test report.

        ``failed`` is ``0`` so the DevLoopOrchestrator does not enter the
        fix-iteration loop.
        """
        run_id = message.metadata.get("run_id")
        phase_id = message.payload.get("phase_id") if isinstance(message.payload, dict) else None
        if not run_id or not phase_id:
            return

        report = {
            "passed": 1,
            "failed": 0,
            "failing_tests": [],
            "summary": "Stub test pass — all tests passed (stub mode).",
            "stub": True,
        }
        await self._bus.publish(
            events.dev_test_completed_message(
                run_id,
                self.id,
                report,
                phase_id=phase_id,
            )
        )

    async def _handle_fix(self, message: Message) -> None:
        """Respond to ``dev.fix.requested`` with a stub fix."""
        run_id = message.metadata.get("run_id")
        phase_id = message.payload.get("phase_id") if isinstance(message.payload, dict) else None
        if not run_id or not phase_id:
            return

        fix = {"action": "stub_fix", "stub": True}
        await self._bus.publish(
            events.dev_fix_completed_message(
                run_id,
                self.id,
                fix,
                phase_id=phase_id,
            )
        )

    async def _handle_review(self, message: Message) -> None:
        """Respond to ``dev.review.requested`` with an approved stub review.

        ``findings`` is empty so ``should_ask_user()`` does not trigger the
        Ask/Stop path.
        """
        run_id = message.metadata.get("run_id")
        phase_id = message.payload.get("phase_id") if isinstance(message.payload, dict) else None
        if not run_id or not phase_id:
            return

        review = {
            "findings": [],
            "approved": True,
            "summary": "Stub review — approved (stub mode).",
            "stub": True,
        }
        await self._bus.publish(
            events.dev_review_completed_message(
                run_id,
                self.id,
                review,
                phase_id=phase_id,
            )
        )

"""
Planner Agent

Subscribes to dev.plan.requested and publishes dev.plan.completed or
dev.plan.failed with a placeholder plan artifact.

This is a reference skeleton agent – it does not perform actual planning.
It demonstrates the MessageBus-based communication pattern.
"""

from typing import Awaitable, Callable, List, Literal, Optional, Tuple
from genus.communication.message_bus import Message, MessageBus
from genus.dev import events, topics
from genus.dev.agents.base import DevAgentBase


class PlannerAgent(DevAgentBase):
    """Agent that responds to planning requests.

    Args:
        bus:         MessageBus instance.
        agent_id:    Unique identifier for this agent.
        mode:        Behavior mode: "ok" (normal) or "fail" (simulate failure).
        fail_topic:  If mode=="fail" and topic matches, publish failed response.

    Example::

        planner = PlannerAgent(bus, "planner-1", mode="ok")
        planner.start()
        # ... orchestrator publishes dev.plan.requested ...
        # ... planner responds with dev.plan.completed ...
        planner.stop()
    """

    def __init__(
        self,
        bus: MessageBus,
        agent_id: str = "PlannerAgent",
        mode: Literal["ok", "fail"] = "ok",
        fail_topic: Optional[str] = None,
    ) -> None:
        super().__init__(bus, agent_id)
        self._mode = mode
        self._fail_topic = fail_topic

    def _subscribe_topics(self) -> List[Tuple[str, Callable[[Message], Awaitable[None]]]]:
        """Register handler for dev.plan.requested."""
        return [(topics.DEV_PLAN_REQUESTED, self._handle_plan_requested)]

    async def _handle_plan_requested(self, msg: Message) -> None:
        """Handle dev.plan.requested messages."""
        # Validate metadata
        run_id = msg.metadata.get("run_id")
        if not run_id:
            return

        # Validate payload
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return

        # Check if we should simulate failure
        should_fail = (
            self._mode == "fail"
            and (self._fail_topic is None or self._fail_topic == msg.topic)
        )

        if should_fail:
            # Publish failed response
            await self._bus.publish(
                events.dev_plan_failed_message(
                    run_id,
                    self.agent_id,
                    "Planning failed (simulated)",
                    phase_id=phase_id,
                )
            )
            return

        # Extract request data
        requirements = msg.payload.get("requirements", [])
        constraints = msg.payload.get("constraints", [])

        # Build placeholder plan
        plan = {
            "steps": [
                "Step 1: Analyze requirements",
                "Step 2: Design solution architecture",
                "Step 3: Implement core functionality",
                "Step 4: Add tests and documentation",
            ],
            "acceptance_criteria": list(requirements) if requirements else ["All tests pass"],
            "risks": self._derive_risks(constraints),
        }

        # Publish completed response
        await self._bus.publish(
            events.dev_plan_completed_message(
                run_id,
                self.agent_id,
                plan,
                phase_id=phase_id,
            )
        )

    def _derive_risks(self, constraints: List[str]) -> List[str]:
        """Derive placeholder risks from constraints."""
        if not constraints:
            return []
        return [f"Risk: constraint '{c}' may be violated" for c in constraints[:2]]

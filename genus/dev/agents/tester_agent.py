"""
Tester Agent

Subscribes to dev.test.requested and publishes dev.test.completed or
dev.test.failed with a placeholder test report.

This is a reference skeleton agent – it does not perform actual testing.
It demonstrates the MessageBus-based communication pattern.
"""

from typing import Awaitable, Callable, List, Literal, Optional, Tuple
from genus.communication.message_bus import Message, MessageBus
from genus.dev import events, topics
from genus.dev.agents.base import DevAgentBase


class TesterAgent(DevAgentBase):
    """Agent that responds to test requests.

    Args:
        bus:         MessageBus instance.
        agent_id:    Unique identifier for this agent.
        mode:        Behavior mode: "ok" (normal) or "fail" (simulate failure).
        fail_topic:  If mode=="fail" and topic matches, publish failed response.

    Example::

        tester = TesterAgent(bus, "tester-1", mode="ok")
        tester.start()
        # ... orchestrator publishes dev.test.requested ...
        # ... tester responds with dev.test.completed ...
        tester.stop()
    """

    def __init__(
        self,
        bus: MessageBus,
        agent_id: str = "TesterAgent",
        mode: Literal["ok", "fail"] = "ok",
        fail_topic: Optional[str] = None,
    ) -> None:
        super().__init__(bus, agent_id)
        self._mode = mode
        self._fail_topic = fail_topic

    def _subscribe_topics(self) -> List[Tuple[str, Callable[[Message], Awaitable[None]]]]:
        """Register handler for dev.test.requested."""
        return [(topics.DEV_TEST_REQUESTED, self._handle_test_requested)]

    async def _handle_test_requested(self, msg: Message) -> None:
        """Handle dev.test.requested messages."""
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
                events.dev_test_failed_message(
                    run_id,
                    self.agent_id,
                    "Testing failed (simulated)",
                    phase_id=phase_id,
                )
            )
            return

        # Build placeholder test report
        report = {
            "passed": 42,
            "failed": 0,
            "duration_s": 3.14,
            "summary": "All tests passed (placeholder)",
            "failing_tests": [],
        }

        # Publish completed response
        await self._bus.publish(
            events.dev_test_completed_message(
                run_id,
                self.agent_id,
                report,
                phase_id=phase_id,
            )
        )

"""
Builder Agent

Subscribes to dev.implement.requested and publishes dev.implement.completed
or dev.implement.failed with a placeholder implementation summary.

This is a reference skeleton agent – it does not perform actual implementation.
It demonstrates the MessageBus-based communication pattern.
"""

from typing import Awaitable, Callable, List, Literal, Optional, Tuple
from genus.communication.message_bus import Message, MessageBus
from genus.dev import events, topics
from genus.dev.agents.base import DevAgentBase


class BuilderAgent(DevAgentBase):
    """Agent that responds to implementation requests.

    Args:
        bus:         MessageBus instance.
        agent_id:    Unique identifier for this agent.
        mode:        Behavior mode: "ok" (normal) or "fail" (simulate failure).
        fail_topic:  If mode=="fail" and topic matches, publish failed response.

    Example::

        builder = BuilderAgent(bus, "builder-1", mode="ok")
        builder.start()
        # ... orchestrator publishes dev.implement.requested ...
        # ... builder responds with dev.implement.completed ...
        builder.stop()
    """

    def __init__(
        self,
        bus: MessageBus,
        agent_id: str = "BuilderAgent",
        mode: Literal["ok", "fail"] = "ok",
        fail_topic: Optional[str] = None,
    ) -> None:
        super().__init__(bus, agent_id)
        self._mode = mode
        self._fail_topic = fail_topic

    def _subscribe_topics(self) -> List[Tuple[str, Callable[[Message], Awaitable[None]]]]:
        """Register handler for dev.implement.requested."""
        return [(topics.DEV_IMPLEMENT_REQUESTED, self._handle_implement_requested)]

    async def _handle_implement_requested(self, msg: Message) -> None:
        """Handle dev.implement.requested messages."""
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
                events.dev_implement_failed_message(
                    run_id,
                    self.agent_id,
                    "Implementation failed (simulated)",
                    phase_id=phase_id,
                )
            )
            return

        # Build placeholder implementation result
        patch_summary = "Implemented planned changes (placeholder)"
        files_changed = ["README.md"]

        # Publish completed response
        await self._bus.publish(
            events.dev_implement_completed_message(
                run_id,
                self.agent_id,
                patch_summary,
                files_changed,
                phase_id=phase_id,
            )
        )

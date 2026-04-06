"""
Reviewer Agent

Subscribes to dev.review.requested and publishes dev.review.completed or
dev.review.failed with a placeholder review artifact.

This is a reference skeleton agent – it does not perform actual code review.
It demonstrates the MessageBus-based communication pattern and supports
configurable review profiles for testing Ask/Stop policy.
"""

from typing import List, Literal, Optional, Tuple
from genus.communication.message_bus import Message, MessageBus
from genus.dev import events, topics
from genus.dev.agents.base import DevAgentBase


class ReviewerAgent(DevAgentBase):
    """Agent that responds to review requests.

    Args:
        bus:            MessageBus instance.
        agent_id:       Unique identifier for this agent.
        mode:           Behavior mode: "ok" (normal) or "fail" (simulate failure).
        fail_topic:     If mode=="fail" and topic matches, publish failed response.
        review_profile: Review profile: "clean" (no issues) or "high_sev" (high severity finding).

    Example::

        # Clean review (no findings)
        reviewer = ReviewerAgent(bus, "reviewer-1", review_profile="clean")
        reviewer.start()
        # ... orchestrator publishes dev.review.requested ...
        # ... reviewer responds with dev.review.completed with empty findings ...

        # High severity review (triggers Ask/Stop)
        reviewer = ReviewerAgent(bus, "reviewer-2", review_profile="high_sev")
        reviewer.start()
        # ... orchestrator will detect high severity and pause ...
        reviewer.stop()
    """

    def __init__(
        self,
        bus: MessageBus,
        agent_id: str = "ReviewerAgent",
        mode: Literal["ok", "fail"] = "ok",
        fail_topic: Optional[str] = None,
        review_profile: Literal["clean", "high_sev"] = "clean",
    ) -> None:
        super().__init__(bus, agent_id)
        self._mode = mode
        self._fail_topic = fail_topic
        self._review_profile = review_profile

    def _subscribe_topics(self) -> List[Tuple[str, any]]:
        """Register handler for dev.review.requested."""
        return [(topics.DEV_REVIEW_REQUESTED, self._handle_review_requested)]

    async def _handle_review_requested(self, msg: Message) -> None:
        """Handle dev.review.requested messages."""
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
                events.dev_review_failed_message(
                    run_id,
                    self.agent_id,
                    "Review failed (simulated)",
                    phase_id=phase_id,
                )
            )
            return

        # Build review based on profile
        review = self._build_review()

        # Publish completed response
        await self._bus.publish(
            events.dev_review_completed_message(
                run_id,
                self.agent_id,
                review,
                phase_id=phase_id,
            )
        )

    def _build_review(self) -> dict:
        """Build review artifact based on review_profile."""
        if self._review_profile == "high_sev":
            return {
                "findings": [
                    {
                        "severity": "high",
                        "message": "Potential security vulnerability detected (placeholder)",
                        "location": "genus/example.py:42",
                    }
                ],
                "severity": "high",
                "required_fixes": ["Address security vulnerability"],
            }
        else:  # clean
            return {
                "findings": [],
                "severity": "none",
                "required_fixes": [],
            }

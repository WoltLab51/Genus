"""
Integration Tests for DevLoop with Agent Skeletons

Validates end-to-end integration of DevLoopOrchestrator with the reference
agent skeletons (PlannerAgent, BuilderAgent, TesterAgent, ReviewerAgent).

These tests verify:
1. Happy Path: All agents respond successfully, loop completes.
2. Ask/Stop Path: High severity finding triggers loop.failed.
3. Failure Path: Agent failure propagates correctly and raises exception.
"""

import pytest
from typing import List

from genus.communication.message_bus import MessageBus, Message
from genus.dev import topics
from genus.dev.devloop_orchestrator import DevLoopOrchestrator
from genus.dev.agents import (
    PlannerAgent,
    BuilderAgent,
    TesterAgent,
    ReviewerAgent,
)
from genus.dev.runtime import DevResponseFailedError


@pytest.fixture
def bus():
    """Create a fresh MessageBus for each test."""
    return MessageBus()


@pytest.fixture
def run_id():
    """Standard run_id for tests."""
    return "2026-04-06T14-00-00Z__agenttest__abc123"


class MessageCapture:
    """Helper to capture messages on specific topics."""

    def __init__(self, bus: MessageBus, topics_to_capture: List[str]):
        self.bus = bus
        self.topics = topics_to_capture
        self.captured: List[Message] = []
        self._subscriber_id = "message-capture"

    def start(self) -> None:
        """Subscribe to topics."""
        for topic in self.topics:
            self.bus.subscribe(topic, f"{self._subscriber_id}:{topic}", self._capture)

    async def _capture(self, msg: Message) -> None:
        """Capture callback."""
        self.captured.append(msg)

    def stop(self) -> None:
        """Unsubscribe from topics."""
        for topic in self.topics:
            self.bus.unsubscribe(topic, f"{self._subscriber_id}:{topic}")

    def get_messages(self, topic: str) -> List[Message]:
        """Get captured messages for a specific topic."""
        return [msg for msg in self.captured if msg.topic == topic]


@pytest.mark.asyncio
async def test_happy_path_all_agents_succeed(bus, run_id):
    """Test 1: Happy Path - All agents respond successfully, loop completes."""
    # Setup agents
    planner = PlannerAgent(bus, "planner-1", mode="ok")
    builder = BuilderAgent(bus, "builder-1", mode="ok")
    tester = TesterAgent(bus, "tester-1", mode="ok")
    reviewer = ReviewerAgent(bus, "reviewer-1", mode="ok", review_profile="clean")

    # Setup message capture
    capture = MessageCapture(
        bus,
        [
            topics.DEV_LOOP_COMPLETED,
            topics.DEV_LOOP_FAILED,
        ],
    )

    # Setup orchestrator
    orchestrator = DevLoopOrchestrator(bus, sender_id="TestOrchestrator", timeout_s=2.0)

    try:
        # Start all components
        planner.start()
        builder.start()
        tester.start()
        reviewer.start()
        capture.start()

        # Run the orchestrator
        await orchestrator.run(
            run_id=run_id,
            goal="Test happy path integration",
            requirements=["All tests pass"],
            constraints=["No breaking changes"],
        )

        # Verify loop completed
        completed_msgs = capture.get_messages(topics.DEV_LOOP_COMPLETED)
        assert len(completed_msgs) == 1, "Expected exactly one loop.completed message"

        # Verify no failures
        failed_msgs = capture.get_messages(topics.DEV_LOOP_FAILED)
        assert len(failed_msgs) == 0, "Expected no loop.failed messages"

    finally:
        # Cleanup
        planner.stop()
        builder.stop()
        tester.stop()
        reviewer.stop()
        capture.stop()


@pytest.mark.asyncio
async def test_ask_stop_path_high_severity(bus, run_id):
    """Test 2: Ask/Stop Path - High severity finding triggers loop.failed."""
    # Setup agents with high_sev reviewer
    planner = PlannerAgent(bus, "planner-2", mode="ok")
    builder = BuilderAgent(bus, "builder-2", mode="ok")
    tester = TesterAgent(bus, "tester-2", mode="ok")
    reviewer = ReviewerAgent(bus, "reviewer-2", mode="ok", review_profile="high_sev")

    # Setup message capture
    capture = MessageCapture(
        bus,
        [
            topics.DEV_LOOP_COMPLETED,
            topics.DEV_LOOP_FAILED,
        ],
    )

    # Setup orchestrator
    orchestrator = DevLoopOrchestrator(bus, sender_id="TestOrchestrator", timeout_s=2.0)

    try:
        # Start all components
        planner.start()
        builder.start()
        tester.start()
        reviewer.start()
        capture.start()

        # Run the orchestrator
        await orchestrator.run(
            run_id=run_id,
            goal="Test Ask/Stop policy with high severity",
        )

        # Verify loop failed (Ask/Stop policy triggered)
        failed_msgs = capture.get_messages(topics.DEV_LOOP_FAILED)
        assert len(failed_msgs) == 1, "Expected exactly one loop.failed message"

        # Verify error message mentions operator
        error = failed_msgs[0].payload.get("error", "")
        assert "Awaiting operator" in error, f"Expected 'Awaiting operator' in error: {error}"

        # Verify no completion
        completed_msgs = capture.get_messages(topics.DEV_LOOP_COMPLETED)
        assert len(completed_msgs) == 0, "Expected no loop.completed messages"

    finally:
        # Cleanup
        planner.stop()
        builder.stop()
        tester.stop()
        reviewer.stop()
        capture.stop()


@pytest.mark.asyncio
async def test_failure_path_implement_fails(bus, run_id):
    """Test 3: Failure Path - BuilderAgent failure raises exception."""
    # Setup agents with failing builder
    planner = PlannerAgent(bus, "planner-3", mode="ok")
    builder = BuilderAgent(bus, "builder-3", mode="fail")
    tester = TesterAgent(bus, "tester-3", mode="ok")
    reviewer = ReviewerAgent(bus, "reviewer-3", mode="ok", review_profile="clean")

    # Setup message capture
    capture = MessageCapture(
        bus,
        [
            topics.DEV_LOOP_COMPLETED,
            topics.DEV_LOOP_FAILED,
        ],
    )

    # Setup orchestrator
    orchestrator = DevLoopOrchestrator(bus, sender_id="TestOrchestrator", timeout_s=2.0)

    try:
        # Start all components
        planner.start()
        builder.start()
        tester.start()
        reviewer.start()
        capture.start()

        # Run the orchestrator - expect exception
        with pytest.raises(DevResponseFailedError) as exc_info:
            await orchestrator.run(
                run_id=run_id,
                goal="Test failure handling",
            )

        # Verify exception details
        assert exc_info.value.run_id == run_id
        assert "Implementation failed (simulated)" in exc_info.value.error

        # Verify loop failed was published
        failed_msgs = capture.get_messages(topics.DEV_LOOP_FAILED)
        assert len(failed_msgs) == 1, "Expected exactly one loop.failed message"

        # Verify no completion
        completed_msgs = capture.get_messages(topics.DEV_LOOP_COMPLETED)
        assert len(completed_msgs) == 0, "Expected no loop.completed messages"

    finally:
        # Cleanup
        planner.stop()
        builder.stop()
        tester.stop()
        reviewer.stop()
        capture.stop()

"""
Tests for DevLoopOrchestrator runtime behavior

Validates that the orchestrator:
- Publishes requested topics with phase_id in correct order
- Awaits each phase response before continuing
- Applies Ask/Stop policy after review
- Handles failures and timeouts properly
- Uses fake responder agents in tests
"""

import pytest
import asyncio

from genus.communication.message_bus import MessageBus, Message
from genus.dev import topics
from genus.dev.devloop_orchestrator import DevLoopOrchestrator
from genus.dev.events import (
    dev_plan_completed_message,
    dev_plan_failed_message,
    dev_implement_completed_message,
    dev_test_completed_message,
    dev_review_completed_message,
)
from genus.dev.runtime import DevResponseFailedError, DevResponseTimeoutError


@pytest.fixture
def bus():
    """Create a fresh MessageBus for each test."""
    return MessageBus()


@pytest.fixture
def run_id():
    """Standard run_id for tests."""
    return "2026-04-06T10-00-00Z__orchtest__xyz789"


@pytest.fixture
def orchestrator(bus):
    """Create an orchestrator with short timeout for tests."""
    return DevLoopOrchestrator(bus, sender_id="TestOrchestrator", timeout_s=2.0)


class FakeResponder:
    """Helper to auto-respond to dev-loop phases."""

    def __init__(self, bus: MessageBus, run_id: str):
        self.bus = bus
        self.run_id = run_id
        self.responses = {}
        self._tasks = []

    def on_plan_requested(self, plan: dict):
        """Set response for plan phase."""
        self.responses["plan"] = plan

    def on_implement_requested(self):
        """Set response for implement phase."""
        self.responses["implement"] = {
            "patch_summary": "Implemented feature",
            "files_changed": ["file.py"],
        }

    def on_test_requested(self):
        """Set response for test phase."""
        self.responses["test"] = {
            "passed": 10,
            "failed": 0,
            "duration_s": 1.5,
            "summary": "All tests passed",
            "failing_tests": [],
        }

    def on_review_requested(self, review: dict):
        """Set response for review phase."""
        self.responses["review"] = review

    async def _handle_plan(self, msg: Message):
        """Respond to plan.requested."""
        if msg.metadata.get("run_id") != self.run_id:
            return
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return
        if "plan" not in self.responses:
            return

        # Spawn response as background task to avoid blocking callback
        asyncio.create_task(self._respond_plan(phase_id))

    async def _respond_plan(self, phase_id: str):
        """Background task to respond to plan request."""
        await asyncio.sleep(0.01)  # Small delay to ensure subscriptions are ready
        await self.bus.publish(
            dev_plan_completed_message(
                self.run_id, "FakePlanner", self.responses["plan"], phase_id=phase_id
            )
        )

    async def _handle_implement(self, msg: Message):
        """Respond to implement.requested."""
        if msg.metadata.get("run_id") != self.run_id:
            return
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return
        if "implement" not in self.responses:
            return

        asyncio.create_task(self._respond_implement(phase_id))

    async def _respond_implement(self, phase_id: str):
        """Background task to respond to implement request."""
        await asyncio.sleep(0.01)
        data = self.responses["implement"]
        await self.bus.publish(
            dev_implement_completed_message(
                self.run_id,
                "FakeBuilder",
                data["patch_summary"],
                data["files_changed"],
                phase_id=phase_id,
            )
        )

    async def _handle_test(self, msg: Message):
        """Respond to test.requested."""
        if msg.metadata.get("run_id") != self.run_id:
            return
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return
        if "test" not in self.responses:
            return

        asyncio.create_task(self._respond_test(phase_id))

    async def _respond_test(self, phase_id: str):
        """Background task to respond to test request."""
        await asyncio.sleep(0.01)
        await self.bus.publish(
            dev_test_completed_message(
                self.run_id, "FakeTester", self.responses["test"], phase_id=phase_id
            )
        )

    async def _handle_review(self, msg: Message):
        """Respond to review.requested."""
        if msg.metadata.get("run_id") != self.run_id:
            return
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return
        if "review" not in self.responses:
            return

        asyncio.create_task(self._respond_review(phase_id))

    async def _respond_review(self, phase_id: str):
        """Background task to respond to review request."""
        await asyncio.sleep(0.01)
        await self.bus.publish(
            dev_review_completed_message(
                self.run_id, "FakeReviewer", self.responses["review"], phase_id=phase_id
            )
        )

    def start(self):
        """Subscribe to all requested topics."""
        self.bus.subscribe(topics.DEV_PLAN_REQUESTED, "FakeResponder", self._handle_plan)
        self.bus.subscribe(
            topics.DEV_IMPLEMENT_REQUESTED, "FakeResponder", self._handle_implement
        )
        self.bus.subscribe(topics.DEV_TEST_REQUESTED, "FakeResponder", self._handle_test)
        self.bus.subscribe(
            topics.DEV_REVIEW_REQUESTED, "FakeResponder", self._handle_review
        )


@pytest.fixture
def fake_responder(bus, run_id):
    """Create a fake responder for tests."""
    responder = FakeResponder(bus, run_id)
    responder.start()
    return responder


class TestOrchestratorMessageFlow:
    """Tests for orchestrator message publishing order."""

    async def test_publishes_loop_started(self, bus, orchestrator, run_id, fake_responder):
        """Orchestrator publishes dev.loop.started first."""
        published = []

        async def capture(msg: Message):
            published.append(msg.topic)

        bus.subscribe(topics.DEV_LOOP_STARTED, "capture", capture)

        # Set up responder
        fake_responder.on_plan_requested({"steps": [], "acceptance_criteria": [], "risks": []})
        fake_responder.on_implement_requested()
        fake_responder.on_test_requested()
        fake_responder.on_review_requested({"findings": [], "severity": "none", "required_fixes": []})

        await orchestrator.run(run_id, "test goal")

        assert topics.DEV_LOOP_STARTED in published

    async def test_publishes_requested_topics_in_order(
        self, bus, orchestrator, run_id, fake_responder
    ):
        """Orchestrator publishes phases in correct order."""
        published = []

        async def capture(msg: Message):
            published.append(msg.topic)

        # Subscribe to all requested topics
        for topic in [
            topics.DEV_PLAN_REQUESTED,
            topics.DEV_IMPLEMENT_REQUESTED,
            topics.DEV_TEST_REQUESTED,
            topics.DEV_REVIEW_REQUESTED,
        ]:
            bus.subscribe(topic, "capture", capture)

        # Set up responder
        fake_responder.on_plan_requested({"steps": [], "acceptance_criteria": [], "risks": []})
        fake_responder.on_implement_requested()
        fake_responder.on_test_requested()
        fake_responder.on_review_requested({"findings": [], "severity": "none", "required_fixes": []})

        await orchestrator.run(run_id, "test goal")

        # Verify order
        assert published == [
            topics.DEV_PLAN_REQUESTED,
            topics.DEV_IMPLEMENT_REQUESTED,
            topics.DEV_TEST_REQUESTED,
            topics.DEV_REVIEW_REQUESTED,
        ]

    async def test_each_requested_has_phase_id(
        self, bus, orchestrator, run_id, fake_responder
    ):
        """Each requested message includes a phase_id."""
        phase_ids = []

        async def capture(msg: Message):
            pid = msg.payload.get("phase_id")
            if pid:
                phase_ids.append(pid)

        # Subscribe to all requested topics
        for topic in [
            topics.DEV_PLAN_REQUESTED,
            topics.DEV_IMPLEMENT_REQUESTED,
            topics.DEV_TEST_REQUESTED,
            topics.DEV_REVIEW_REQUESTED,
        ]:
            bus.subscribe(topic, "capture", capture)

        # Set up responder
        fake_responder.on_plan_requested({"steps": [], "acceptance_criteria": [], "risks": []})
        fake_responder.on_implement_requested()
        fake_responder.on_test_requested()
        fake_responder.on_review_requested({"findings": [], "severity": "none", "required_fixes": []})

        await orchestrator.run(run_id, "test goal")

        # Should have 4 unique phase_ids
        assert len(phase_ids) == 4
        assert len(set(phase_ids)) == 4  # all unique


class TestOrchestratorAwaitLogic:
    """Tests for orchestrator await behavior."""

    async def test_waits_for_plan_before_implement(
        self, bus, orchestrator, run_id, fake_responder
    ):
        """Orchestrator waits for plan.completed before publishing implement.requested."""
        events_order = []

        async def track_plan_completed(msg: Message):
            events_order.append("plan_completed")

        async def track_implement_requested(msg: Message):
            events_order.append("implement_requested")

        bus.subscribe(topics.DEV_PLAN_COMPLETED, "track", track_plan_completed)
        bus.subscribe(topics.DEV_IMPLEMENT_REQUESTED, "track", track_implement_requested)

        # Set up responder
        fake_responder.on_plan_requested({"steps": [], "acceptance_criteria": [], "risks": []})
        fake_responder.on_implement_requested()
        fake_responder.on_test_requested()
        fake_responder.on_review_requested({"findings": [], "severity": "none", "required_fixes": []})

        await orchestrator.run(run_id, "test goal")

        # plan_completed must come before implement_requested
        assert events_order.index("plan_completed") < events_order.index("implement_requested")

    async def test_successful_loop_completion(
        self, bus, orchestrator, run_id, fake_responder
    ):
        """Orchestrator completes successfully when all phases succeed."""
        completed_published = []

        async def capture_completed(msg: Message):
            completed_published.append(msg.topic)

        bus.subscribe(topics.DEV_LOOP_COMPLETED, "capture", capture_completed)

        # Set up responder
        fake_responder.on_plan_requested({"steps": [], "acceptance_criteria": [], "risks": []})
        fake_responder.on_implement_requested()
        fake_responder.on_test_requested()
        fake_responder.on_review_requested({"findings": [], "severity": "none", "required_fixes": []})

        await orchestrator.run(run_id, "test goal")

        assert topics.DEV_LOOP_COMPLETED in completed_published


class TestOrchestratorAskStopPolicy:
    """Tests for Ask/Stop policy gate."""

    async def test_stops_on_high_severity_finding(
        self, bus, orchestrator, run_id, fake_responder
    ):
        """Orchestrator stops and publishes loop.failed when review has high severity."""
        failed_published = []

        async def capture_failed(msg: Message):
            failed_published.append(msg.payload.get("error", ""))

        bus.subscribe(topics.DEV_LOOP_FAILED, "capture", capture_failed)

        # Set up responder with high-severity finding
        fake_responder.on_plan_requested({"steps": [], "acceptance_criteria": [], "risks": []})
        fake_responder.on_implement_requested()
        fake_responder.on_test_requested()
        fake_responder.on_review_requested(
            {
                "findings": [{"severity": "high", "message": "Critical issue"}],
                "severity": "high",
                "required_fixes": ["fix-1"],
            }
        )

        await orchestrator.run(run_id, "test goal")

        # Should have published loop.failed
        assert len(failed_published) == 1
        assert "Awaiting operator" in failed_published[0]

    async def test_continues_on_low_severity(
        self, bus, orchestrator, run_id, fake_responder
    ):
        """Orchestrator continues when review has only low severity findings."""
        completed_published = []

        async def capture_completed(msg: Message):
            completed_published.append(msg.topic)

        bus.subscribe(topics.DEV_LOOP_COMPLETED, "capture", capture_completed)

        # Set up responder with low-severity finding
        fake_responder.on_plan_requested({"steps": [], "acceptance_criteria": [], "risks": []})
        fake_responder.on_implement_requested()
        fake_responder.on_test_requested()
        fake_responder.on_review_requested(
            {
                "findings": [{"severity": "low", "message": "Minor issue"}],
                "severity": "low",
                "required_fixes": [],
            }
        )

        await orchestrator.run(run_id, "test goal")

        # Should complete successfully
        assert topics.DEV_LOOP_COMPLETED in completed_published


class TestOrchestratorFailureHandling:
    """Tests for phase failure and timeout handling."""

    async def test_handles_plan_failure(self, bus, orchestrator, run_id):
        """Orchestrator handles plan.failed and publishes loop.failed."""
        # Subscribe to respond with failure
        async def fail_plan(msg: Message):
            phase_id = msg.payload.get("phase_id")
            if phase_id:
                async def respond_with_failure():
                    await asyncio.sleep(0.01)
                    await bus.publish(
                        dev_plan_failed_message(
                            run_id, "FakePlanner", "Planning error", phase_id=phase_id
                        )
                    )
                asyncio.create_task(respond_with_failure())

        bus.subscribe(topics.DEV_PLAN_REQUESTED, "failer", fail_plan)

        with pytest.raises(DevResponseFailedError) as exc_info:
            await orchestrator.run(run_id, "test goal")

        assert exc_info.value.error == "Planning error"

    async def test_handles_timeout(self, bus, run_id):
        """Orchestrator handles timeout when no response arrives."""
        # Create orchestrator with very short timeout
        orchestrator = DevLoopOrchestrator(bus, timeout_s=0.1)

        # Don't set up any responder - let it timeout
        with pytest.raises(DevResponseTimeoutError) as exc_info:
            await orchestrator.run(run_id, "test goal")

        assert exc_info.value.run_id == run_id
        assert exc_info.value.timeout_s == 0.1

    async def test_publishes_loop_failed_on_exception(
        self, bus, orchestrator, run_id
    ):
        """Orchestrator publishes loop.failed when an exception occurs."""
        failed_published = []

        async def capture_failed(msg: Message):
            failed_published.append(msg.topic)

        bus.subscribe(topics.DEV_LOOP_FAILED, "capture", capture_failed)

        # Create orchestrator with very short timeout to trigger error
        short_orchestrator = DevLoopOrchestrator(bus, timeout_s=0.1)

        with pytest.raises(DevResponseTimeoutError):
            await short_orchestrator.run(run_id, "test goal")

        # Should have published loop.failed
        assert topics.DEV_LOOP_FAILED in failed_published

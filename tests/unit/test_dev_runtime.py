"""
Tests for genus/dev/runtime.py

Validates await_dev_response behavior including:
- Successful completion matching
- Failed topic exception handling
- Timeout handling
- Filtering by run_id and phase_id
- Proper subscription cleanup
"""

import pytest
import asyncio

from genus.communication.message_bus import MessageBus
from genus.dev import topics
from genus.dev.events import (
    dev_plan_requested_message,
    dev_plan_completed_message,
    dev_plan_failed_message,
)
from genus.dev.runtime import (
    await_dev_response,
    DevResponseFailedError,
    DevResponseTimeoutError,
)


@pytest.fixture
def bus():
    """Create a fresh MessageBus for each test."""
    return MessageBus()


@pytest.fixture
def run_id():
    """Standard run_id for tests."""
    return "2026-04-06T10-00-00Z__test__abc123"


class TestAwaitDevResponseSuccess:
    """Tests for successful completion scenarios."""

    async def test_returns_completed_message(self, bus, run_id):
        """await_dev_response returns the completed message when published."""
        phase_id = "test-phase-1"

        # Start awaiting in background
        wait_task = asyncio.create_task(
            await_dev_response(
                bus,
                run_id=run_id,
                phase_id=phase_id,
                completed_topic=topics.DEV_PLAN_COMPLETED,
                failed_topic=topics.DEV_PLAN_FAILED,
                timeout_s=1.0,
            )
        )

        # Give the subscription time to register
        await asyncio.sleep(0.01)

        # Publish a matching completed message
        plan = {"steps": ["step1"], "acceptance_criteria": [], "risks": []}
        await bus.publish(
            dev_plan_completed_message(run_id, "planner", plan, phase_id=phase_id)
        )

        # Await should complete with the message
        result = await wait_task
        assert result.topic == topics.DEV_PLAN_COMPLETED
        assert result.payload["phase_id"] == phase_id
        assert result.payload["plan"] == plan

    async def test_ignores_wrong_run_id(self, bus, run_id):
        """await_dev_response ignores messages with different run_id."""
        phase_id = "test-phase-2"
        wrong_run_id = "different-run-id"

        wait_task = asyncio.create_task(
            await_dev_response(
                bus,
                run_id=run_id,
                phase_id=phase_id,
                completed_topic=topics.DEV_PLAN_COMPLETED,
                failed_topic=topics.DEV_PLAN_FAILED,
                timeout_s=0.2,
            )
        )

        await asyncio.sleep(0.01)

        # Publish with wrong run_id
        plan = {"steps": []}
        await bus.publish(
            dev_plan_completed_message(wrong_run_id, "planner", plan, phase_id=phase_id)
        )

        # Should timeout since run_id doesn't match
        with pytest.raises(DevResponseTimeoutError) as exc_info:
            await wait_task

        assert exc_info.value.run_id == run_id
        assert exc_info.value.phase_id == phase_id

    async def test_ignores_wrong_phase_id(self, bus, run_id):
        """await_dev_response ignores messages with different phase_id."""
        phase_id = "test-phase-3"
        wrong_phase_id = "different-phase-id"

        wait_task = asyncio.create_task(
            await_dev_response(
                bus,
                run_id=run_id,
                phase_id=phase_id,
                completed_topic=topics.DEV_PLAN_COMPLETED,
                failed_topic=topics.DEV_PLAN_FAILED,
                timeout_s=0.2,
            )
        )

        await asyncio.sleep(0.01)

        # Publish with wrong phase_id
        plan = {"steps": []}
        await bus.publish(
            dev_plan_completed_message(run_id, "planner", plan, phase_id=wrong_phase_id)
        )

        # Should timeout since phase_id doesn't match
        with pytest.raises(DevResponseTimeoutError):
            await wait_task


class TestAwaitDevResponseFailure:
    """Tests for failure scenarios."""

    async def test_raises_on_failed_topic(self, bus, run_id):
        """await_dev_response raises DevResponseFailedError on failed topic."""
        phase_id = "test-phase-4"

        wait_task = asyncio.create_task(
            await_dev_response(
                bus,
                run_id=run_id,
                phase_id=phase_id,
                completed_topic=topics.DEV_PLAN_COMPLETED,
                failed_topic=topics.DEV_PLAN_FAILED,
                timeout_s=1.0,
            )
        )

        await asyncio.sleep(0.01)

        # Publish a failed message
        await bus.publish(
            dev_plan_failed_message(run_id, "planner", "Planning failed", phase_id=phase_id)
        )

        # Should raise DevResponseFailedError
        with pytest.raises(DevResponseFailedError) as exc_info:
            await wait_task

        assert exc_info.value.run_id == run_id
        assert exc_info.value.phase_id == phase_id
        assert exc_info.value.error == "Planning failed"
        assert exc_info.value.message.topic == topics.DEV_PLAN_FAILED

    async def test_failed_topic_ignores_wrong_run_id(self, bus, run_id):
        """await_dev_response ignores failed messages with wrong run_id."""
        phase_id = "test-phase-5"
        wrong_run_id = "different-run-id"

        wait_task = asyncio.create_task(
            await_dev_response(
                bus,
                run_id=run_id,
                phase_id=phase_id,
                completed_topic=topics.DEV_PLAN_COMPLETED,
                failed_topic=topics.DEV_PLAN_FAILED,
                timeout_s=0.2,
            )
        )

        await asyncio.sleep(0.01)

        # Publish failed with wrong run_id
        await bus.publish(
            dev_plan_failed_message(wrong_run_id, "planner", "error", phase_id=phase_id)
        )

        # Should timeout, not raise DevResponseFailedError
        with pytest.raises(DevResponseTimeoutError):
            await wait_task


class TestAwaitDevResponseTimeout:
    """Tests for timeout scenarios."""

    async def test_raises_timeout_error(self, bus, run_id):
        """await_dev_response raises DevResponseTimeoutError on timeout."""
        phase_id = "test-phase-6"

        with pytest.raises(DevResponseTimeoutError) as exc_info:
            await await_dev_response(
                bus,
                run_id=run_id,
                phase_id=phase_id,
                completed_topic=topics.DEV_PLAN_COMPLETED,
                failed_topic=topics.DEV_PLAN_FAILED,
                timeout_s=0.1,
            )

        assert exc_info.value.run_id == run_id
        assert exc_info.value.phase_id == phase_id
        assert exc_info.value.timeout_s == 0.1

    async def test_timeout_error_message(self, bus, run_id):
        """DevResponseTimeoutError has descriptive message."""
        phase_id = "test-phase-7"

        with pytest.raises(DevResponseTimeoutError) as exc_info:
            await await_dev_response(
                bus,
                run_id=run_id,
                phase_id=phase_id,
                completed_topic=topics.DEV_PLAN_COMPLETED,
                failed_topic=topics.DEV_PLAN_FAILED,
                timeout_s=0.1,
            )

        error_msg = str(exc_info.value)
        assert "Timeout" in error_msg
        assert phase_id in error_msg
        assert run_id in error_msg


class TestAwaitDevResponseCleanup:
    """Tests for subscription cleanup."""

    async def test_unsubscribes_on_success(self, bus, run_id):
        """await_dev_response cleans up subscriptions on success."""
        phase_id = "test-phase-8"

        wait_task = asyncio.create_task(
            await_dev_response(
                bus,
                run_id=run_id,
                phase_id=phase_id,
                completed_topic=topics.DEV_PLAN_COMPLETED,
                failed_topic=topics.DEV_PLAN_FAILED,
                timeout_s=1.0,
            )
        )

        await asyncio.sleep(0.01)

        # Verify subscriptions exist
        assert bus.get_subscriber_count(topics.DEV_PLAN_COMPLETED) > 0
        assert bus.get_subscriber_count(topics.DEV_PLAN_FAILED) > 0

        # Complete the wait
        plan = {"steps": []}
        await bus.publish(
            dev_plan_completed_message(run_id, "planner", plan, phase_id=phase_id)
        )
        await wait_task

        # Subscriptions should be cleaned up
        assert bus.get_subscriber_count(topics.DEV_PLAN_COMPLETED) == 0
        assert bus.get_subscriber_count(topics.DEV_PLAN_FAILED) == 0

    async def test_unsubscribes_on_timeout(self, bus, run_id):
        """await_dev_response cleans up subscriptions on timeout."""
        phase_id = "test-phase-9"

        with pytest.raises(DevResponseTimeoutError):
            await await_dev_response(
                bus,
                run_id=run_id,
                phase_id=phase_id,
                completed_topic=topics.DEV_PLAN_COMPLETED,
                failed_topic=topics.DEV_PLAN_FAILED,
                timeout_s=0.1,
            )

        # Subscriptions should be cleaned up
        assert bus.get_subscriber_count(topics.DEV_PLAN_COMPLETED) == 0
        assert bus.get_subscriber_count(topics.DEV_PLAN_FAILED) == 0

    async def test_unsubscribes_on_failure(self, bus, run_id):
        """await_dev_response cleans up subscriptions on failure."""
        phase_id = "test-phase-10"

        wait_task = asyncio.create_task(
            await_dev_response(
                bus,
                run_id=run_id,
                phase_id=phase_id,
                completed_topic=topics.DEV_PLAN_COMPLETED,
                failed_topic=topics.DEV_PLAN_FAILED,
                timeout_s=1.0,
            )
        )

        await asyncio.sleep(0.01)

        # Publish failed
        await bus.publish(
            dev_plan_failed_message(run_id, "planner", "error", phase_id=phase_id)
        )

        with pytest.raises(DevResponseFailedError):
            await wait_task

        # Subscriptions should be cleaned up
        assert bus.get_subscriber_count(topics.DEV_PLAN_COMPLETED) == 0
        assert bus.get_subscriber_count(topics.DEV_PLAN_FAILED) == 0

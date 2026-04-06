"""
DevLoop Runtime Helpers

Provides utilities for awaiting dev-loop phase responses with deterministic
correlation, timeout handling, and proper cleanup.

Key function:
- :func:`await_dev_response`: Subscribe to completed/failed topics, filter by
  run_id and phase_id, and return the matching response or raise an exception.
"""

import asyncio
from typing import Optional

from genus.communication.message_bus import Message, MessageBus


class DevResponseTimeoutError(TimeoutError):
    """Raised when awaiting a dev-loop response times out.

    Attributes:
        run_id:    The run identifier that was being awaited.
        phase_id:  The phase identifier that was being awaited.
        timeout_s: The timeout duration in seconds.
    """

    def __init__(self, run_id: str, phase_id: str, timeout_s: float):
        self.run_id = run_id
        self.phase_id = phase_id
        self.timeout_s = timeout_s
        super().__init__(
            f"Timeout after {timeout_s}s waiting for response to "
            f"phase_id={phase_id!r} in run_id={run_id!r}"
        )


class DevResponseFailedError(RuntimeError):
    """Raised when a dev-loop phase fails.

    Attributes:
        run_id:    The run identifier.
        phase_id:  The phase identifier.
        error:     The error message from the failed response payload.
        message:   The complete failed message.
    """

    def __init__(self, run_id: str, phase_id: str, error: str, message: Message):
        self.run_id = run_id
        self.phase_id = phase_id
        self.error = error
        self.message = message
        super().__init__(
            f"Phase {phase_id!r} in run {run_id!r} failed: {error}"
        )


async def await_dev_response(
    bus: MessageBus,
    *,
    run_id: str,
    phase_id: str,
    completed_topic: str,
    failed_topic: str,
    timeout_s: float,
) -> Message:
    """Wait for a dev-loop phase response with correlation and timeout.

    Subscribes to both completed and failed topics, filters messages by
    run_id (in metadata) and phase_id (in payload), and returns the first
    matching message. Raises an exception if the phase fails or times out.

    Args:
        bus:             The MessageBus instance to subscribe to.
        run_id:          The run identifier to match in message metadata.
        phase_id:        The phase identifier to match in message payload.
        completed_topic: Topic string for successful completion (e.g., "dev.plan.completed").
        failed_topic:    Topic string for failure (e.g., "dev.plan.failed").
        timeout_s:       Maximum time to wait in seconds before raising DevResponseTimeoutError.

    Returns:
        The completed Message if the phase succeeds.

    Raises:
        DevResponseFailedError:  If a matching message arrives on the failed_topic.
        DevResponseTimeoutError: If no matching message arrives within timeout_s.

    Example::

        # Orchestrator publishes dev.plan.requested with phase_id
        plan_phase_id = new_phase_id(run_id, "plan")
        await bus.publish(
            dev_plan_requested_message(run_id, "orchestrator", phase_id=plan_phase_id)
        )

        # Wait for the planner agent to respond
        response = await await_dev_response(
            bus,
            run_id=run_id,
            phase_id=plan_phase_id,
            completed_topic=topics.DEV_PLAN_COMPLETED,
            failed_topic=topics.DEV_PLAN_FAILED,
            timeout_s=30.0,
        )
        plan = response.payload["plan"]
    """
    subscriber_id = f"await_dev_response:{phase_id}"
    response_future: asyncio.Future[Message] = asyncio.Future()

    async def on_completed(msg: Message) -> None:
        """Callback for completed topic."""
        # Check run_id in metadata
        if msg.metadata.get("run_id") != run_id:
            return
        # Check phase_id in payload
        if msg.payload.get("phase_id") != phase_id:
            return
        # Match found - resolve future with completed message
        if not response_future.done():
            response_future.set_result(msg)

    async def on_failed(msg: Message) -> None:
        """Callback for failed topic."""
        # Check run_id in metadata
        if msg.metadata.get("run_id") != run_id:
            return
        # Check phase_id in payload
        if msg.payload.get("phase_id") != phase_id:
            return
        # Match found - resolve future with exception
        if not response_future.done():
            error_text = msg.payload.get("error", "Unknown error")
            response_future.set_exception(
                DevResponseFailedError(run_id, phase_id, error_text, msg)
            )

    # Subscribe to both topics
    bus.subscribe(completed_topic, subscriber_id, on_completed)
    bus.subscribe(failed_topic, subscriber_id, on_failed)

    try:
        # Wait for response or timeout
        result = await asyncio.wait_for(response_future, timeout=timeout_s)
        return result
    except asyncio.TimeoutError:
        # Convert asyncio.TimeoutError to DevResponseTimeoutError
        raise DevResponseTimeoutError(run_id, phase_id, timeout_s)
    finally:
        # Clean up subscriptions
        bus.unsubscribe(completed_topic, subscriber_id)
        bus.unsubscribe(failed_topic, subscriber_id)

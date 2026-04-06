"""
DevLoop Runtime Helpers

Provides utilities for awaiting dev-loop phase responses with deterministic
correlation, timeout handling, and proper cleanup.

Key function:
- :func:`await_dev_response`: Subscribe to completed/failed topics, filter by
  run_id and phase_id, and return the matching response or raise an exception.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Callable, Optional

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


@dataclass
class DevResponseListener:
    """Listener for awaiting dev-loop phase responses.

    Subscribes immediately to completed/failed topics and provides methods
    to wait for responses and clean up subscriptions. This implements the
    listen-before-publish pattern to avoid race conditions.

    Use :func:`listen_for_dev_response` factory to create instances.

    Attributes:
        future:           The asyncio.Future that will be resolved with the response.
        subscriber_id:    Unique subscriber identifier for this listener.
        completed_topic:  Topic string for successful completion.
        failed_topic:     Topic string for failure.
        bus:              The MessageBus instance.
        run_id:           The run identifier being awaited.
        phase_id:         The phase identifier being awaited.
        _closed:          Internal flag to track cleanup state.
    """

    future: asyncio.Future[Message]
    subscriber_id: str
    completed_topic: str
    failed_topic: str
    bus: MessageBus
    run_id: str
    phase_id: str
    _closed: bool = field(default=False, init=False)

    async def wait(self, timeout_s: float) -> Message:
        """Wait for the response or timeout.

        Args:
            timeout_s: Maximum time to wait in seconds.

        Returns:
            The completed Message if the phase succeeds.

        Raises:
            DevResponseFailedError:  If a matching message arrives on the failed_topic.
            DevResponseTimeoutError: If no matching message arrives within timeout_s.
        """
        try:
            result = await asyncio.wait_for(self.future, timeout=timeout_s)
            return result
        except asyncio.TimeoutError as exc:
            raise DevResponseTimeoutError(self.run_id, self.phase_id, timeout_s) from exc

    def close(self) -> None:
        """Unsubscribe from topics and mark as closed.

        This method is idempotent - calling it multiple times is safe.
        """
        if self._closed:
            return
        self._closed = True
        self.bus.unsubscribe(self.completed_topic, self.subscriber_id)
        self.bus.unsubscribe(self.failed_topic, self.subscriber_id)


def listen_for_dev_response(
    bus: MessageBus,
    *,
    run_id: str,
    phase_id: str,
    completed_topic: str,
    failed_topic: str,
) -> DevResponseListener:
    """Subscribe to dev-loop response topics and return a listener.

    Creates a listener that immediately subscribes to both completed and failed
    topics, filtering by run_id (in metadata) and phase_id (in payload). This
    enables the listen-before-publish pattern to avoid race conditions.

    Args:
        bus:             The MessageBus instance to subscribe to.
        run_id:          The run identifier to match in message metadata.
        phase_id:        The phase identifier to match in message payload.
        completed_topic: Topic string for successful completion (e.g., "dev.plan.completed").
        failed_topic:    Topic string for failure (e.g., "dev.plan.failed").

    Returns:
        A DevResponseListener that is already subscribed and ready to receive messages.

    Example::

        # Create listener and subscribe immediately
        listener = listen_for_dev_response(
            bus, run_id=run_id, phase_id=phase_id,
            completed_topic=topics.DEV_PLAN_COMPLETED,
            failed_topic=topics.DEV_PLAN_FAILED,
        )
        try:
            # Now safe to publish - listener is already subscribed
            await bus.publish(plan_request_message)
            # Wait for response
            response = await listener.wait(timeout_s=30.0)
        finally:
            listener.close()
    """
    subscriber_id = f"await_dev_response:{phase_id}"
    response_future: asyncio.Future[Message] = asyncio.Future()

    async def on_completed(msg: Message) -> None:
        """Callback for completed topic."""
        if msg.metadata.get("run_id") != run_id:
            return
        if msg.payload.get("phase_id") != phase_id:
            return
        if not response_future.done():
            response_future.set_result(msg)

    async def on_failed(msg: Message) -> None:
        """Callback for failed topic."""
        if msg.metadata.get("run_id") != run_id:
            return
        if msg.payload.get("phase_id") != phase_id:
            return
        if not response_future.done():
            error_text = msg.payload.get("error", "Unknown error")
            response_future.set_exception(
                DevResponseFailedError(run_id, phase_id, error_text, msg)
            )

    # Subscribe immediately
    bus.subscribe(completed_topic, subscriber_id, on_completed)
    bus.subscribe(failed_topic, subscriber_id, on_failed)

    return DevResponseListener(
        future=response_future,
        subscriber_id=subscriber_id,
        completed_topic=completed_topic,
        failed_topic=failed_topic,
        bus=bus,
        run_id=run_id,
        phase_id=phase_id,
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

    Convenience wrapper around :func:`listen_for_dev_response` that handles
    subscription and cleanup automatically. For more control, use the listener
    pattern directly.

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
    listener = listen_for_dev_response(
        bus,
        run_id=run_id,
        phase_id=phase_id,
        completed_topic=completed_topic,
        failed_topic=failed_topic,
    )
    try:
        return await listener.wait(timeout_s)
    finally:
        listener.close()

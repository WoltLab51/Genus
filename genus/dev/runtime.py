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


class DevResponseAwaiter:
    """Context manager for awaiting dev-loop phase responses.

    Implements subscribe-before-publish pattern to avoid race conditions.
    Subscribes to completion/failure topics on entry, allowing the caller
    to publish the request message, then awaits the response.

    Usage::

        async with DevResponseAwaiter(
            bus, run_id=run_id, phase_id=phase_id,
            completed_topic=topics.DEV_PLAN_COMPLETED,
            failed_topic=topics.DEV_PLAN_FAILED,
            timeout_s=30.0
        ) as awaiter:
            # Subscriptions are now active - safe to publish
            await bus.publish(plan_request_message)
            # Wait for response
            response = await awaiter.wait()
    """

    def __init__(
        self,
        bus: MessageBus,
        *,
        run_id: str,
        phase_id: str,
        completed_topic: str,
        failed_topic: str,
        timeout_s: float,
    ):
        self._bus = bus
        self._run_id = run_id
        self._phase_id = phase_id
        self._completed_topic = completed_topic
        self._failed_topic = failed_topic
        self._timeout_s = timeout_s
        self._subscriber_id = f"await_dev_response:{phase_id}"
        self._response_future: Optional[asyncio.Future[Message]] = None

    async def __aenter__(self):
        """Subscribe to topics on context entry."""
        self._response_future = asyncio.Future()

        async def on_completed(msg: Message) -> None:
            """Callback for completed topic."""
            if msg.metadata.get("run_id") != self._run_id:
                return
            if msg.payload.get("phase_id") != self._phase_id:
                return
            if not self._response_future.done():
                self._response_future.set_result(msg)

        async def on_failed(msg: Message) -> None:
            """Callback for failed topic."""
            if msg.metadata.get("run_id") != self._run_id:
                return
            if msg.payload.get("phase_id") != self._phase_id:
                return
            if not self._response_future.done():
                error_text = msg.payload.get("error", "Unknown error")
                self._response_future.set_exception(
                    DevResponseFailedError(self._run_id, self._phase_id, error_text, msg)
                )

        # Store callbacks for cleanup
        self._on_completed = on_completed
        self._on_failed = on_failed

        # Subscribe to both topics
        self._bus.subscribe(self._completed_topic, self._subscriber_id, on_completed)
        self._bus.subscribe(self._failed_topic, self._subscriber_id, on_failed)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Unsubscribe on context exit."""
        self._bus.unsubscribe(self._completed_topic, self._subscriber_id)
        self._bus.unsubscribe(self._failed_topic, self._subscriber_id)
        return False

    async def wait(self) -> Message:
        """Wait for the response or timeout.

        Returns:
            The completed Message if the phase succeeds.

        Raises:
            DevResponseFailedError:  If a matching message arrives on the failed_topic.
            DevResponseTimeoutError: If no matching message arrives within timeout_s.
        """
        try:
            result = await asyncio.wait_for(self._response_future, timeout=self._timeout_s)
            return result
        except asyncio.TimeoutError:
            raise DevResponseTimeoutError(self._run_id, self._phase_id, self._timeout_s)


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

    **Note:** This function has a race condition if responders publish their
    response during the request callback. For deterministic behavior, use
    :class:`DevResponseAwaiter` context manager to subscribe before publishing.

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
    async with DevResponseAwaiter(
        bus,
        run_id=run_id,
        phase_id=phase_id,
        completed_topic=completed_topic,
        failed_topic=failed_topic,
        timeout_s=timeout_s,
    ) as awaiter:
        return await awaiter.wait()

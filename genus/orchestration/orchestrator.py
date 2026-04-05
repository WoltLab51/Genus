"""
Orchestrator

Executes a run by delegating tool calls via the MessageBus.  Each tool
call is identified by a UUID ``step_id`` and correlated with its response
via ``(metadata["run_id"], payload["step_id"])``.

Lifecycle events are published exclusively through the factory functions
in :mod:`genus.run.events`.  Tool-call events are published through the
factory functions in :mod:`genus.tools.events`.

Usage::

    bus = MessageBus()
    orc = Orchestrator(bus)
    await orc.initialize()
    run_id = await orc.run("Summarize the quarterly report")

The :meth:`run` method returns once all steps have been completed (or the
run has failed).  It is safe to call concurrently for different problems,
because every run maintains its own ``asyncio.Future`` map keyed by
``step_id``.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from genus.communication.message_bus import Message, MessageBus
from genus.core.run import new_run_id
from genus.run.events import (
    run_completed_message,
    run_failed_message,
    run_started_message,
    run_step_completed_message,
    run_step_failed_message,
    run_step_planned_message,
    run_step_started_message,
)
from genus.tools import topics as tool_topics
from genus.tools.events import (
    tool_call_requested_message,
)


@dataclass
class _Step:
    """Internal description of a single orchestrated step."""

    step_id: str
    tool_name: str
    tool_args: Dict[str, Any]
    future: "asyncio.Future[Message]" = field(default=None)  # type: ignore[assignment]


class Orchestrator:
    """Minimal Orchestrator that delegates tool calls via the MessageBus.

    Args:
        bus:       The :class:`~genus.communication.message_bus.MessageBus`
                   used for all publish/subscribe operations.
        sender_id: Identifier used as ``sender_id`` on all published messages.
                   Defaults to ``"Orchestrator"``.
    """

    def __init__(
        self,
        bus: MessageBus,
        sender_id: str = "Orchestrator",
        tool_timeout_s: float = 30.0,
    ) -> None:
        self._bus = bus
        self._sender_id = sender_id
        self._tool_timeout_s = tool_timeout_s
        # Maps step_id -> Future[Message] for pending tool calls.
        # Keyed by run_id so concurrent runs don't interfere.
        self._pending: Dict[str, Dict[str, "asyncio.Future[Message]"]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Subscribe to tool-call response topics.

        Must be called before :meth:`run`.
        """
        self._bus.subscribe(
            tool_topics.TOOL_CALL_SUCCEEDED,
            self._sender_id,
            self._on_tool_response,
        )
        self._bus.subscribe(
            tool_topics.TOOL_CALL_FAILED,
            self._sender_id,
            self._on_tool_response,
        )

    async def shutdown(self) -> None:
        """Unsubscribe from all tool-call response topics."""
        self._bus.unsubscribe(tool_topics.TOOL_CALL_SUCCEEDED, self._sender_id)
        self._bus.unsubscribe(tool_topics.TOOL_CALL_FAILED, self._sender_id)

    # ------------------------------------------------------------------
    # Run entry-point
    # ------------------------------------------------------------------

    async def run(
        self,
        problem: str,
        *,
        steps: Optional[List[Dict[str, Any]]] = None,
        sender_id: Optional[str] = None,
    ) -> str:
        """Execute a run for *problem* and return the ``run_id``.

        Args:
            problem:   Human-readable problem / goal description.  Used as
                       the slug for :func:`~genus.core.run.new_run_id`.
            steps:     Optional explicit list of step descriptors.  Each
                       entry must have ``"tool_name"`` and ``"tool_args"``
                       keys.  When omitted, two deterministic default steps
                       are used (``echo`` then ``summarize``).
            sender_id: Override the orchestrator ``sender_id`` for this run.

        Returns:
            The ``run_id`` string (timestamp__slug__suffix format).

        Raises:
            RuntimeError: When a tool call fails during the run.
        """
        sid = sender_id or self._sender_id
        run_id = new_run_id(slug=problem)

        # Determine steps
        if steps is None:
            steps = [
                {"tool_name": "echo", "tool_args": {"message": problem}},
                {"tool_name": "summarize", "tool_args": {"text": problem}},
            ]

        # Build internal Step objects with UUID IDs; futures are created here
        # inside the running coroutine so they are bound to the correct loop.
        loop = asyncio.get_running_loop()
        step_objects: List[_Step] = [
            _Step(
                step_id=str(uuid.uuid4()),
                tool_name=s["tool_name"],
                tool_args=s["tool_args"],
                future=loop.create_future(),
            )
            for s in steps
        ]

        # Register futures for this run
        self._pending[run_id] = {s.step_id: s.future for s in step_objects}

        # --- publish run.started ---
        await self._bus.publish(run_started_message(run_id, sid, payload={"problem": problem}))

        # --- publish run.step.planned for all steps ---
        for step in step_objects:
            await self._bus.publish(
                run_step_planned_message(
                    run_id,
                    sid,
                    step.step_id,
                    payload={"tool_name": step.tool_name},
                )
            )

        # --- execute steps sequentially ---
        try:
            for step in step_objects:
                await self._execute_step(run_id, sid, step)
        except _StepFailed as exc:
            await self._bus.publish(
                run_failed_message(run_id, sid, payload={"error": str(exc)})
            )
            raise RuntimeError(str(exc)) from exc
        finally:
            self._pending.pop(run_id, None)

        # --- run completed ---
        await self._bus.publish(run_completed_message(run_id, sid))
        return run_id

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    async def _execute_step(
        self, run_id: str, sender_id: str, step: _Step
    ) -> None:
        """Publish tool.call.requested, wait for response, publish lifecycle events."""
        await self._bus.publish(
            run_step_started_message(
                run_id,
                sender_id,
                step.step_id,
                payload={"tool_name": step.tool_name},
            )
        )
        await self._bus.publish(
            tool_call_requested_message(
                run_id,
                sender_id,
                step.step_id,
                step.tool_name,
                step.tool_args,
            )
        )

        # Wait for response (succeeded or failed), with timeout guard.
        try:
            response: Message = await asyncio.wait_for(
                step.future, timeout=self._tool_timeout_s
            )
        except asyncio.TimeoutError:
            await self._bus.publish(
                run_step_failed_message(
                    run_id,
                    sender_id,
                    step.step_id,
                    payload={"error": "timeout"},
                )
            )
            raise _StepFailed(
                f"Step {step.step_id!r} ({step.tool_name!r}) timed out"
                f" after {self._tool_timeout_s}s"
            )

        if response.topic == tool_topics.TOOL_CALL_SUCCEEDED:
            await self._bus.publish(
                run_step_completed_message(
                    run_id,
                    sender_id,
                    step.step_id,
                    payload={"result": response.payload.get("result")},
                )
            )
        else:
            error = response.payload.get("error", "unknown error")
            await self._bus.publish(
                run_step_failed_message(
                    run_id,
                    sender_id,
                    step.step_id,
                    payload={"error": error},
                )
            )
            raise _StepFailed(
                f"Step {step.step_id!r} ({step.tool_name!r}) failed: {error}"
            )

    # ------------------------------------------------------------------
    # Response handler
    # ------------------------------------------------------------------

    async def _on_tool_response(self, message: Message) -> None:
        """Handle incoming tool.call.succeeded / tool.call.failed messages."""
        run_id: Optional[str] = message.metadata.get("run_id")
        step_id: Optional[str] = message.payload.get("step_id") if isinstance(
            message.payload, dict
        ) else None

        if run_id is None or step_id is None:
            # Malformed response – missing correlation fields; drop silently.
            return

        run_futures = self._pending.get(run_id)
        if run_futures is None:
            # Response arrived for an unknown or already-completed run; drop.
            return

        future = run_futures.get(step_id)
        if future is None or future.done():
            # Late or duplicate response; drop silently.
            return

        future.set_result(message)


class _StepFailed(Exception):
    """Internal signal: a step returned tool.call.failed."""

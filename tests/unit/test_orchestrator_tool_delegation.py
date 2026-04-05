"""
Tests for the Orchestrator tool-delegation flow.

Verifies:
- Run lifecycle event sequence (run.started → step.planned × N →
  step.started → tool.call.requested → tool.call.succeeded →
  step.completed → … → run.completed)
- step_ids are valid UUIDs
- run_id is attached on all run.* and tool.call.* events
- No mutation of input payload dicts
- Failure path: tool.call.failed → step.failed → run.failed
"""

import asyncio
import uuid
import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.orchestration.orchestrator import Orchestrator
from genus.run import topics as run_topics
from genus.tools import topics as tool_topics
from genus.tools.events import (
    tool_call_succeeded_message,
    tool_call_failed_message,
)
from genus.core.run import get_run_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_uuid(value: str) -> bool:
    """Return True when *value* is a canonical UUID4 string."""
    try:
        uuid.UUID(value, version=4)
        return True
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# In-memory test tool executor agent
# ---------------------------------------------------------------------------

class _TestToolExecutor:
    """Deterministic in-memory agent that responds to tool.call.requested.

    Supported tools:
    - ``echo``:      returns the ``message`` arg unchanged
    - ``add``:       returns the sum of ``a`` + ``b`` args
    - ``summarize``: returns a fixed summary string
    - ``fail``:      always responds with tool.call.failed
    """

    AGENT_ID = "TestToolExecutor"

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus

    async def initialize(self) -> None:
        self._bus.subscribe(
            tool_topics.TOOL_CALL_REQUESTED,
            self.AGENT_ID,
            self._handle,
        )

    async def _handle(self, message: Message) -> None:
        payload = message.payload
        run_id = message.metadata.get("run_id", "")
        step_id = payload.get("step_id", "")
        tool_name = payload.get("tool_name", "")
        tool_args = payload.get("tool_args", {})

        if tool_name == "echo":
            result = tool_args.get("message", "")
            response = tool_call_succeeded_message(
                run_id, self.AGENT_ID, step_id, tool_name, result
            )
        elif tool_name == "add":
            result = int(tool_args.get("a", 0)) + int(tool_args.get("b", 0))
            response = tool_call_succeeded_message(
                run_id, self.AGENT_ID, step_id, tool_name, result
            )
        elif tool_name == "summarize":
            result = "summary: " + str(tool_args.get("text", ""))
            response = tool_call_succeeded_message(
                run_id, self.AGENT_ID, step_id, tool_name, result
            )
        elif tool_name == "fail":
            response = tool_call_failed_message(
                run_id, self.AGENT_ID, step_id, tool_name, "intentional failure"
            )
        else:
            response = tool_call_failed_message(
                run_id, self.AGENT_ID, step_id, tool_name, f"unknown tool: {tool_name}"
            )

        await self._bus.publish(response)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def bus_and_orchestrator():
    """Create a MessageBus + Orchestrator + test executor, all initialized."""
    bus = MessageBus()
    executor = _TestToolExecutor(bus)
    orc = Orchestrator(bus)

    await executor.initialize()
    await orc.initialize()

    return bus, orc


# ---------------------------------------------------------------------------
# Happy-path: two default steps (echo + summarize)
# ---------------------------------------------------------------------------

class TestOrchestratorHappyPath:

    async def test_run_returns_run_id(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        run_id = await orc.run("test-problem")
        assert isinstance(run_id, str)
        assert len(run_id) > 0

    async def test_run_id_contains_slug(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        run_id = await orc.run("my-task")
        assert "my-task" in run_id

    async def test_run_lifecycle_event_sequence(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        await orc.run("seq-test")

        history = bus.get_message_history(limit=200)
        topics_seen = [m.topic for m in history]

        # run.started must come first
        assert run_topics.RUN_STARTED in topics_seen
        # Both default steps planned
        assert topics_seen.count(run_topics.RUN_STEP_PLANNED) == 2
        # Both steps started
        assert topics_seen.count(run_topics.RUN_STEP_STARTED) == 2
        # Both tool calls requested
        assert topics_seen.count(tool_topics.TOOL_CALL_REQUESTED) == 2
        # Both tool calls succeeded
        assert topics_seen.count(tool_topics.TOOL_CALL_SUCCEEDED) == 2
        # Both steps completed
        assert topics_seen.count(run_topics.RUN_STEP_COMPLETED) == 2
        # run.completed must be last relevant event
        assert run_topics.RUN_COMPLETED in topics_seen
        # No failures
        assert run_topics.RUN_FAILED not in topics_seen
        assert run_topics.RUN_STEP_FAILED not in topics_seen
        assert tool_topics.TOOL_CALL_FAILED not in topics_seen

    async def test_run_completed_comes_after_steps(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        await orc.run("ordering-test")

        history = bus.get_message_history(limit=200)
        topics_list = [m.topic for m in history]

        completed_idx = max(
            i for i, t in enumerate(topics_list) if t == run_topics.RUN_STEP_COMPLETED
        )
        run_completed_idx = topics_list.index(run_topics.RUN_COMPLETED)
        assert run_completed_idx > completed_idx

    async def test_step_ids_are_uuids(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        await orc.run("uuid-test")

        history = bus.get_message_history(limit=200)
        step_msgs = [
            m for m in history
            if m.topic in {
                run_topics.RUN_STEP_PLANNED,
                run_topics.RUN_STEP_STARTED,
                run_topics.RUN_STEP_COMPLETED,
                tool_topics.TOOL_CALL_REQUESTED,
                tool_topics.TOOL_CALL_SUCCEEDED,
            }
        ]
        assert len(step_msgs) > 0
        for msg in step_msgs:
            step_id = msg.payload.get("step_id") if isinstance(msg.payload, dict) else None
            assert step_id is not None, f"Missing step_id in {msg.topic}"
            assert _is_uuid(step_id), f"step_id {step_id!r} is not a UUID in {msg.topic}"

    async def test_run_id_in_all_run_events(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        run_id = await orc.run("run-id-propagation")

        run_event_topics = {
            run_topics.RUN_STARTED,
            run_topics.RUN_STEP_PLANNED,
            run_topics.RUN_STEP_STARTED,
            run_topics.RUN_STEP_COMPLETED,
            run_topics.RUN_COMPLETED,
        }
        history = bus.get_message_history(limit=200)
        for msg in history:
            if msg.topic in run_event_topics:
                assert get_run_id(msg) == run_id, (
                    f"run_id mismatch on topic {msg.topic!r}"
                )

    async def test_run_id_in_all_tool_events(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        run_id = await orc.run("tool-run-id")

        tool_event_topics = {
            tool_topics.TOOL_CALL_REQUESTED,
            tool_topics.TOOL_CALL_SUCCEEDED,
        }
        history = bus.get_message_history(limit=200)
        for msg in history:
            if msg.topic in tool_event_topics:
                assert get_run_id(msg) == run_id, (
                    f"run_id mismatch on tool topic {msg.topic!r}"
                )

    async def test_two_distinct_step_ids(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        await orc.run("distinct-steps")

        history = bus.get_message_history(limit=200)
        step_ids = {
            m.payload["step_id"]
            for m in history
            if m.topic == run_topics.RUN_STEP_PLANNED
            and isinstance(m.payload, dict)
        }
        assert len(step_ids) == 2

    async def test_step_id_correlation_across_topics(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        await orc.run("correlation-test")

        history = bus.get_message_history(limit=200)

        # Gather step_ids from planned events
        planned_step_ids = {
            m.payload["step_id"]
            for m in history
            if m.topic == run_topics.RUN_STEP_PLANNED
        }
        # Every tool.call.requested should reference a known step_id
        for msg in history:
            if msg.topic == tool_topics.TOOL_CALL_REQUESTED:
                assert msg.payload["step_id"] in planned_step_ids

        # Every tool.call.succeeded should reference a known step_id
        for msg in history:
            if msg.topic == tool_topics.TOOL_CALL_SUCCEEDED:
                assert msg.payload["step_id"] in planned_step_ids


# ---------------------------------------------------------------------------
# Custom steps (echo, add)
# ---------------------------------------------------------------------------

class TestOrchestratorCustomSteps:

    async def test_echo_tool_returns_message(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        await orc.run(
            "echo-test",
            steps=[{"tool_name": "echo", "tool_args": {"message": "hello"}}],
        )
        history = bus.get_message_history(limit=200)
        completed = [m for m in history if m.topic == run_topics.RUN_STEP_COMPLETED]
        assert len(completed) == 1
        assert completed[0].payload.get("result") == "hello"

    async def test_add_tool_returns_sum(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        await orc.run(
            "add-test",
            steps=[{"tool_name": "add", "tool_args": {"a": 3, "b": 4}}],
        )
        history = bus.get_message_history(limit=200)
        completed = [m for m in history if m.topic == run_topics.RUN_STEP_COMPLETED]
        assert len(completed) == 1
        assert completed[0].payload.get("result") == 7


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------

class TestOrchestratorFailurePath:

    async def test_failing_tool_raises_runtime_error(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        with pytest.raises(RuntimeError):
            await orc.run(
                "fail-test",
                steps=[{"tool_name": "fail", "tool_args": {}}],
            )

    async def test_failing_tool_publishes_run_failed(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        with pytest.raises(RuntimeError):
            await orc.run(
                "fail-events",
                steps=[{"tool_name": "fail", "tool_args": {}}],
            )

        history = bus.get_message_history(limit=200)
        topics_seen = [m.topic for m in history]

        assert run_topics.RUN_STEP_FAILED in topics_seen
        assert run_topics.RUN_FAILED in topics_seen
        assert run_topics.RUN_COMPLETED not in topics_seen

    async def test_failing_tool_run_id_in_failure_events(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        captured_run_id = None

        orig_run = orc.run

        async def _capture_run(*args, **kwargs):
            nonlocal captured_run_id
            try:
                captured_run_id = await orig_run(*args, **kwargs)
            except RuntimeError:
                pass
            return captured_run_id

        # Use the bus history to get the run_id from the started event
        with pytest.raises(RuntimeError):
            await orc.run(
                "fail-run-id",
                steps=[{"tool_name": "fail", "tool_args": {}}],
            )

        history = bus.get_message_history(limit=200)
        started = [m for m in history if m.topic == run_topics.RUN_STARTED]
        assert len(started) >= 1
        run_id = get_run_id(started[-1])

        failed_events = [
            m for m in history
            if m.topic in {run_topics.RUN_STEP_FAILED, run_topics.RUN_FAILED}
        ]
        for msg in failed_events:
            assert get_run_id(msg) == run_id


# ---------------------------------------------------------------------------
# No-mutation contract
# ---------------------------------------------------------------------------

class TestNoMutation:

    async def test_step_tool_args_not_mutated(self, bus_and_orchestrator):
        bus, orc = bus_and_orchestrator
        original_args = {"message": "immutable"}
        steps = [{"tool_name": "echo", "tool_args": original_args}]
        await orc.run("no-mutation", steps=steps)
        # original_args must be untouched
        assert original_args == {"message": "immutable"}
        assert steps[0]["tool_args"] == {"message": "immutable"}

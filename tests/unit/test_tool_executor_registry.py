"""
Tests for ToolExecutor with ToolRegistry integration.

Verifies:
- _handle_tool_call logic with registry lookup
- Unknown tool returns tool.call.failed
- echo/add/summarize tools succeed
- Invalid arguments return tool.call.failed
- Uses Message factories from genus.tools.events

These tests isolate _handle_tool_call without requiring Redis.
"""

import asyncio
import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.tools import topics as tool_topics
from genus.tools.events import tool_call_requested_message
from genus.tools.registry import ToolRegistry, ToolSpec
from genus.tools.impl.echo import echo
from genus.tools.impl.add import add
from genus.tools.impl.summarize import summarize


# ---------------------------------------------------------------------------
# Helper to simulate _handle_tool_call
# ---------------------------------------------------------------------------

async def _simulate_handle_tool_call(
    bus: MessageBus, registry: ToolRegistry, message: Message
) -> None:
    """Simulate the _handle_tool_call logic from tool_executor.py.

    This is a simplified version for testing without Redis dependencies.
    """
    from genus.tools.events import tool_call_failed_message, tool_call_succeeded_message
    import inspect

    AGENT_ID = "TestToolExecutor"

    payload = message.payload if isinstance(message.payload, dict) else {}
    run_id: str = message.metadata.get("run_id", "")
    step_id: str = payload.get("step_id", "")
    tool_name: str = payload.get("tool_name", "")
    tool_args: dict = payload.get("tool_args", {})

    # Look up the tool in the registry
    spec = registry.get(tool_name)
    if spec is None:
        error = "unknown tool: {}".format(tool_name)
        response = tool_call_failed_message(
            run_id, AGENT_ID, step_id, tool_name, error
        )
        await bus.publish(response)
        return

    # Execute the tool handler
    try:
        handler = spec.handler
        # Check if the handler is async or sync
        if inspect.iscoroutinefunction(handler):
            result = await handler(**tool_args)
        else:
            result = handler(**tool_args)

        response = tool_call_succeeded_message(
            run_id, AGENT_ID, step_id, tool_name, result
        )
    except TypeError as exc:
        # Wrong arguments passed to the handler
        error = "invalid arguments: {}".format(str(exc))
        response = tool_call_failed_message(
            run_id, AGENT_ID, step_id, tool_name, error
        )
    except Exception as exc:
        # Other execution errors
        error = str(exc)
        response = tool_call_failed_message(
            run_id, AGENT_ID, step_id, tool_name, error
        )

    await bus.publish(response)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bus():
    """Create an in-memory MessageBus."""
    return MessageBus()


@pytest.fixture
def registry():
    """Create a ToolRegistry with standard tools."""
    reg = ToolRegistry()
    reg.register(ToolSpec(name="echo", handler=echo))
    reg.register(ToolSpec(name="add", handler=add))
    reg.register(ToolSpec(name="summarize", handler=summarize))
    return reg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestToolExecutorRegistry:

    async def test_unknown_tool_returns_failed(self, bus, registry):
        """Unknown tool should return tool.call.failed."""
        request = tool_call_requested_message(
            run_id="test-run",
            sender_id="Orchestrator",
            step_id="step-1",
            tool_name="nonexistent",
            tool_args={},
        )

        await _simulate_handle_tool_call(bus, registry, request)

        history = bus.get_message_history()
        assert len(history) == 1
        response = history[0]

        assert response.topic == tool_topics.TOOL_CALL_FAILED
        assert response.payload["tool_name"] == "nonexistent"
        assert "unknown tool" in response.payload["error"]

    async def test_echo_tool_success(self, bus, registry):
        """Echo tool should return the message unchanged."""
        request = tool_call_requested_message(
            run_id="test-run",
            sender_id="Orchestrator",
            step_id="step-1",
            tool_name="echo",
            tool_args={"message": "hello world"},
        )

        await _simulate_handle_tool_call(bus, registry, request)

        history = bus.get_message_history()
        assert len(history) == 1
        response = history[0]

        assert response.topic == tool_topics.TOOL_CALL_SUCCEEDED
        assert response.payload["tool_name"] == "echo"
        assert response.payload["result"] == "hello world"

    async def test_add_tool_success(self, bus, registry):
        """Add tool should return the sum of a and b."""
        request = tool_call_requested_message(
            run_id="test-run",
            sender_id="Orchestrator",
            step_id="step-2",
            tool_name="add",
            tool_args={"a": 5, "b": 7},
        )

        await _simulate_handle_tool_call(bus, registry, request)

        history = bus.get_message_history()
        assert len(history) == 1
        response = history[0]

        assert response.topic == tool_topics.TOOL_CALL_SUCCEEDED
        assert response.payload["tool_name"] == "add"
        assert response.payload["result"] == 12

    async def test_summarize_tool_success(self, bus, registry):
        """Summarize tool should return 'summary: <text>'."""
        request = tool_call_requested_message(
            run_id="test-run",
            sender_id="Orchestrator",
            step_id="step-3",
            tool_name="summarize",
            tool_args={"text": "long document"},
        )

        await _simulate_handle_tool_call(bus, registry, request)

        history = bus.get_message_history()
        assert len(history) == 1
        response = history[0]

        assert response.topic == tool_topics.TOOL_CALL_SUCCEEDED
        assert response.payload["tool_name"] == "summarize"
        assert response.payload["result"] == "summary: long document"

    async def test_invalid_arguments_returns_failed(self, bus, registry):
        """Calling a tool with wrong arguments should return tool.call.failed."""
        request = tool_call_requested_message(
            run_id="test-run",
            sender_id="Orchestrator",
            step_id="step-4",
            tool_name="add",
            tool_args={"a": 5},  # Missing 'b' argument
        )

        await _simulate_handle_tool_call(bus, registry, request)

        history = bus.get_message_history()
        assert len(history) == 1
        response = history[0]

        assert response.topic == tool_topics.TOOL_CALL_FAILED
        assert response.payload["tool_name"] == "add"
        assert "invalid arguments" in response.payload["error"]

    async def test_run_id_preserved_in_response(self, bus, registry):
        """The run_id should be preserved in the response metadata."""
        request = tool_call_requested_message(
            run_id="my-special-run-123",
            sender_id="Orchestrator",
            step_id="step-5",
            tool_name="echo",
            tool_args={"message": "test"},
        )

        await _simulate_handle_tool_call(bus, registry, request)

        history = bus.get_message_history()
        assert len(history) == 1
        response = history[0]

        assert response.metadata.get("run_id") == "my-special-run-123"

    async def test_step_id_preserved_in_response(self, bus, registry):
        """The step_id should be preserved in the response payload."""
        request = tool_call_requested_message(
            run_id="test-run",
            sender_id="Orchestrator",
            step_id="unique-step-id-789",
            tool_name="echo",
            tool_args={"message": "test"},
        )

        await _simulate_handle_tool_call(bus, registry, request)

        history = bus.get_message_history()
        assert len(history) == 1
        response = history[0]

        assert response.payload["step_id"] == "unique-step-id-789"

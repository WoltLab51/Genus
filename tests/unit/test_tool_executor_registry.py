"""
Tests for ToolExecutor with ToolRegistry integration.

Verifies:
- _handle_tool_call logic with registry lookup
- Unknown tool returns tool.call.failed
- echo/add/summarize tools succeed
- Invalid arguments return tool.call.failed
- Uses Message factories from genus.tools.events

These tests exercise the real implementation in genus.tools.executor
without requiring Redis.
"""

import asyncio
import pytest

from genus.communication.message_bus import MessageBus
from genus.tools import topics as tool_topics
from genus.tools.events import tool_call_requested_message
from genus.tools.executor import _build_registry, _handle_tool_call


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bus():
    """Create an in-memory MessageBus."""
    return MessageBus()


@pytest.fixture
def registry():
    """Create a ToolRegistry with standard tools via the real _build_registry."""
    return _build_registry()


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

        await _handle_tool_call(bus, registry, request)

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

        await _handle_tool_call(bus, registry, request)

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

        await _handle_tool_call(bus, registry, request)

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

        await _handle_tool_call(bus, registry, request)

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

        await _handle_tool_call(bus, registry, request)

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

        await _handle_tool_call(bus, registry, request)

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

        await _handle_tool_call(bus, registry, request)

        history = bus.get_message_history()
        assert len(history) == 1
        response = history[0]

        assert response.payload["step_id"] == "unique-step-id-789"

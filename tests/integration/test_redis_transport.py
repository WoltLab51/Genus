"""
Integration tests for the Redis transport layer.

These tests are **skipped automatically** unless the ``GENUS_REDIS_URL``
environment variable is set to a reachable Redis instance.

Run locally::

    export GENUS_REDIS_URL=redis://localhost:6379/0
    python -m pytest tests/integration/test_redis_transport.py -v

CI: set ``GENUS_REDIS_URL`` as a GitHub Actions environment variable or
service container to enable these tests.
"""

import asyncio
import os

import pytest

REDIS_URL = os.environ.get("GENUS_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not REDIS_URL,
    reason="GENUS_REDIS_URL not set – skipping Redis integration tests",
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def redis_bus():
    """Provide a connected RedisMessageBus and close it after the test."""
    from genus.communication.redis_message_bus import RedisMessageBus

    bus = RedisMessageBus(redis_url=REDIS_URL)
    await bus.connect()
    yield bus
    await bus.close()


# ---------------------------------------------------------------------------
# Serialization / transport round-trip
# ---------------------------------------------------------------------------


class TestRedisTransportRoundTrip:
    """Verify that a published message arrives at a subscriber."""

    async def test_publish_subscribe_exact_topic(self, redis_bus):
        """A message published to a topic must be received by a subscriber."""
        received: list = []
        redis_bus.subscribe("test.ping", "test-sub", lambda m: received.append(m))

        # Give the subscription task time to register with Redis
        await asyncio.sleep(0.3)

        from genus.communication.message_bus import Message

        msg = Message(topic="test.ping", payload={"hello": "world"}, sender_id="test")
        await redis_bus.publish(msg)

        # Wait for the message to arrive
        deadline = asyncio.get_running_loop().time() + 3.0
        while not received and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].payload == {"hello": "world"}
        assert received[0].topic == "test.ping"

    async def test_run_id_preserved_across_redis(self, redis_bus):
        """run_id in metadata must survive the Redis serialization round-trip."""
        from genus.communication.message_bus import Message
        from genus.core.run import attach_run_id, get_run_id

        received: list = []
        redis_bus.subscribe("test.run_id", "run-sub", lambda m: received.append(m))
        await asyncio.sleep(0.3)

        run_id = "2026-04-05T19-40-20Z__integration__abc123"
        msg = Message(topic="test.run_id", payload={}, sender_id="test")
        msg = attach_run_id(msg, run_id)
        await redis_bus.publish(msg)

        deadline = asyncio.get_running_loop().time() + 3.0
        while not received and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.05)

        assert received
        assert get_run_id(received[0]) == run_id


# ---------------------------------------------------------------------------
# Full end-to-end: Orchestrator + ToolExecutor on a shared bus
# ---------------------------------------------------------------------------


class TestOrchestratorToolExecutorEndToEnd:
    """Verify that Orchestrator and ToolExecutor communicate via Redis."""

    async def test_echo_tool_via_redis(self, redis_bus):
        """Orchestrator should complete an echo run via the shared Redis bus."""
        from genus.communication.message_bus import Message
        from genus.orchestration.orchestrator import Orchestrator
        from genus.tools import topics as tool_topics
        from genus.tools.events import tool_call_succeeded_message

        # Inline mini-executor on the same bus (simulates the ToolExecutor process)
        async def _executor_handler(message: Message) -> None:
            payload = message.payload if isinstance(message.payload, dict) else {}
            run_id = message.metadata.get("run_id", "")
            step_id = payload.get("step_id", "")
            tool_name = payload.get("tool_name", "")
            tool_args = payload.get("tool_args", {})
            if tool_name == "echo":
                result = tool_args.get("message", "")
            else:
                result = "ok"
            response = tool_call_succeeded_message(
                run_id, "TestExecutor", step_id, tool_name, result
            )
            await redis_bus.publish(response)

        redis_bus.subscribe(
            tool_topics.TOOL_CALL_REQUESTED, "TestExecutor", _executor_handler
        )

        orc = Orchestrator(redis_bus, tool_timeout_s=5.0)
        await orc.initialize()

        # Give subscriptions time to register
        await asyncio.sleep(0.5)

        run_id = await orc.run(
            "redis-echo-test",
            steps=[{"tool_name": "echo", "tool_args": {"message": "hello-redis"}}],
        )
        assert isinstance(run_id, str)
        assert "redis-echo-test" in run_id

    async def test_add_tool_via_redis(self, redis_bus):
        """Orchestrator should complete an add run and receive the correct result."""
        from genus.communication.message_bus import Message
        from genus.orchestration.orchestrator import Orchestrator
        from genus.run import topics as run_topics
        from genus.tools import topics as tool_topics
        from genus.tools.events import tool_call_succeeded_message

        results: list = []

        async def _executor_handler(message: Message) -> None:
            payload = message.payload if isinstance(message.payload, dict) else {}
            run_id = message.metadata.get("run_id", "")
            step_id = payload.get("step_id", "")
            tool_name = payload.get("tool_name", "")
            tool_args = payload.get("tool_args", {})
            if tool_name == "add":
                result = int(tool_args.get("a", 0)) + int(tool_args.get("b", 0))
            else:
                result = None
            response = tool_call_succeeded_message(
                run_id, "AddExecutor", step_id, tool_name, result
            )
            await redis_bus.publish(response)

        redis_bus.subscribe(
            tool_topics.TOOL_CALL_REQUESTED, "AddExecutor", _executor_handler
        )

        # Track results
        async def _track_completed(message: Message) -> None:
            if isinstance(message.payload, dict):
                results.append(message.payload.get("result"))

        redis_bus.subscribe(run_topics.RUN_STEP_COMPLETED, "ResultTracker", _track_completed)

        orc = Orchestrator(redis_bus, tool_timeout_s=5.0)
        await orc.initialize()
        await asyncio.sleep(0.5)

        await orc.run(
            "redis-add-test",
            steps=[{"tool_name": "add", "tool_args": {"a": 10, "b": 32}}],
        )

        # Wait briefly for tracker to receive the completed event
        deadline = asyncio.get_running_loop().time() + 3.0
        while not results and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.05)

        assert results == [42]

"""
Tool Executor Process

Standalone process that subscribes to ``tool.call.requested`` via Redis
Pub/Sub and responds with ``tool.call.succeeded`` or ``tool.call.failed``.

Run::

    python -m genus.cli.tool_executor

Environment variables
---------------------
``GENUS_REDIS_URL``
    Redis connection URL.  Defaults to ``redis://localhost:6379/0``.

Supported tools (whitelist)
---------------------------
``echo``
    Returns the ``message`` argument unchanged.

``add``
    Returns the integer sum of arguments ``a`` and ``b``.

``summarize``
    Returns a fixed deterministic summary string of the ``text`` argument.
"""

import asyncio
import inspect
import logging
import os
import signal
import sys

from genus.communication.message_bus import Message
from genus.communication.redis_message_bus import RedisMessageBus
from genus.communication.secure_bus import SecureMessageBus
from genus.tools import topics as tool_topics
from genus.tools.events import tool_call_failed_message, tool_call_succeeded_message
from genus.tools.registry import ToolRegistry, ToolSpec
from genus.tools.impl.echo import echo
from genus.tools.impl.add import add
from genus.tools.impl.summarize import summarize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ToolExecutor] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

AGENT_ID = "ToolExecutor"

# ---------------------------------------------------------------------------
# Tool registry setup
# ---------------------------------------------------------------------------

def _build_registry() -> ToolRegistry:
    """Build and populate the tool registry with standard tools.

    Returns:
        A ToolRegistry with echo, add, and summarize registered.
    """
    registry = ToolRegistry()
    registry.register(ToolSpec(name="echo", handler=echo, description="Echo message back"))
    registry.register(ToolSpec(name="add", handler=add, description="Add two integers"))
    registry.register(
        ToolSpec(name="summarize", handler=summarize, description="Summarize text")
    )
    return registry


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------

async def _handle_tool_call(
    bus: SecureMessageBus, registry: ToolRegistry, message: Message
) -> None:
    """Process a single ``tool.call.requested`` message.

    Args:
        bus: The message bus for publishing responses.
        registry: The tool registry to look up tools.
        message: The incoming tool.call.requested message.
    """
    payload = message.payload if isinstance(message.payload, dict) else {}
    run_id: str = message.metadata.get("run_id", "")
    step_id: str = payload.get("step_id", "")
    tool_name: str = payload.get("tool_name", "")
    tool_args: dict = payload.get("tool_args", {})

    logger.info("Received tool.call.requested: tool=%r step_id=%s", tool_name, step_id)

    # Look up the tool in the registry
    spec = registry.get(tool_name)
    if spec is None:
        error = "unknown tool: {}".format(tool_name)
        response = tool_call_failed_message(
            run_id, AGENT_ID, step_id, tool_name, error
        )
        logger.warning("Tool %r not found in registry", tool_name)
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
        logger.info("Tool %r succeeded: result=%r", tool_name, result)
    except TypeError as exc:
        # Wrong arguments passed to the handler
        error = "invalid arguments: {}".format(str(exc))
        response = tool_call_failed_message(
            run_id, AGENT_ID, step_id, tool_name, error
        )
        logger.warning("Tool %r failed with invalid arguments: %s", tool_name, error)
    except Exception as exc:
        # Other execution errors
        error = str(exc)
        response = tool_call_failed_message(
            run_id, AGENT_ID, step_id, tool_name, error
        )
        logger.warning("Tool %r failed: %s", tool_name, error)

    await bus.publish(response)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    redis_url = os.environ.get("GENUS_REDIS_URL", "redis://localhost:6379/0")
    logger.info("Connecting to Redis at %s", redis_url)

    inner_bus = RedisMessageBus(redis_url=redis_url)
    await inner_bus.connect()

    bus = SecureMessageBus(inner_bus)

    # Build the tool registry
    registry = _build_registry()
    logger.info("Registered tools: %s", ", ".join(registry.list_names()))

    async def handler(message: Message) -> None:
        await _handle_tool_call(bus, registry, message)

    bus.subscribe(tool_topics.TOOL_CALL_REQUESTED, AGENT_ID, handler)

    # Give the subscription task time to register with Redis
    await asyncio.sleep(0.2)

    logger.info(
        "ToolExecutor ready.  Listening on %r.  Supported tools: %s",
        tool_topics.TOOL_CALL_REQUESTED,
        ", ".join(registry.list_names()),
    )

    # Keep running until SIGINT/SIGTERM
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _on_signal():
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except (NotImplementedError, OSError):
            # Windows does not support add_signal_handler
            pass

    await stop_event.wait()
    logger.info("Shutting down ToolExecutor …")
    await bus.close()
    logger.info("ToolExecutor stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

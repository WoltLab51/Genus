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
import logging
import os
import signal
import sys

from genus.communication.message_bus import Message
from genus.communication.redis_message_bus import RedisMessageBus
from genus.communication.secure_bus import SecureMessageBus
from genus.tools import topics as tool_topics
from genus.tools.events import tool_call_failed_message, tool_call_succeeded_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ToolExecutor] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

AGENT_ID = "ToolExecutor"

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

SUPPORTED_TOOLS = {"echo", "add", "summarize"}


def _run_tool(tool_name: str, tool_args: dict):
    """Execute *tool_name* with *tool_args* and return the result.

    Raises:
        KeyError:  If a required argument is missing.
        ValueError: If argument types are invalid.
        LookupError: If the tool is not in the whitelist.
    """
    if tool_name == "echo":
        return tool_args.get("message", "")
    if tool_name == "add":
        return int(tool_args.get("a", 0)) + int(tool_args.get("b", 0))
    if tool_name == "summarize":
        return "summary: " + str(tool_args.get("text", ""))
    raise LookupError(f"Unknown tool: {tool_name!r}")


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------

async def _handle_tool_call(bus: SecureMessageBus, message: Message) -> None:
    """Process a single ``tool.call.requested`` message."""
    payload = message.payload if isinstance(message.payload, dict) else {}
    run_id: str = message.metadata.get("run_id", "")
    step_id: str = payload.get("step_id", "")
    tool_name: str = payload.get("tool_name", "")
    tool_args: dict = payload.get("tool_args", {})

    logger.info("Received tool.call.requested: tool=%r step_id=%s", tool_name, step_id)

    try:
        result = _run_tool(tool_name, tool_args)
        response = tool_call_succeeded_message(
            run_id, AGENT_ID, step_id, tool_name, result
        )
        logger.info("Tool %r succeeded: result=%r", tool_name, result)
    except Exception as exc:
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

    async def handler(message: Message) -> None:
        await _handle_tool_call(bus, message)

    bus.subscribe(tool_topics.TOOL_CALL_REQUESTED, AGENT_ID, handler)

    # Give the subscription task time to register with Redis
    await asyncio.sleep(0.2)

    logger.info(
        "ToolExecutor ready.  Listening on %r.  Supported tools: %s",
        tool_topics.TOOL_CALL_REQUESTED,
        ", ".join(sorted(SUPPORTED_TOOLS)),
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

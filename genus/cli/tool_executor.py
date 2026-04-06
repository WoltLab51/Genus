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
from genus.tools.executor import AGENT_ID, _build_registry, _handle_tool_call

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ToolExecutor] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


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

"""
Tool Executor Core Logic

Provides :func:`_build_registry` and :func:`_handle_tool_call` as importable,
Redis-free functions that can be tested directly and reused by the CLI.

The CLI (``genus.cli.tool_executor``) imports and calls these functions so
that tests exercise the real implementation without any Redis dependency.
"""

import inspect
import logging

from genus.communication.message_bus import Message, MessageBus
from genus.tools.events import tool_call_failed_message, tool_call_succeeded_message
from genus.tools.impl.add import add
from genus.tools.impl.echo import echo
from genus.tools.impl.summarize import summarize
from genus.tools.registry import ToolRegistry, ToolSpec

logger = logging.getLogger(__name__)

AGENT_ID = "ToolExecutor"


def _build_registry() -> ToolRegistry:
    """Build and populate the tool registry with standard tools.

    Returns:
        A :class:`~genus.tools.registry.ToolRegistry` with ``echo``, ``add``,
        and ``summarize`` registered.
    """
    registry = ToolRegistry()
    registry.register(ToolSpec(name="echo", handler=echo, description="Echo message back"))
    registry.register(ToolSpec(name="add", handler=add, description="Add two integers"))
    registry.register(
        ToolSpec(name="summarize", handler=summarize, description="Summarize text")
    )
    return registry


async def _handle_tool_call(
    bus: MessageBus, registry: ToolRegistry, message: Message
) -> None:
    """Process a single ``tool.call.requested`` message.

    Looks up *tool_name* in *registry*.  If not found, publishes a
    ``tool.call.failed`` response.  On success, publishes
    ``tool.call.succeeded``; on any execution error, publishes
    ``tool.call.failed``.

    Args:
        bus:      The message bus for publishing responses.
        registry: The tool registry to look up tools.
        message:  The incoming ``tool.call.requested`` message.
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
        response = tool_call_failed_message(run_id, AGENT_ID, step_id, tool_name, error)
        logger.warning("Tool %r not found in registry", tool_name)
        await bus.publish(response)
        return

    # Execute the tool handler
    try:
        handler = spec.handler
        if inspect.iscoroutinefunction(handler):
            result = await handler(**tool_args)
        else:
            result = handler(**tool_args)

        response = tool_call_succeeded_message(run_id, AGENT_ID, step_id, tool_name, result)
        logger.info("Tool %r succeeded: result=%r", tool_name, result)
    except TypeError as exc:
        error = "invalid arguments: {}".format(str(exc))
        response = tool_call_failed_message(run_id, AGENT_ID, step_id, tool_name, error)
        logger.warning("Tool %r failed with invalid arguments: %s", tool_name, error)
    except Exception as exc:
        error = str(exc)
        response = tool_call_failed_message(run_id, AGENT_ID, step_id, tool_name, error)
        logger.warning("Tool %r failed: %s", tool_name, error)

    await bus.publish(response)

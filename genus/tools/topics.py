"""
Tool-Call Topic Constants

Defines the standard topic strings for GENUS tool-call delegation messages.
The Orchestrator publishes ``tool.call.requested`` and tool-executor agents
publish ``tool.call.succeeded`` or ``tool.call.failed`` in response.

Correlation key: ``(metadata["run_id"], payload["step_id"])``.
"""

TOOL_CALL_REQUESTED = "tool.call.requested"
TOOL_CALL_SUCCEEDED = "tool.call.succeeded"
TOOL_CALL_FAILED = "tool.call.failed"

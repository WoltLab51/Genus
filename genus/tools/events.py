"""
Tool-Call Message Factories

Pure factory functions that build :class:`~genus.communication.message_bus.Message`
instances for each GENUS tool-call delegation topic.

Design rules:
- ``sender_id`` and ``run_id`` are always required.
- ``run_id`` is always attached to ``metadata`` via :func:`~genus.core.run.attach_run_id`.
- ``step_id`` (UUID string) and ``tool_name`` are always included in the payload.
- Optional ``payload`` dict and optional extra ``metadata`` dict are merged safely
  (input dicts are never mutated).
- No IO, no MessageBus dependency.

Correlation key: ``(metadata["run_id"], payload["step_id"])``.
"""

from typing import Any, Dict, Optional

from genus.communication.message_bus import Message
from genus.core.run import attach_run_id
from genus.tools import topics


def _build_tool_message(
    topic: str,
    run_id: str,
    sender_id: str,
    step_id: str,
    tool_name: str,
    extra: Dict[str, Any],
    payload: Optional[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]],
) -> Message:
    """Internal helper: construct a tool-call Message."""
    merged_payload: Dict[str, Any] = dict(payload) if payload else {}
    merged_payload["step_id"] = step_id
    merged_payload["tool_name"] = tool_name
    merged_payload.update(extra)

    merged_metadata: Dict[str, Any] = dict(metadata) if metadata else {}

    base = Message(
        topic=topic,
        payload=merged_payload,
        sender_id=sender_id,
        metadata=merged_metadata,
    )
    return attach_run_id(base, run_id)


def tool_call_requested_message(
    run_id: str,
    sender_id: str,
    step_id: str,
    tool_name: str,
    tool_args: Dict[str, Any],
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``tool.call.requested`` delegation message.

    Args:
        run_id:    The current run identifier (attached to metadata).
        sender_id: The component publishing this message (e.g. "Orchestrator").
        step_id:   UUID string identifying this step (correlation key).
        tool_name: Name of the tool to invoke (e.g. ``"echo"``).
        tool_args: Keyword arguments for the tool call (copied, not mutated).
        payload:   Optional extra payload fields (not mutated).
        metadata:  Optional extra metadata fields (not mutated).

    Returns:
        A :class:`~genus.communication.message_bus.Message` ready for publishing.
    """
    extra: Dict[str, Any] = {"tool_args": dict(tool_args)}
    return _build_tool_message(
        topics.TOOL_CALL_REQUESTED,
        run_id,
        sender_id,
        step_id,
        tool_name,
        extra,
        payload,
        metadata,
    )


def tool_call_succeeded_message(
    run_id: str,
    sender_id: str,
    step_id: str,
    tool_name: str,
    result: Any,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``tool.call.succeeded`` response message.

    Args:
        run_id:    The current run identifier (attached to metadata).
        sender_id: The component publishing this message (e.g. a tool executor).
        step_id:   UUID string identifying the step (correlation key).
        tool_name: Name of the tool that was invoked.
        result:    The result value returned by the tool.
        payload:   Optional extra payload fields (not mutated).
        metadata:  Optional extra metadata fields (not mutated).

    Returns:
        A :class:`~genus.communication.message_bus.Message` ready for publishing.
    """
    extra: Dict[str, Any] = {"result": result}
    return _build_tool_message(
        topics.TOOL_CALL_SUCCEEDED,
        run_id,
        sender_id,
        step_id,
        tool_name,
        extra,
        payload,
        metadata,
    )


def tool_call_failed_message(
    run_id: str,
    sender_id: str,
    step_id: str,
    tool_name: str,
    error: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``tool.call.failed`` response message.

    Args:
        run_id:    The current run identifier (attached to metadata).
        sender_id: The component publishing this message (e.g. a tool executor).
        step_id:   UUID string identifying the step (correlation key).
        tool_name: Name of the tool that failed.
        error:     Human-readable error description.
        payload:   Optional extra payload fields (not mutated).
        metadata:  Optional extra metadata fields (not mutated).

    Returns:
        A :class:`~genus.communication.message_bus.Message` ready for publishing.
    """
    extra: Dict[str, Any] = {"error": error}
    return _build_tool_message(
        topics.TOOL_CALL_FAILED,
        run_id,
        sender_id,
        step_id,
        tool_name,
        extra,
        payload,
        metadata,
    )

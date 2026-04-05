"""
Run Lifecycle Message Factories

Pure factory functions that build :class:`~genus.communication.message_bus.Message`
instances for each GENUS run lifecycle topic.

Design rules:
- ``sender_id`` is always required.
- ``run_id`` is always attached to ``metadata`` via :func:`~genus.core.run.attach_run_id`.
- Optional ``payload`` dict and optional extra ``metadata`` dict are merged safely
  (input dicts are never mutated).
- Step events require ``step_id`` and include it in the payload.
- No IO, no MessageBus dependency.
"""

from typing import Any, Dict, Optional

from genus.communication.message_bus import Message
from genus.core.run import attach_run_id
from genus.run import topics


def _build_message(
    topic: str,
    sender_id: str,
    run_id: str,
    payload: Optional[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]],
) -> Message:
    """Internal helper: construct a Message and attach run_id to metadata."""
    merged_payload: Dict[str, Any] = dict(payload) if payload else {}
    merged_metadata: Dict[str, Any] = dict(metadata) if metadata else {}

    base = Message(
        topic=topic,
        payload=merged_payload,
        sender_id=sender_id,
        metadata=merged_metadata,
    )
    return attach_run_id(base, run_id)


def run_started_message(
    run_id: str,
    sender_id: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``run.started`` lifecycle message."""
    return _build_message(topics.RUN_STARTED, sender_id, run_id, payload, metadata)


def run_step_planned_message(
    run_id: str,
    sender_id: str,
    step_id: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``run.step.planned`` lifecycle message."""
    merged_payload: Dict[str, Any] = dict(payload) if payload else {}
    merged_payload["step_id"] = step_id
    return _build_message(topics.RUN_STEP_PLANNED, sender_id, run_id, merged_payload, metadata)


def run_step_started_message(
    run_id: str,
    sender_id: str,
    step_id: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``run.step.started`` lifecycle message."""
    merged_payload: Dict[str, Any] = dict(payload) if payload else {}
    merged_payload["step_id"] = step_id
    return _build_message(topics.RUN_STEP_STARTED, sender_id, run_id, merged_payload, metadata)


def run_step_completed_message(
    run_id: str,
    sender_id: str,
    step_id: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``run.step.completed`` lifecycle message."""
    merged_payload: Dict[str, Any] = dict(payload) if payload else {}
    merged_payload["step_id"] = step_id
    return _build_message(topics.RUN_STEP_COMPLETED, sender_id, run_id, merged_payload, metadata)


def run_step_failed_message(
    run_id: str,
    sender_id: str,
    step_id: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``run.step.failed`` lifecycle message."""
    merged_payload: Dict[str, Any] = dict(payload) if payload else {}
    merged_payload["step_id"] = step_id
    return _build_message(topics.RUN_STEP_FAILED, sender_id, run_id, merged_payload, metadata)


def run_completed_message(
    run_id: str,
    sender_id: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``run.completed`` lifecycle message."""
    return _build_message(topics.RUN_COMPLETED, sender_id, run_id, payload, metadata)


def run_failed_message(
    run_id: str,
    sender_id: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``run.failed`` lifecycle message."""
    return _build_message(topics.RUN_FAILED, sender_id, run_id, payload, metadata)

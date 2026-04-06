"""
Meta Event Factories

Pure factory functions that build :class:`~genus.communication.message_bus.Message`
instances for meta-layer topics.

Design rules:
- ``sender_id`` and ``run_id`` are always required.
- ``run_id`` is always attached to ``metadata`` via :func:`~genus.core.run.attach_run_id`.
- Payload values must be JSON-compatible (dict/list/str/int/bool/None).
- No IO, no MessageBus dependency.
"""

from typing import Any, Dict, Optional

from genus.communication.message_bus import Message
from genus.core.run import attach_run_id
from genus.meta import topics


def meta_evaluation_completed_message(
    run_id: str,
    sender_id: str,
    score: int,
    failure_class: Optional[str] = None,
    *,
    summary: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``meta.evaluation.completed`` message.

    Args:
        run_id: The current run identifier (attached to metadata).
        sender_id: The component publishing this message.
        score: Evaluation score (0-100).
        failure_class: Optional failure classification.
        summary: Optional human-readable summary of evaluation.
        payload: Optional extra payload fields (not mutated).
        metadata: Optional extra metadata fields (not mutated).

    Returns:
        A Message instance for the meta.evaluation.completed topic.
    """
    merged_payload = dict(payload) if payload else {}
    merged_payload.update({
        "score": score,
        "failure_class": failure_class,
        "summary": summary or "",
    })

    merged_metadata = dict(metadata) if metadata else {}

    base = Message(
        topic=topics.META_EVALUATION_COMPLETED,
        payload=merged_payload,
        sender_id=sender_id,
        metadata=merged_metadata,
    )
    return attach_run_id(base, run_id)

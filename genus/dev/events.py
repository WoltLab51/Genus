"""
DevLoop Message Factories

Pure factory functions that build :class:`~genus.communication.message_bus.Message`
instances for each GENUS dev-loop phase topic.

Design rules:
- ``sender_id`` and ``run_id`` are always required.
- ``run_id`` is always attached to ``metadata`` via :func:`~genus.core.run.attach_run_id`.
- Optional ``payload`` dict and optional extra ``metadata`` dict are merged safely
  (input dicts are never mutated).
- Payload values must be JSON-compatible (dict/list/str/int/bool/None).
- No IO, no MessageBus dependency.
"""

from typing import Any, Dict, List, Optional

from genus.communication.message_bus import Message
from genus.core.run import attach_run_id
from genus.dev import topics


def _build_dev_message(
    topic: str,
    run_id: str,
    sender_id: str,
    extra: Dict[str, Any],
    payload: Optional[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]],
) -> Message:
    """Internal helper: construct a dev-loop Message and attach run_id."""
    merged_payload: Dict[str, Any] = dict(payload) if payload else {}
    merged_payload.update(extra)

    merged_metadata: Dict[str, Any] = dict(metadata) if metadata else {}

    base = Message(
        topic=topic,
        payload=merged_payload,
        sender_id=sender_id,
        metadata=merged_metadata,
    )
    return attach_run_id(base, run_id)


# ---------------------------------------------------------------------------
# Dev loop lifecycle
# ---------------------------------------------------------------------------

def dev_loop_started_message(
    run_id: str,
    sender_id: str,
    goal: str,
    *,
    context: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.loop.started`` message.

    Args:
        run_id:    The current run identifier (attached to metadata).
        sender_id: The component publishing this message.
        goal:      Human-readable goal/objective for this dev loop.
        context:   Optional contextual information (e.g. repo, branch).
        payload:   Optional extra payload fields (not mutated).
        metadata:  Optional extra metadata fields (not mutated).
    """
    extra: Dict[str, Any] = {"goal": goal, "context": context or {}}
    return _build_dev_message(topics.DEV_LOOP_STARTED, run_id, sender_id, extra, payload, metadata)


def dev_loop_completed_message(
    run_id: str,
    sender_id: str,
    *,
    summary: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.loop.completed`` message."""
    extra: Dict[str, Any] = {"summary": summary or ""}
    return _build_dev_message(topics.DEV_LOOP_COMPLETED, run_id, sender_id, extra, payload, metadata)


def dev_loop_failed_message(
    run_id: str,
    sender_id: str,
    error: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.loop.failed`` message."""
    extra: Dict[str, Any] = {"error": error}
    return _build_dev_message(topics.DEV_LOOP_FAILED, run_id, sender_id, extra, payload, metadata)


# ---------------------------------------------------------------------------
# Planning phase
# ---------------------------------------------------------------------------

def dev_plan_requested_message(
    run_id: str,
    sender_id: str,
    *,
    requirements: Optional[List[str]] = None,
    constraints: Optional[List[str]] = None,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.plan.requested`` message."""
    extra: Dict[str, Any] = {
        "requirements": requirements or [],
        "constraints": constraints or [],
    }
    return _build_dev_message(topics.DEV_PLAN_REQUESTED, run_id, sender_id, extra, payload, metadata)


def dev_plan_completed_message(
    run_id: str,
    sender_id: str,
    plan: Dict[str, Any],
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.plan.completed`` message.

    Args:
        plan: A JSON-compatible dict describing the plan artifact.
              Recommended shape: see :class:`~genus.dev.schemas.PlanArtifact`.
    """
    extra: Dict[str, Any] = {"plan": plan}
    return _build_dev_message(topics.DEV_PLAN_COMPLETED, run_id, sender_id, extra, payload, metadata)


def dev_plan_failed_message(
    run_id: str,
    sender_id: str,
    error: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.plan.failed`` message."""
    extra: Dict[str, Any] = {"error": error}
    return _build_dev_message(topics.DEV_PLAN_FAILED, run_id, sender_id, extra, payload, metadata)


# ---------------------------------------------------------------------------
# Implementation phase
# ---------------------------------------------------------------------------

def dev_implement_requested_message(
    run_id: str,
    sender_id: str,
    plan: Dict[str, Any],
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.implement.requested`` message."""
    extra: Dict[str, Any] = {"plan": plan}
    return _build_dev_message(topics.DEV_IMPLEMENT_REQUESTED, run_id, sender_id, extra, payload, metadata)


def dev_implement_completed_message(
    run_id: str,
    sender_id: str,
    patch_summary: str,
    files_changed: List[str],
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.implement.completed`` message."""
    extra: Dict[str, Any] = {
        "patch_summary": patch_summary,
        "files_changed": list(files_changed),
    }
    return _build_dev_message(topics.DEV_IMPLEMENT_COMPLETED, run_id, sender_id, extra, payload, metadata)


def dev_implement_failed_message(
    run_id: str,
    sender_id: str,
    error: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.implement.failed`` message."""
    extra: Dict[str, Any] = {"error": error}
    return _build_dev_message(topics.DEV_IMPLEMENT_FAILED, run_id, sender_id, extra, payload, metadata)


# ---------------------------------------------------------------------------
# Testing phase
# ---------------------------------------------------------------------------

def dev_test_requested_message(
    run_id: str,
    sender_id: str,
    *,
    test_command: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.test.requested`` message."""
    extra: Dict[str, Any] = {"test_command": test_command or ""}
    return _build_dev_message(topics.DEV_TEST_REQUESTED, run_id, sender_id, extra, payload, metadata)


def dev_test_completed_message(
    run_id: str,
    sender_id: str,
    report: Dict[str, Any],
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.test.completed`` message.

    Args:
        report: A JSON-compatible dict describing the test report.
                Recommended shape: see :class:`~genus.dev.schemas.TestReportArtifact`.
    """
    extra: Dict[str, Any] = {"report": report}
    return _build_dev_message(topics.DEV_TEST_COMPLETED, run_id, sender_id, extra, payload, metadata)


def dev_test_failed_message(
    run_id: str,
    sender_id: str,
    error: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.test.failed`` message."""
    extra: Dict[str, Any] = {"error": error}
    return _build_dev_message(topics.DEV_TEST_FAILED, run_id, sender_id, extra, payload, metadata)


# ---------------------------------------------------------------------------
# Review phase
# ---------------------------------------------------------------------------

def dev_review_requested_message(
    run_id: str,
    sender_id: str,
    *,
    patch_summary: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.review.requested`` message."""
    extra: Dict[str, Any] = {"patch_summary": patch_summary or ""}
    return _build_dev_message(topics.DEV_REVIEW_REQUESTED, run_id, sender_id, extra, payload, metadata)


def dev_review_completed_message(
    run_id: str,
    sender_id: str,
    review: Dict[str, Any],
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.review.completed`` message.

    Args:
        review: A JSON-compatible dict describing the review artifact.
                Recommended shape: see :class:`~genus.dev.schemas.ReviewArtifact`.
    """
    extra: Dict[str, Any] = {"review": review}
    return _build_dev_message(topics.DEV_REVIEW_COMPLETED, run_id, sender_id, extra, payload, metadata)


def dev_review_failed_message(
    run_id: str,
    sender_id: str,
    error: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.review.failed`` message."""
    extra: Dict[str, Any] = {"error": error}
    return _build_dev_message(topics.DEV_REVIEW_FAILED, run_id, sender_id, extra, payload, metadata)


# ---------------------------------------------------------------------------
# Fix phase
# ---------------------------------------------------------------------------

def dev_fix_requested_message(
    run_id: str,
    sender_id: str,
    findings: List[Dict[str, Any]],
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.fix.requested`` message."""
    extra: Dict[str, Any] = {"findings": list(findings)}
    return _build_dev_message(topics.DEV_FIX_REQUESTED, run_id, sender_id, extra, payload, metadata)


def dev_fix_completed_message(
    run_id: str,
    sender_id: str,
    fix: Dict[str, Any],
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.fix.completed`` message.

    Args:
        fix: A JSON-compatible dict describing the fix artifact.
             Recommended shape: see :class:`~genus.dev.schemas.FixArtifact`.
    """
    extra: Dict[str, Any] = {"fix": fix}
    return _build_dev_message(topics.DEV_FIX_COMPLETED, run_id, sender_id, extra, payload, metadata)


def dev_fix_failed_message(
    run_id: str,
    sender_id: str,
    error: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Message:
    """Build a ``dev.fix.failed`` message."""
    extra: Dict[str, Any] = {"error": error}
    return _build_dev_message(topics.DEV_FIX_FAILED, run_id, sender_id, extra, payload, metadata)

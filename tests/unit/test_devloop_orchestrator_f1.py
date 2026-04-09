"""Tests for F1 Orchestrator improvements.

Tests per-phase timeouts, test_report artifact persistence,
plan validation, and episodic context injection.
"""
import copy
import pytest
from unittest.mock import MagicMock

from genus.communication.message_bus import MessageBus
from genus.dev.devloop_orchestrator import DevLoopOrchestrator
from genus.dev import topics
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_store_and_journal(tmp_path, run_id="test-run-001"):
    store = JsonlRunStore(base_dir=str(tmp_path / "runs"))
    journal = RunJournal(run_id, store)
    journal.initialize(goal="Test goal", repo_id="owner/repo")
    return store, journal


def make_orchestrator(bus, journal, **kwargs):
    return DevLoopOrchestrator(
        bus=bus,
        run_journal=journal,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Fix 1: Per-Phase Timeouts
# ---------------------------------------------------------------------------

def test_per_phase_timeout_defaults_to_timeout_s(tmp_path):
    """When no per-phase timeouts given, all phases use timeout_s."""
    bus = MagicMock(spec=MessageBus)
    _, journal = make_store_and_journal(tmp_path)
    orch = make_orchestrator(bus, journal, timeout_s=42.0)
    assert orch._plan_timeout_s == 42.0
    assert orch._implement_timeout_s == 42.0
    assert orch._test_timeout_s == 42.0
    assert orch._fix_timeout_s == 42.0
    assert orch._review_timeout_s == 42.0


def test_per_phase_timeout_override(tmp_path):
    """Per-phase timeouts override the default timeout_s."""
    bus = MagicMock(spec=MessageBus)
    _, journal = make_store_and_journal(tmp_path)
    orch = make_orchestrator(
        bus, journal,
        timeout_s=30.0,
        plan_timeout_s=10.0,
        implement_timeout_s=120.0,
        test_timeout_s=90.0,
        fix_timeout_s=60.0,
        review_timeout_s=20.0,
    )
    assert orch._plan_timeout_s == 10.0
    assert orch._implement_timeout_s == 120.0
    assert orch._test_timeout_s == 90.0
    assert orch._fix_timeout_s == 60.0
    assert orch._review_timeout_s == 20.0


def test_partial_per_phase_timeout_override(tmp_path):
    """Only overridden phases use custom timeouts; others fall back to timeout_s."""
    bus = MagicMock(spec=MessageBus)
    _, journal = make_store_and_journal(tmp_path)
    orch = make_orchestrator(
        bus, journal,
        timeout_s=30.0,
        implement_timeout_s=120.0,
    )
    assert orch._plan_timeout_s == 30.0       # fallback
    assert orch._implement_timeout_s == 120.0  # overridden
    assert orch._test_timeout_s == 30.0       # fallback
    assert orch._fix_timeout_s == 30.0        # fallback
    assert orch._review_timeout_s == 30.0     # fallback


# ---------------------------------------------------------------------------
# Fix 2: test_report Artifact
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_test_report_artifact_saved_on_pass(tmp_path):
    """test_report artifact is saved when tests pass."""
    store, journal = make_store_and_journal(tmp_path)
    bus = MessageBus()
    orch = make_orchestrator(bus, journal, timeout_s=5.0)

    async def fake_plan_agent(msg):
        from genus.dev.events import dev_plan_completed_message
        resp = dev_plan_completed_message(
            "test-run-001", "planner",
            {"steps": ["do something"]},
            phase_id=msg.payload["phase_id"],
        )
        resp_copy = copy.copy(resp)
        resp_copy.metadata = dict(resp.metadata)
        await bus.publish(resp_copy)

    async def fake_implement_agent(msg):
        from genus.dev.events import dev_implement_completed_message
        resp = dev_implement_completed_message(
            "test-run-001", "builder",
            patch_summary="did it",
            files_changed=["foo.py"],
            phase_id=msg.payload["phase_id"],
        )
        resp_copy = copy.copy(resp)
        resp_copy.metadata = dict(resp.metadata)
        await bus.publish(resp_copy)

    async def fake_test_agent(msg):
        from genus.dev.events import dev_test_completed_message
        resp = dev_test_completed_message(
            "test-run-001", "tester",
            {"failed": 0, "failing_tests": [], "summary": "All passed"},
            phase_id=msg.payload["phase_id"],
        )
        resp_copy = copy.copy(resp)
        resp_copy.metadata = dict(resp.metadata)
        await bus.publish(resp_copy)

    async def fake_review_agent(msg):
        from genus.dev.events import dev_review_completed_message
        resp = dev_review_completed_message(
            "test-run-001", "reviewer",
            {"findings": [], "approved": True},
            phase_id=msg.payload["phase_id"],
        )
        resp_copy = copy.copy(resp)
        resp_copy.metadata = dict(resp.metadata)
        await bus.publish(resp_copy)

    bus.subscribe(topics.DEV_PLAN_REQUESTED, "fake-planner", fake_plan_agent)
    bus.subscribe(topics.DEV_IMPLEMENT_REQUESTED, "fake-builder", fake_implement_agent)
    bus.subscribe(topics.DEV_TEST_REQUESTED, "fake-tester", fake_test_agent)
    bus.subscribe(topics.DEV_REVIEW_REQUESTED, "fake-reviewer", fake_review_agent)

    await orch.run("test-run-001", goal="Test goal")

    # test_report artifact must exist
    artifacts = journal.get_artifacts(artifact_type="test_report", phase="test")
    assert len(artifacts) >= 1
    assert artifacts[0].payload.get("summary") == "All passed"


# ---------------------------------------------------------------------------
# Fix 4: Plan validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_plan_triggers_loop_failed(tmp_path):
    """An empty plan payload causes dev.loop.failed to be published."""
    store, journal = make_store_and_journal(tmp_path)
    bus = MessageBus()
    orch = make_orchestrator(bus, journal, timeout_s=5.0)

    failed_messages = []

    async def capture_failed(msg):
        failed_messages.append(msg)

    bus.subscribe(topics.DEV_LOOP_FAILED, "capture", capture_failed)

    async def fake_plan_agent_empty(msg):
        from genus.dev.events import dev_plan_completed_message
        # Return empty plan
        resp = dev_plan_completed_message(
            "test-run-001", "planner",
            {},  # empty plan
            phase_id=msg.payload["phase_id"],
        )
        resp_copy = copy.copy(resp)
        resp_copy.metadata = dict(resp.metadata)
        await bus.publish(resp_copy)

    bus.subscribe(topics.DEV_PLAN_REQUESTED, "fake-planner", fake_plan_agent_empty)

    await orch.run("test-run-001", goal="Test empty plan")

    assert len(failed_messages) == 1
    assert "empty plan" in failed_messages[0].payload.get("error", "").lower()


# ---------------------------------------------------------------------------
# Fix 1 integration: phase-specific timeout is used
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_timeout_is_used_not_default(tmp_path):
    """plan_timeout_s is used for the plan phase, not timeout_s."""
    store, journal = make_store_and_journal(tmp_path)
    bus = MessageBus()
    # Very short plan timeout, longer default
    orch = make_orchestrator(bus, journal, timeout_s=60.0, plan_timeout_s=0.01)

    # No plan agent subscribed — will time out
    from genus.dev.runtime import DevResponseTimeoutError
    with pytest.raises(DevResponseTimeoutError) as exc_info:
        await orch.run("test-run-001", goal="Test timeout")

    assert exc_info.value.timeout_s == 0.01

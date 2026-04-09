"""Tests for individual PhaseRunners."""
import dataclasses
import copy
import pytest

from genus.communication.message_bus import MessageBus
from genus.dev import topics
from genus.dev.run_context import PhaseTimeouts, RunContext
from genus.dev.phase_runners import (
    PlanPhaseRunner,
    ImplPhaseRunner,
    TestPhaseRunner,
    FixPhaseRunner,
    ReviewPhaseRunner,
)
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pub(resp, bus):
    """Helper: copy message and publish with metadata dict."""
    r = copy.copy(resp)
    r.metadata = dict(resp.metadata)
    return bus.publish(r)


@pytest.fixture
def ctx(tmp_path):
    store = JsonlRunStore(base_dir=str(tmp_path / "runs"))
    journal = RunJournal("run-001", store)
    journal.initialize(goal="Test goal", repo_id="owner/repo")
    bus = MessageBus()
    return RunContext(
        run_id="run-001",
        goal="Test goal",
        bus=bus,
        journal=journal,
        sender_id="test-orchestrator",
        timeouts=PhaseTimeouts(plan=5.0, implement=5.0, test=5.0, fix=5.0, review=5.0),
    )


# ---------------------------------------------------------------------------
# PlanPhaseRunner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_runner_returns_plan(ctx):
    async def fake_planner(msg):
        from genus.dev.events import dev_plan_completed_message
        resp = dev_plan_completed_message(
            "run-001", "planner",
            {"steps": ["step1"]},
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx.bus)

    ctx.bus.subscribe(topics.DEV_PLAN_REQUESTED, "planner", fake_planner)
    plan = await PlanPhaseRunner().run(ctx)
    assert plan == {"steps": ["step1"]}


@pytest.mark.asyncio
async def test_plan_runner_saves_artifact(ctx):
    async def fake_planner(msg):
        from genus.dev.events import dev_plan_completed_message
        resp = dev_plan_completed_message(
            "run-001", "planner", {"steps": ["s1"]},
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx.bus)

    ctx.bus.subscribe(topics.DEV_PLAN_REQUESTED, "planner", fake_planner)
    await PlanPhaseRunner().run(ctx)

    artifacts = ctx.journal.get_artifacts(artifact_type="plan", phase="plan")
    assert len(artifacts) == 1
    assert artifacts[0].payload == {"steps": ["s1"]}


@pytest.mark.asyncio
async def test_plan_runner_raises_on_empty_plan(ctx):
    async def fake_planner_empty(msg):
        from genus.dev.events import dev_plan_completed_message
        resp = dev_plan_completed_message(
            "run-001", "planner", {},
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx.bus)

    ctx.bus.subscribe(topics.DEV_PLAN_REQUESTED, "planner", fake_planner_empty)
    with pytest.raises(ValueError, match="empty plan"):
        await PlanPhaseRunner().run(ctx)


@pytest.mark.asyncio
async def test_plan_runner_injects_episodic_context(ctx):
    """Episodic context is passed in the plan request payload."""
    ep = [{"run_id": "old-run", "goal": "old goal"}]
    ctx2 = dataclasses.replace(ctx, episodic_context=ep)

    received_payloads = []

    async def fake_planner(msg):
        received_payloads.append(dict(msg.payload))
        from genus.dev.events import dev_plan_completed_message
        resp = dev_plan_completed_message(
            "run-001", "planner", {"steps": ["x"]},
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx2.bus)

    ctx2.bus.subscribe(topics.DEV_PLAN_REQUESTED, "planner", fake_planner)
    await PlanPhaseRunner().run(ctx2)

    assert received_payloads[0].get("episodic_context") == ep


@pytest.mark.asyncio
async def test_plan_runner_timeout(ctx):
    from genus.dev.runtime import DevResponseTimeoutError
    ctx_short = dataclasses.replace(ctx, timeouts=PhaseTimeouts(plan=0.01))
    with pytest.raises(DevResponseTimeoutError):
        await PlanPhaseRunner().run(ctx_short)


# ---------------------------------------------------------------------------
# ImplPhaseRunner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_impl_runner_returns_payload(ctx):
    async def fake_builder(msg):
        from genus.dev.events import dev_implement_completed_message
        resp = dev_implement_completed_message(
            "run-001", "builder",
            patch_summary="done", files_changed=["foo.py"],
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx.bus)

    ctx.bus.subscribe(topics.DEV_IMPLEMENT_REQUESTED, "builder", fake_builder)
    result = await ImplPhaseRunner().run(ctx, plan={"steps": ["x"]})
    assert result["patch_summary"] == "done"


# ---------------------------------------------------------------------------
# TestPhaseRunner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_test_runner_tests_passed(ctx):
    async def fake_tester(msg):
        from genus.dev.events import dev_test_completed_message
        resp = dev_test_completed_message(
            "run-001", "tester",
            {"failed": 0, "failing_tests": [], "summary": "All green"},
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx.bus)

    ctx.bus.subscribe(topics.DEV_TEST_REQUESTED, "tester", fake_tester)
    report, passed = await TestPhaseRunner().run(ctx)
    assert passed is True
    assert report["summary"] == "All green"


@pytest.mark.asyncio
async def test_test_runner_tests_failed(ctx):
    async def fake_tester(msg):
        from genus.dev.events import dev_test_completed_message
        resp = dev_test_completed_message(
            "run-001", "tester",
            {"failed": 2, "failing_tests": ["test_foo"], "summary": "2 failed"},
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx.bus)

    ctx.bus.subscribe(topics.DEV_TEST_REQUESTED, "tester", fake_tester)
    report, passed = await TestPhaseRunner().run(ctx)
    assert passed is False
    assert report["failed"] == 2


@pytest.mark.asyncio
async def test_test_runner_saves_artifact(ctx):
    async def fake_tester(msg):
        from genus.dev.events import dev_test_completed_message
        resp = dev_test_completed_message(
            "run-001", "tester",
            {"failed": 0, "failing_tests": [], "summary": "ok"},
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx.bus)

    ctx.bus.subscribe(topics.DEV_TEST_REQUESTED, "tester", fake_tester)
    await TestPhaseRunner().run(ctx)
    artifacts = ctx.journal.get_artifacts(artifact_type="test_report", phase="test")
    assert len(artifacts) == 1


@pytest.mark.asyncio
async def test_test_runner_logs_test_failed_event(ctx):
    async def fake_tester(msg):
        from genus.dev.events import dev_test_completed_message
        resp = dev_test_completed_message(
            "run-001", "tester",
            {"failed": 1, "failing_tests": ["test_bar"], "summary": "1 failed"},
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx.bus)

    ctx.bus.subscribe(topics.DEV_TEST_REQUESTED, "tester", fake_tester)
    await TestPhaseRunner().run(ctx)
    events_list = ctx.journal.get_events(phase="test", event_type="test_failed")
    assert len(events_list) == 1


# ---------------------------------------------------------------------------
# ReviewPhaseRunner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_review_runner_returns_review(ctx):
    async def fake_reviewer(msg):
        from genus.dev.events import dev_review_completed_message
        resp = dev_review_completed_message(
            "run-001", "reviewer",
            {"findings": [], "approved": True},
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx.bus)

    ctx.bus.subscribe(topics.DEV_REVIEW_REQUESTED, "reviewer", fake_reviewer)
    review = await ReviewPhaseRunner().run(ctx)
    assert review["approved"] is True


@pytest.mark.asyncio
async def test_review_runner_saves_artifact(ctx):
    async def fake_reviewer(msg):
        from genus.dev.events import dev_review_completed_message
        resp = dev_review_completed_message(
            "run-001", "reviewer",
            {"findings": [], "approved": True},
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx.bus)

    ctx.bus.subscribe(topics.DEV_REVIEW_REQUESTED, "reviewer", fake_reviewer)
    await ReviewPhaseRunner().run(ctx)
    artifacts = ctx.journal.get_artifacts(artifact_type="review", phase="review")
    assert len(artifacts) == 1


# ---------------------------------------------------------------------------
# FixPhaseRunner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fix_runner_returns_payload(ctx):
    async def fake_fixer(msg):
        from genus.dev.events import dev_fix_completed_message
        resp = dev_fix_completed_message(
            "run-001", "fixer",
            {"patched": True},
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx.bus)

    ctx.bus.subscribe(topics.DEV_FIX_REQUESTED, "fixer", fake_fixer)
    result = await FixPhaseRunner().run(
        ctx,
        test_report={"failed": 1, "failing_tests": ["test_x"], "summary": "1 failed"},
        iteration=1,
    )
    assert result.get("fix", {}).get("patched") is True


@pytest.mark.asyncio
async def test_fix_runner_logs_fix_completed_event(ctx):
    async def fake_fixer(msg):
        from genus.dev.events import dev_fix_completed_message
        resp = dev_fix_completed_message(
            "run-001", "fixer", {},
            phase_id=msg.payload["phase_id"],
        )
        await _pub(resp, ctx.bus)

    ctx.bus.subscribe(topics.DEV_FIX_REQUESTED, "fixer", fake_fixer)
    await FixPhaseRunner().run(
        ctx,
        test_report={"failed": 1, "failing_tests": [], "summary": "failed"},
        iteration=1,
    )
    events_list = ctx.journal.get_events(phase="fix", event_type="fix_completed")
    assert len(events_list) == 1

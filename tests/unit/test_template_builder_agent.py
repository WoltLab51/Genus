"""
Unit Tests — TemplateBuilderAgent

Tests for :class:`~genus.dev.agents.template_builder_agent.TemplateBuilderAgent`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.dev.agents.template_builder_agent import TemplateBuilderAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect(bus: MessageBus, topic: str) -> List[Message]:
    captured: List[Message] = []

    async def _cb(msg: Message) -> None:
        captured.append(msg)

    bus.subscribe(topic, f"__test_collector_{topic}__", _cb)
    return captured


def _plan_requested_msg(run_id: str, phase_id: str, extra_payload: dict = None) -> Message:
    payload = {
        "phase_id": phase_id,
        "requirements": [],
        "constraints": [],
    }
    if extra_payload:
        payload.update(extra_payload)
    return Message(
        topic="dev.plan.requested",
        payload=payload,
        sender_id="DevLoopOrchestrator",
        metadata={
            "run_id": run_id,
            "domain": "family",
            "need_description": "missing_calendar_reminders",
            "agent_spec_template": {
                "name": "FamilyCalendarAgent",
                "topics": ["family.calendar.requested"],
            },
        },
    )


def _implement_requested_msg(run_id: str, phase_id: str, plan: dict) -> Message:
    return Message(
        topic="dev.implement.requested",
        payload={"phase_id": phase_id, "plan": plan},
        sender_id="DevLoopOrchestrator",
        metadata={"run_id": run_id},
    )


def _test_requested_msg(run_id: str, phase_id: str) -> Message:
    return Message(
        topic="dev.test.requested",
        payload={"phase_id": phase_id, "test_command": ""},
        sender_id="DevLoopOrchestrator",
        metadata={"run_id": run_id},
    )


def _fix_requested_msg(run_id: str, phase_id: str) -> Message:
    return Message(
        topic="dev.fix.requested",
        payload={"phase_id": phase_id, "findings": [{"type": "error", "message": "boom"}]},
        sender_id="DevLoopOrchestrator",
        metadata={"run_id": run_id},
    )


def _review_requested_msg(run_id: str, phase_id: str) -> Message:
    return Message(
        topic="dev.review.requested",
        payload={"phase_id": phase_id, "patch_summary": ""},
        sender_id="DevLoopOrchestrator",
        metadata={"run_id": run_id},
    )


async def _setup_agent(tmp_path: Path) -> tuple:
    bus = MessageBus()
    agent = TemplateBuilderAgent(
        message_bus=bus,
        output_base_path=tmp_path / "generated",
    )
    await agent.initialize()
    await agent.start()
    return bus, agent


# ---------------------------------------------------------------------------
# Plan phase tests
# ---------------------------------------------------------------------------

class TestTemplateBuilderAgentPlan:
    async def test_plan_requested_publishes_plan_completed(self, tmp_path: Path) -> None:
        bus, agent = await _setup_agent(tmp_path)
        completed: List[Message] = _collect(bus, "dev.plan.completed")

        await bus.publish(_plan_requested_msg("run-1", "phase-plan-1"))
        await asyncio.sleep(0)

        assert len(completed) == 1

    async def test_plan_completed_contains_class_name(self, tmp_path: Path) -> None:
        bus, agent = await _setup_agent(tmp_path)
        completed: List[Message] = _collect(bus, "dev.plan.completed")

        await bus.publish(_plan_requested_msg("run-2", "phase-plan-2"))
        await asyncio.sleep(0)

        plan = completed[0].payload.get("plan", {})
        assert plan.get("class_name") == "FamilyCalendarAgent"

    async def test_plan_completed_contains_domain(self, tmp_path: Path) -> None:
        bus, agent = await _setup_agent(tmp_path)
        completed: List[Message] = _collect(bus, "dev.plan.completed")

        await bus.publish(_plan_requested_msg("run-3", "phase-plan-3"))
        await asyncio.sleep(0)

        plan = completed[0].payload.get("plan", {})
        assert plan.get("domain") == "family"

    async def test_plan_completed_template_based_true(self, tmp_path: Path) -> None:
        bus, agent = await _setup_agent(tmp_path)
        completed: List[Message] = _collect(bus, "dev.plan.completed")

        await bus.publish(_plan_requested_msg("run-4", "phase-plan-4"))
        await asyncio.sleep(0)

        plan = completed[0].payload.get("plan", {})
        assert plan.get("template_based") is True

    async def test_plan_stores_run_state(self, tmp_path: Path) -> None:
        bus, agent = await _setup_agent(tmp_path)

        await bus.publish(_plan_requested_msg("run-5", "phase-plan-5"))
        await asyncio.sleep(0)

        assert "run-5" in agent._run_state
        assert agent._run_state["run-5"]["class_name"] == "FamilyCalendarAgent"


# ---------------------------------------------------------------------------
# Implement phase tests
# ---------------------------------------------------------------------------

class TestTemplateBuilderAgentImplement:
    async def _run_plan_and_get(self, tmp_path: Path):
        """Run plan phase and return bus, agent, and the plan dict."""
        bus, agent = await _setup_agent(tmp_path)
        completed: List[Message] = _collect(bus, "dev.plan.completed")

        await bus.publish(_plan_requested_msg("run-impl-1", "phase-plan-impl-1"))
        await asyncio.sleep(0)

        plan = completed[0].payload["plan"]
        return bus, agent, plan

    async def test_implement_requested_publishes_implement_completed(self, tmp_path: Path) -> None:
        bus, agent, plan = await self._run_plan_and_get(tmp_path)
        impl_completed: List[Message] = _collect(bus, "dev.implement.completed")

        await bus.publish(_implement_requested_msg("run-impl-1", "phase-impl-1", plan))
        await asyncio.sleep(0)

        assert len(impl_completed) == 1

    async def test_implement_writes_file_to_disk(self, tmp_path: Path) -> None:
        bus, agent, plan = await self._run_plan_and_get(tmp_path)

        await bus.publish(_implement_requested_msg("run-impl-1", "phase-impl-2", plan))
        await asyncio.sleep(0)

        generated_dir = tmp_path / "generated"
        files = list(generated_dir.glob("*.py"))
        py_files = [f for f in files if f.name != "__init__.py"]
        assert len(py_files) == 1, f"Expected 1 generated .py file, got: {[f.name for f in py_files]}"

    async def test_generated_file_exists(self, tmp_path: Path) -> None:
        bus, agent, plan = await self._run_plan_and_get(tmp_path)

        await bus.publish(_implement_requested_msg("run-impl-1", "phase-impl-3", plan))
        await asyncio.sleep(0)

        expected_file = tmp_path / "generated" / "family_calendar_agent.py"
        assert expected_file.exists(), f"Expected {expected_file} to exist"

    async def test_generated_file_contains_class_name(self, tmp_path: Path) -> None:
        bus, agent, plan = await self._run_plan_and_get(tmp_path)

        await bus.publish(_implement_requested_msg("run-impl-1", "phase-impl-4", plan))
        await asyncio.sleep(0)

        expected_file = tmp_path / "generated" / "family_calendar_agent.py"
        content = expected_file.read_text(encoding="utf-8")
        assert "FamilyCalendarAgent" in content

    async def test_implement_updates_run_state(self, tmp_path: Path) -> None:
        bus, agent, plan = await self._run_plan_and_get(tmp_path)

        await bus.publish(_implement_requested_msg("run-impl-1", "phase-impl-5", plan))
        await asyncio.sleep(0)

        run_info = agent._run_state.get("run-impl-1", {})
        assert run_info.get("generated_file") is not None


# ---------------------------------------------------------------------------
# Test phase tests
# ---------------------------------------------------------------------------

class TestTemplateBuilderAgentTest:
    async def _run_plan_and_implement(self, tmp_path: Path, run_id: str):
        bus, agent = await _setup_agent(tmp_path)
        plan_completed: List[Message] = _collect(bus, "dev.plan.completed")

        await bus.publish(_plan_requested_msg(run_id, f"phase-plan-{run_id}"))
        await asyncio.sleep(0)

        plan = plan_completed[0].payload["plan"]
        await bus.publish(_implement_requested_msg(run_id, f"phase-impl-{run_id}", plan))
        await asyncio.sleep(0)

        return bus, agent

    async def test_test_after_implement_passes(self, tmp_path: Path) -> None:
        bus, agent = await self._run_plan_and_implement(tmp_path, "run-test-1")
        test_completed: List[Message] = _collect(bus, "dev.test.completed")

        await bus.publish(_test_requested_msg("run-test-1", "phase-test-1"))
        await asyncio.sleep(0)

        assert len(test_completed) == 1
        report = test_completed[0].payload.get("report", {})
        assert report.get("failed") == 0

    async def test_test_when_file_missing_fails(self, tmp_path: Path) -> None:
        bus, agent = await _setup_agent(tmp_path)
        test_completed: List[Message] = _collect(bus, "dev.test.completed")

        # Don't run plan/implement — file won't exist
        await bus.publish(_test_requested_msg("run-test-missing", "phase-test-m"))
        await asyncio.sleep(0)

        assert len(test_completed) == 1
        report = test_completed[0].payload.get("report", {})
        assert report.get("failed") == 1
        assert "import_check" in report.get("failing_tests", [])

    async def test_test_report_contains_template_based(self, tmp_path: Path) -> None:
        bus, agent = await _setup_agent(tmp_path)
        test_completed: List[Message] = _collect(bus, "dev.test.completed")

        await bus.publish(_test_requested_msg("run-test-tb", "phase-test-tb"))
        await asyncio.sleep(0)

        report = test_completed[0].payload.get("report", {})
        assert report.get("template_based") is True


# ---------------------------------------------------------------------------
# Fix phase tests
# ---------------------------------------------------------------------------

class TestTemplateBuilderAgentFix:
    async def test_fix_always_responds(self, tmp_path: Path) -> None:
        bus, agent = await _setup_agent(tmp_path)
        fix_completed: List[Message] = _collect(bus, "dev.fix.completed")

        await bus.publish(_fix_requested_msg("run-fix-1", "phase-fix-1"))
        await asyncio.sleep(0)

        assert len(fix_completed) == 1

    async def test_fix_response_is_template_based(self, tmp_path: Path) -> None:
        bus, agent = await _setup_agent(tmp_path)
        fix_completed: List[Message] = _collect(bus, "dev.fix.completed")

        await bus.publish(_fix_requested_msg("run-fix-2", "phase-fix-2"))
        await asyncio.sleep(0)

        fix = fix_completed[0].payload.get("fix", {})
        assert fix.get("template_based") is True
        assert fix.get("action") == "template_fix_not_supported"


# ---------------------------------------------------------------------------
# Review phase tests
# ---------------------------------------------------------------------------

class TestTemplateBuilderAgentReview:
    async def test_review_approved_when_file_exists(self, tmp_path: Path) -> None:
        bus, agent = await _setup_agent(tmp_path)
        plan_completed: List[Message] = _collect(bus, "dev.plan.completed")
        review_completed: List[Message] = _collect(bus, "dev.review.completed")

        run_id = "run-review-1"
        await bus.publish(_plan_requested_msg(run_id, "phase-plan-r1"))
        await asyncio.sleep(0)
        plan = plan_completed[0].payload["plan"]

        await bus.publish(_implement_requested_msg(run_id, "phase-impl-r1", plan))
        await asyncio.sleep(0)

        await bus.publish(_review_requested_msg(run_id, "phase-review-r1"))
        await asyncio.sleep(0)

        assert len(review_completed) == 1
        review = review_completed[0].payload.get("review", {})
        assert review.get("approved") is True
        assert review.get("findings") == []

    async def test_review_not_approved_when_file_missing(self, tmp_path: Path) -> None:
        bus, agent = await _setup_agent(tmp_path)
        review_completed: List[Message] = _collect(bus, "dev.review.completed")

        await bus.publish(_review_requested_msg("run-review-missing", "phase-review-m"))
        await asyncio.sleep(0)

        assert len(review_completed) == 1
        review = review_completed[0].payload.get("review", {})
        assert review.get("approved") is False
        assert review.get("findings") == []

    async def test_review_findings_always_empty(self, tmp_path: Path) -> None:
        """findings is always empty so Ask/Stop is never triggered."""
        bus, agent = await _setup_agent(tmp_path)
        review_completed: List[Message] = _collect(bus, "dev.review.completed")

        await bus.publish(_review_requested_msg("run-review-empty", "phase-review-e"))
        await asyncio.sleep(0)

        review = review_completed[0].payload.get("review", {})
        assert review.get("findings") == []


# ---------------------------------------------------------------------------
# Run state tests
# ---------------------------------------------------------------------------

class TestTemplateBuilderAgentRunState:
    async def test_run_state_per_run_id(self, tmp_path: Path) -> None:
        bus, agent = await _setup_agent(tmp_path)
        plan_completed: List[Message] = _collect(bus, "dev.plan.completed")

        await bus.publish(_plan_requested_msg("run-state-A", "phase-plan-A"))
        await bus.publish(_plan_requested_msg("run-state-B", "phase-plan-B"))
        await asyncio.sleep(0)

        assert "run-state-A" in agent._run_state
        assert "run-state-B" in agent._run_state
        assert agent._run_state["run-state-A"]["class_name"] == "FamilyCalendarAgent"
        assert agent._run_state["run-state-B"]["class_name"] == "FamilyCalendarAgent"

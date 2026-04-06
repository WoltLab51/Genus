"""
Tests for DevLoopOrchestrator + StrategySelector integration.

Validates that:
- StrategySelector.select_strategy() is called before each fix iteration
- The fix-request payload contains 'strategy' and 'strategy_reason' fields
- Without a strategy_selector the orchestrator behaves as before (backwards-compat)
- _derive_recommendations() derives the correct hints from a test report
"""

import asyncio
import tempfile
from unittest.mock import MagicMock

import pytest

from genus.communication.message_bus import MessageBus, Message
from genus.dev import topics
from genus.dev.devloop_orchestrator import DevLoopOrchestrator, _derive_recommendations
from genus.dev.events import (
    dev_plan_completed_message,
    dev_implement_completed_message,
    dev_test_completed_message,
    dev_fix_completed_message,
    dev_review_completed_message,
)
from genus.strategy.models import PlaybookId, StrategyDecision, StrategyProfile
from genus.strategy.selector import StrategySelector
from genus.strategy.store_json import StrategyStoreJson


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = "2026-04-06T10-00-00Z__strattest__abc123"


def _make_fake_decision(playbook: str = PlaybookId.TARGET_FAILING_TEST_FIRST) -> StrategyDecision:
    from datetime import datetime, timezone
    return StrategyDecision(
        run_id=RUN_ID,
        phase="fix",
        iteration=1,
        selected_playbook=playbook,
        candidates=PlaybookId.all_values(),
        reason=f"Selected '{playbook}' (score: 30).",
        derived_from={"failure_class": "test_failure"},
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class FakeResponder:
    """Responds automatically to dev-loop phases for testing."""

    def __init__(self, bus: MessageBus, run_id: str, fail_first_test: bool = False):
        self.bus = bus
        self.run_id = run_id
        self.fail_first_test = fail_first_test
        self._test_call_count = 0
        self.fix_payloads: list = []

    def start(self):
        self.bus.subscribe(topics.DEV_PLAN_REQUESTED, "responder", self._handle_plan)
        self.bus.subscribe(topics.DEV_IMPLEMENT_REQUESTED, "responder", self._handle_implement)
        self.bus.subscribe(topics.DEV_TEST_REQUESTED, "responder", self._handle_test)
        self.bus.subscribe(topics.DEV_FIX_REQUESTED, "responder", self._handle_fix)
        self.bus.subscribe(topics.DEV_REVIEW_REQUESTED, "responder", self._handle_review)

    async def _handle_plan(self, msg: Message):
        if msg.metadata.get("run_id") != self.run_id:
            return
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return
        asyncio.create_task(self._respond_plan(phase_id))

    async def _respond_plan(self, phase_id: str):
        await asyncio.sleep(0.01)
        await self.bus.publish(
            dev_plan_completed_message(
                self.run_id, "responder",
                {"steps": [], "risks": []},
                phase_id=phase_id,
            )
        )

    async def _handle_implement(self, msg: Message):
        if msg.metadata.get("run_id") != self.run_id:
            return
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return
        asyncio.create_task(self._respond_implement(phase_id))

    async def _respond_implement(self, phase_id: str):
        await asyncio.sleep(0.01)
        await self.bus.publish(
            dev_implement_completed_message(
                self.run_id, "responder",
                "ok", [],
                phase_id=phase_id,
            )
        )

    async def _handle_test(self, msg: Message):
        if msg.metadata.get("run_id") != self.run_id:
            return
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return
        self._test_call_count += 1
        asyncio.create_task(self._respond_test(phase_id))

    async def _respond_test(self, phase_id: str):
        await asyncio.sleep(0.01)
        if self.fail_first_test and self._test_call_count == 1:
            report = {
                "passed": 0, "failed": 1,
                "summary": "1 test failed",
                "failing_tests": ["test_foo"],
                "failure_class": "test_failure",
            }
        else:
            report = {
                "passed": 5, "failed": 0,
                "summary": "All tests passed",
                "failing_tests": [],
            }
        await self.bus.publish(
            dev_test_completed_message(
                self.run_id, "responder", report, phase_id=phase_id,
            )
        )

    async def _handle_fix(self, msg: Message):
        if msg.metadata.get("run_id") != self.run_id:
            return
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return
        self.fix_payloads.append(dict(msg.payload))
        asyncio.create_task(self._respond_fix(phase_id))

    async def _respond_fix(self, phase_id: str):
        await asyncio.sleep(0.01)
        await self.bus.publish(
            dev_fix_completed_message(
                self.run_id, "responder",
                {"patch_summary": "fixed", "files_changed": [], "fixes_applied": []},
                phase_id=phase_id,
            )
        )

    async def _handle_review(self, msg: Message):
        if msg.metadata.get("run_id") != self.run_id:
            return
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return
        asyncio.create_task(self._respond_review(phase_id))

    async def _respond_review(self, phase_id: str):
        await asyncio.sleep(0.01)
        await self.bus.publish(
            dev_review_completed_message(
                self.run_id, "responder",
                {"findings": [], "approved": True},
                phase_id=phase_id,
            )
        )


# ---------------------------------------------------------------------------
# Tests: _derive_recommendations
# ---------------------------------------------------------------------------

def test_derive_recommendations_test_failure():
    """Returns ['target_failing_test_first'] when failing_tests is non-empty."""
    report = {"failing_tests": ["test_foo", "test_bar"], "timed_out": False}
    result = _derive_recommendations(report)
    assert result == ["target_failing_test_first"]


def test_derive_recommendations_timeout():
    """Returns ['increase_timeout_once'] when timed_out is True."""
    report = {"failing_tests": [], "timed_out": True}
    result = _derive_recommendations(report)
    assert result == ["increase_timeout_once"]


def test_derive_recommendations_no_hints():
    """Returns [] when no notable failure indicators."""
    report = {"failing_tests": [], "timed_out": False}
    result = _derive_recommendations(report)
    assert result == []


# ---------------------------------------------------------------------------
# Tests: strategy integration in DevLoopOrchestrator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_strategy_selected_on_fix_iteration():
    """select_strategy() is called with correct failure_class when tests fail."""
    bus = MessageBus()
    mock_selector = MagicMock()
    mock_selector.select_strategy.return_value = _make_fake_decision()

    orchestrator = DevLoopOrchestrator(
        bus,
        sender_id="TestOrch",
        timeout_s=2.0,
        strategy_selector=mock_selector,
    )

    responder = FakeResponder(bus, RUN_ID, fail_first_test=True)
    responder.start()

    await orchestrator.run(RUN_ID, goal="test goal")

    mock_selector.select_strategy.assert_called_once()
    call_kwargs = mock_selector.select_strategy.call_args
    assert call_kwargs.kwargs["phase"] == "fix"
    assert call_kwargs.kwargs["evaluation_artifact"]["failure_class"] == "test_failure"


@pytest.mark.asyncio
async def test_strategy_payload_in_fix_request():
    """dev.fix.requested payload includes 'strategy' and 'strategy_reason'."""
    bus = MessageBus()
    mock_selector = MagicMock()
    mock_selector.select_strategy.return_value = _make_fake_decision(
        PlaybookId.TARGET_FAILING_TEST_FIRST
    )

    orchestrator = DevLoopOrchestrator(
        bus,
        sender_id="TestOrch",
        timeout_s=2.0,
        strategy_selector=mock_selector,
    )

    responder = FakeResponder(bus, RUN_ID, fail_first_test=True)
    responder.start()

    await orchestrator.run(RUN_ID, goal="test goal")

    assert len(responder.fix_payloads) == 1
    fix_payload = responder.fix_payloads[0]
    assert "strategy" in fix_payload
    assert "strategy_reason" in fix_payload
    assert fix_payload["strategy"] == PlaybookId.TARGET_FAILING_TEST_FIRST


@pytest.mark.asyncio
async def test_no_strategy_selector_backwards_compat():
    """Without strategy_selector the orchestrator works without errors and
    the fix payload does NOT contain 'strategy' or 'strategy_reason'."""
    bus = MessageBus()

    orchestrator = DevLoopOrchestrator(
        bus,
        sender_id="TestOrch",
        timeout_s=2.0,
        # strategy_selector omitted (default None)
    )

    responder = FakeResponder(bus, RUN_ID, fail_first_test=True)
    responder.start()

    # Should complete without error
    await orchestrator.run(RUN_ID, goal="test goal")

    assert len(responder.fix_payloads) == 1
    fix_payload = responder.fix_payloads[0]
    assert "strategy" not in fix_payload
    assert "strategy_reason" not in fix_payload

"""End-to-end integration test: LLMRouter → DevLoopOrchestrator (Phase 11a).

Tests the full signal flow with a real MockProvider:
  LLMRouter → PlannerAgent → BuilderAgent → ReviewerAgent

No real API calls are made — MockProvider returns pre-configured responses.
"""

import json
import tempfile
from pathlib import Path
from typing import List

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.dev import topics
from genus.dev.agents.builder_agent import BuilderAgent
from genus.dev.agents.planner_agent import PlannerAgent
from genus.dev.agents.reviewer_agent import ReviewerAgent
from genus.dev.agents.tester_agent import TesterAgent
from genus.dev.devloop_orchestrator import DevLoopOrchestrator
from genus.llm.providers.mock_provider import MockProvider
from genus.llm.providers.registry import ProviderRegistry
from genus.llm.router import LLMRouter, TaskType
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_journal(tmp_path: Path, run_id: str) -> RunJournal:
    store = JsonlRunStore(base_dir=str(tmp_path / "runs"))
    journal = RunJournal(run_id, store)
    journal.initialize(goal="E2E LLM test")
    return journal


def _make_router(responses: List[str], tmp_path: Path) -> LLMRouter:
    """Create an LLMRouter backed by a MockProvider."""
    provider = MockProvider(responses=responses)
    registry = ProviderRegistry()
    registry.register(provider)
    scores_path = tmp_path / "scores.jsonl"
    return LLMRouter(registry=registry, scores_path=scores_path)


def _collect(bus: MessageBus, topic: str) -> List[Message]:
    collected: List[Message] = []

    async def _cb(msg: Message) -> None:
        collected.append(msg)

    bus.subscribe(topic, f"__e2e_{topic}__", _cb)
    return collected


# ---------------------------------------------------------------------------
# End-to-end test with MockProvider
# ---------------------------------------------------------------------------

class TestE2EDevLoopWithLLM:
    async def test_full_devloop_llm_router_injected(self, tmp_path: Path) -> None:
        """LLMRouter is injected into all phase agents and stored on the orchestrator."""
        bus = MessageBus()
        run_id = "e2e-llm-001"

        # PlannerAgent response
        plan_response = json.dumps({
            "steps": ["1. Create class", "2. Implement method", "3. Add tests"],
            "plan_summary": "E2E test plan via MockProvider",
        })
        # BuilderAgent response
        builder_response = "# stub implementation\nclass MockAgent:\n    pass\n"
        # ReviewerAgent response
        reviewer_response = json.dumps({
            "approved": True,
            "score": 0.9,
            "issues": [],
            "suggestions": [],
            "summary": "Good code",
        })

        router = _make_router(
            [plan_response, builder_response, reviewer_response],
            tmp_path,
        )
        journal = _make_journal(tmp_path, run_id)

        # Agents with llm_router injected
        planner = PlannerAgent(bus, llm_router=router)
        builder = BuilderAgent(bus, llm_router=router)
        tester = TesterAgent(bus, mode="ok")
        reviewer = ReviewerAgent(bus, llm_router=router)

        completed: List[Message] = _collect(bus, topics.DEV_LOOP_COMPLETED)
        failed: List[Message] = _collect(bus, topics.DEV_LOOP_FAILED)

        planner.start()
        builder.start()
        tester.start()
        reviewer.start()

        try:
            orchestrator = DevLoopOrchestrator(
                bus=bus,
                run_journal=journal,
                timeout_s=5.0,
                llm_router=router,
            )

            # The orchestrator must store the router
            assert orchestrator._llm_router is router

            await orchestrator.run(run_id=run_id, goal="Create a simple test agent")

            # Loop should complete (reviewer approved=True, no high-sev findings)
            assert len(completed) == 1, f"Expected loop.completed; failed msgs: {[m.payload for m in failed]}"
            assert len(failed) == 0

        finally:
            planner.stop()
            builder.stop()
            tester.stop()
            reviewer.stop()

    async def test_devloop_without_llm_router_still_works(self, tmp_path: Path) -> None:
        """DevLoopOrchestrator without llm_router → stub mode, backward compatible."""
        bus = MessageBus()
        run_id = "e2e-stub-001"
        journal = _make_journal(tmp_path, run_id)

        # Agents without llm_router → stub mode
        planner = PlannerAgent(bus, mode="ok")
        builder = BuilderAgent(bus, mode="ok")
        tester = TesterAgent(bus, mode="ok")
        reviewer = ReviewerAgent(bus, mode="ok", review_profile="clean")

        completed: List[Message] = _collect(bus, topics.DEV_LOOP_COMPLETED)

        planner.start()
        builder.start()
        tester.start()
        reviewer.start()

        try:
            orchestrator = DevLoopOrchestrator(
                bus=bus,
                run_journal=journal,
                timeout_s=5.0,
                llm_router=None,
            )

            assert orchestrator._llm_router is None

            await orchestrator.run(run_id=run_id, goal="Stub mode test")

            assert len(completed) == 1

        finally:
            planner.stop()
            builder.stop()
            tester.stop()
            reviewer.stop()

    async def test_llm_router_scores_populated_after_run(self, tmp_path: Path) -> None:
        """After a run with MockProvider, the router has been used (call_count > 0)."""
        bus = MessageBus()
        run_id = "e2e-scores-001"

        plan_response = json.dumps({
            "steps": ["step1"],
            "plan_summary": "Score test plan",
        })
        builder_response = "# code\npass\n"
        # Reviewer uses legacy path (no 'code' in review payload by default)
        # so we just check the MockProvider was called for planning
        router = _make_router(
            [plan_response, builder_response, plan_response],
            tmp_path,
        )
        # Track call count via the provider directly
        mock_provider = router._registry.get("mock")

        journal = _make_journal(tmp_path, run_id)

        planner = PlannerAgent(bus, llm_router=router)
        builder = BuilderAgent(bus, llm_router=router)
        tester = TesterAgent(bus, mode="ok")
        reviewer = ReviewerAgent(bus, llm_router=router)

        planner.start()
        builder.start()
        tester.start()
        reviewer.start()

        try:
            orchestrator = DevLoopOrchestrator(
                bus=bus,
                run_journal=journal,
                timeout_s=5.0,
                llm_router=router,
            )
            await orchestrator.run(run_id=run_id, goal="Score feedback test")
        finally:
            planner.stop()
            builder.stop()
            tester.stop()
            reviewer.stop()

        # The MockProvider should have been called at least once (for planning or building)
        assert mock_provider._call_count >= 1, (
            f"Expected MockProvider to be called at least once, got {mock_provider._call_count}"
        )

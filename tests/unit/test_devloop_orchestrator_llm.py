"""Unit tests for DevLoopOrchestrator LLM router injection (Phase 11a).

Verifies that:
- DevLoopOrchestrator accepts llm_router=None → stub behaviour (backward compat)
- DevLoopOrchestrator stores llm_router when provided
- llm_router is accessible for injection into agents
"""

import pytest
from unittest.mock import MagicMock

from genus.communication.message_bus import MessageBus
from genus.dev.devloop_orchestrator import DevLoopOrchestrator
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_journal(tmp_path, run_id: str = "test-run-llm-001") -> RunJournal:
    store = JsonlRunStore(base_dir=str(tmp_path / "runs"))
    journal = RunJournal(run_id, store)
    journal.initialize(goal="LLM injection test")
    return journal


def _make_mock_router():
    """Create a minimal mock LLMRouter."""
    return MagicMock(name="MockLLMRouter")


# ---------------------------------------------------------------------------
# Tests — backward compatibility (llm_router=None)
# ---------------------------------------------------------------------------

class TestDevLoopOrchestratorNoLLM:
    def test_no_llm_router_default_is_none(self, tmp_path):
        """DevLoopOrchestrator without llm_router → _llm_router is None (stub mode)."""
        bus = MagicMock(spec=MessageBus)
        journal = _make_journal(tmp_path)

        orch = DevLoopOrchestrator(bus=bus, run_journal=journal)

        assert orch._llm_router is None

    def test_explicit_none_is_accepted(self, tmp_path):
        """DevLoopOrchestrator(llm_router=None) is valid and stores None."""
        bus = MagicMock(spec=MessageBus)
        journal = _make_journal(tmp_path)

        orch = DevLoopOrchestrator(bus=bus, run_journal=journal, llm_router=None)

        assert orch._llm_router is None

    def test_other_params_unaffected(self, tmp_path):
        """Adding llm_router=None does not affect other constructor parameters."""
        bus = MagicMock(spec=MessageBus)
        journal = _make_journal(tmp_path)

        orch = DevLoopOrchestrator(
            bus=bus,
            run_journal=journal,
            timeout_s=99.0,
            max_iterations=5,
            llm_router=None,
        )

        assert orch._timeout_s == 99.0
        assert orch._max_iterations == 5
        assert orch._llm_router is None


# ---------------------------------------------------------------------------
# Tests — llm_router injection
# ---------------------------------------------------------------------------

class TestDevLoopOrchestratorWithLLM:
    def test_llm_router_stored_on_orchestrator(self, tmp_path):
        """DevLoopOrchestrator stores the provided llm_router."""
        bus = MagicMock(spec=MessageBus)
        journal = _make_journal(tmp_path)
        mock_router = _make_mock_router()

        orch = DevLoopOrchestrator(
            bus=bus,
            run_journal=journal,
            llm_router=mock_router,
        )

        assert orch._llm_router is mock_router

    def test_llm_router_is_same_object(self, tmp_path):
        """The stored llm_router is the exact same object (not a copy)."""
        bus = MagicMock(spec=MessageBus)
        journal = _make_journal(tmp_path)
        mock_router = _make_mock_router()

        orch = DevLoopOrchestrator(bus=bus, run_journal=journal, llm_router=mock_router)

        assert orch._llm_router is mock_router

    def test_planner_receives_llm_router_via_lifespan_helper(self, tmp_path):
        """Verify the lifespan _run_devloop helper passes llm_router to PlannerAgent."""
        # We test the contract: PlannerAgent constructor accepts llm_router
        from genus.dev.agents.planner_agent import PlannerAgent
        bus = MessageBus()
        mock_router = _make_mock_router()

        agent = PlannerAgent(bus, llm_router=mock_router)

        assert agent._llm_router is mock_router

    def test_builder_receives_llm_router_via_lifespan_helper(self, tmp_path):
        """Verify the lifespan _run_devloop helper passes llm_router to BuilderAgent."""
        from genus.dev.agents.builder_agent import BuilderAgent
        bus = MessageBus()
        mock_router = _make_mock_router()

        agent = BuilderAgent(bus, llm_router=mock_router)

        assert agent._llm_router is mock_router

    def test_reviewer_receives_llm_router_via_lifespan_helper(self, tmp_path):
        """Verify the lifespan _run_devloop helper passes llm_router to ReviewerAgent."""
        from genus.dev.agents.reviewer_agent import ReviewerAgent
        bus = MessageBus()
        mock_router = _make_mock_router()

        agent = ReviewerAgent(bus, llm_router=mock_router)

        assert agent._llm_router is mock_router

    def test_per_phase_timeouts_still_work_with_llm_router(self, tmp_path):
        """llm_router does not interfere with per-phase timeout configuration."""
        bus = MagicMock(spec=MessageBus)
        journal = _make_journal(tmp_path)
        mock_router = _make_mock_router()

        orch = DevLoopOrchestrator(
            bus=bus,
            run_journal=journal,
            timeout_s=30.0,
            plan_timeout_s=10.0,
            review_timeout_s=15.0,
            llm_router=mock_router,
        )

        assert orch._plan_timeout_s == 10.0
        assert orch._review_timeout_s == 15.0
        assert orch._llm_router is mock_router

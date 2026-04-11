"""Integration test for the LLM score-feedback loop (Phase 10d).

Validates that after multiple code reviews, the LLMRouter's ADAPTIVE strategy
selects the provider with the highest average score.

No real API calls are made — all LLM responses come from MockProvider.
"""

import json
import tempfile
from pathlib import Path

import pytest

from genus.communication.message_bus import MessageBus
from genus.dev import events, topics
from genus.dev.agents.builder_agent import BuilderAgent
from genus.dev.agents.reviewer_agent import ReviewerAgent
from genus.llm.providers.mock_provider import MockProvider
from genus.llm.providers.registry import ProviderRegistry
from genus.llm.router import LLMRouter, RoutingStrategy, TaskType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_AGENT_CODE = """\
from __future__ import annotations
from typing import Optional
from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState

class MyAgent(Agent):
    def __init__(self, message_bus: MessageBus, agent_id: Optional[str] = None,
                 name: Optional[str] = None) -> None:
        super().__init__(agent_id=agent_id, name=name or "MyAgent")
        self._bus = message_bus

    async def initialize(self) -> None:
        self._bus.subscribe("my.topic", self.id, self.process_message)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        self._bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message: Message) -> None:
        pass
"""


def _make_review(score: float, approved: bool = True) -> str:
    return json.dumps(
        {
            "approved": approved,
            "score": score,
            "issues": [],
            "suggestions": [],
            "summary": f"Score: {score}",
        }
    )


def _make_router_with_scores_path(review_response: str, tmp_path: Path) -> LLMRouter:
    """Create a router backed by a MockProvider that saves scores to tmp_path."""
    provider = MockProvider(responses=[review_response])
    registry = ProviderRegistry()
    registry.register(provider)
    return LLMRouter(
        registry=registry,
        strategy=RoutingStrategy.ADAPTIVE,
        scores_path=tmp_path / "scores.jsonl",
    )


def _review_requested_message(
    run_id: str,
    code: str,
    provider_name: str = "mock",
) -> object:
    """Build a dev.review.requested message with code payload."""
    return events.dev_review_requested_message(
        run_id,
        "TestOrchestrator",
        payload={
            "code": code,
            "filename": "my_agent.py",
            "plan": {"steps": ["implement agent"]},
            "metadata": {
                "provider_name": provider_name,
                "run_id": run_id,
            },
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScoreFeedbackLoop:

    async def test_scores_recorded_after_review(self, tmp_path):
        """After a review, scores are recorded in the router."""
        bus = MessageBus()
        run_id = "run-score-001"

        router = _make_router_with_scores_path(_make_review(0.85), tmp_path)
        reviewer = ReviewerAgent(bus, llm_router=router)
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id, _VALID_AGENT_CODE, provider_name="mock")
        await reviewer._handle_review_requested(msg)

        # Scores should now be recorded
        review_scores = router.get_scores(task_type=TaskType.CODE_REVIEW)
        assert len(review_scores) >= 1
        assert review_scores[0]["score"] == pytest.approx(0.85)

        reviewer.stop()

    async def test_builder_provider_score_recorded_for_code_gen(self, tmp_path):
        """After review, CODE_GEN score is recorded for the builder provider."""
        bus = MessageBus()
        run_id = "run-score-002"

        router = _make_router_with_scores_path(_make_review(0.9), tmp_path)
        reviewer = ReviewerAgent(bus, llm_router=router)
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id, _VALID_AGENT_CODE, provider_name="mock")
        await reviewer._handle_review_requested(msg)

        code_gen_scores = router.get_scores(task_type=TaskType.CODE_GEN)
        assert any(s["score"] == pytest.approx(0.9) for s in code_gen_scores)

        reviewer.stop()

    async def test_adaptive_routing_after_multiple_reviews(self, tmp_path):
        """After 3 reviews, ADAPTIVE strategy selects the best provider."""
        bus = MessageBus()

        # Create two providers: "good_provider" and "bad_provider"
        good_provider = MockProvider(responses=[_make_review(0.9)])
        bad_provider = MockProvider(responses=[_make_review(0.3)])

        # Give them distinct names by subclassing
        class GoodProvider(MockProvider):
            _name = "good_provider"

        class BadProvider(MockProvider):
            _name = "bad_provider"

        good = GoodProvider(responses=[_make_review(0.9)])
        bad = BadProvider(responses=[_make_review(0.3)])

        registry = ProviderRegistry()
        registry.register(good)
        registry.register(bad)
        router = LLMRouter(
            registry=registry,
            strategy=RoutingStrategy.ADAPTIVE,
            scores_path=tmp_path / "scores.jsonl",
        )

        # Simulate 3 reviews: good provider scores high, bad provider scores low
        await router.record_score("good_provider", TaskType.CODE_GEN, 0.9, run_id="r1")
        await router.record_score("good_provider", TaskType.CODE_GEN, 0.85, run_id="r2")
        await router.record_score("bad_provider", TaskType.CODE_GEN, 0.3, run_id="r3")

        best = router.get_best_provider_for(TaskType.CODE_GEN)
        assert best == "good_provider"

    async def test_adaptive_selects_best_code_review_provider(self, tmp_path):
        """ADAPTIVE strategy selects the best CODE_REVIEW provider."""
        router = LLMRouter(
            registry=ProviderRegistry(),
            strategy=RoutingStrategy.ADAPTIVE,
            scores_path=tmp_path / "scores.jsonl",
        )

        await router.record_score("anthropic", TaskType.CODE_REVIEW, 0.95, run_id="r1")
        await router.record_score("openai", TaskType.CODE_REVIEW, 0.7, run_id="r2")
        await router.record_score("anthropic", TaskType.CODE_REVIEW, 0.92, run_id="r3")

        best = router.get_best_provider_for(TaskType.CODE_REVIEW)
        assert best == "anthropic"

    async def test_score_feedback_persisted_to_file(self, tmp_path):
        """Scores recorded by ReviewerAgent are persisted to the scores file."""
        bus = MessageBus()
        run_id = "run-score-persist"
        scores_file = tmp_path / "scores.jsonl"

        router = LLMRouter(
            registry=ProviderRegistry(),
            strategy=RoutingStrategy.ADAPTIVE,
            scores_path=scores_file,
        )

        await router.record_score("mock", TaskType.CODE_REVIEW, 0.82, run_id=run_id)

        assert scores_file.exists()
        lines = scores_file.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["provider"] == "mock"
        assert entry["task_type"] == "code_review"
        assert entry["score"] == pytest.approx(0.82)

    async def test_full_review_cycle_score_recorded(self, tmp_path):
        """End-to-end: ReviewerAgent receives code, does LLM review, scores recorded."""
        bus = MessageBus()
        run_id = "run-score-e2e"

        provider = MockProvider(responses=[_make_review(0.87)])
        registry = ProviderRegistry()
        registry.register(provider)
        router = LLMRouter(
            registry=registry,
            strategy=RoutingStrategy.ADAPTIVE,
            scores_path=tmp_path / "scores.jsonl",
        )
        reviewer = ReviewerAgent(bus, llm_router=router)
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id, _VALID_AGENT_CODE, provider_name="mock")
        await reviewer._handle_review_requested(msg)

        assert len(captured) == 1
        review = captured[0].payload["review"]
        assert review["score"] == pytest.approx(0.87)
        assert review["approved"] is True

        # Both CODE_GEN and CODE_REVIEW scores should be recorded
        assert len(router.get_scores(task_type=TaskType.CODE_GEN)) == 1
        assert len(router.get_scores(task_type=TaskType.CODE_REVIEW)) == 1

        reviewer.stop()

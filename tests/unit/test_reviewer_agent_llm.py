"""Unit tests for ReviewerAgent with LLM support (Phase 10d).

All tests use MockProvider — no real API calls are made.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from genus.communication.message_bus import MessageBus
from genus.dev import events, topics
from genus.dev.agents.reviewer_agent import ReviewerAgent
from genus.llm.models import LLMMessage, LLMRole
from genus.llm.providers.mock_provider import MockProvider
from genus.llm.providers.registry import ProviderRegistry
from genus.llm.router import LLMRouter, TaskType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_REVIEW = json.dumps(
    {
        "approved": True,
        "score": 0.88,
        "issues": [],
        "suggestions": ["Add type hints"],
        "summary": "Good code",
    }
)

_SIMPLE_CODE = """\
from genus.core.agent import Agent
class MyAgent(Agent):
    pass
"""

_DANGEROUS_CODE = """\
import os
os.system("rm -rf /")
"""


def _make_router(responses: list) -> LLMRouter:
    """Create an LLMRouter backed by a MockProvider with the given responses."""
    provider = MockProvider(responses=responses)
    registry = ProviderRegistry()
    registry.register(provider)
    return LLMRouter(registry=registry)


def _review_requested_message(
    run_id: str,
    code: str = _SIMPLE_CODE,
    filename: str = "my_agent.py",
    plan: dict = None,
    metadata: dict = None,
):
    """Build a dev.review.requested message with code payload (Phase 10d format)."""
    return events.dev_review_requested_message(
        run_id,
        "TestOrchestrator",
        payload={
            "code": code,
            "filename": filename,
            "plan": plan or {"steps": ["step1", "step2"]},
            "metadata": metadata or {},
        },
    )


# ---------------------------------------------------------------------------
# Tests — LLM-backed review
# ---------------------------------------------------------------------------


class TestReviewerAgentLLM:

    async def test_llm_review_called_and_result_returned(self):
        """dev.review.requested with code → LLM called → dev.review.completed."""
        bus = MessageBus()
        run_id = "run-reviewer-001"
        router = _make_router([MOCK_REVIEW])
        reviewer = ReviewerAgent(bus, llm_router=router)
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id)
        await reviewer._handle_review_requested(msg)

        assert len(captured) == 1
        review = captured[0].payload.get("review", {})
        assert "approved" in review
        assert "score" in review
        assert "issues" in review
        assert "suggestions" in review
        assert "summary" in review

        reviewer.stop()

    async def test_llm_review_fields_correct(self):
        """dev.review.completed contains approved, score, issues, suggestions, summary."""
        bus = MessageBus()
        run_id = "run-reviewer-002"
        router = _make_router([MOCK_REVIEW])
        reviewer = ReviewerAgent(bus, llm_router=router)
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id)
        await reviewer._handle_review_requested(msg)

        review = captured[0].payload["review"]
        assert review["approved"] is True
        assert review["score"] == pytest.approx(0.88)
        assert review["issues"] == []
        assert review["suggestions"] == ["Add type hints"]
        assert review["summary"] == "Good code"

        reviewer.stop()

    async def test_low_score_sets_approved_false(self):
        """score < 0.5 → approved=False regardless of LLM answer."""
        bus = MessageBus()
        run_id = "run-reviewer-003"
        low_score_review = json.dumps(
            {
                "approved": True,  # LLM said True, but score is low
                "score": 0.3,
                "issues": ["Poor structure"],
                "suggestions": [],
                "summary": "Low quality",
            }
        )
        router = _make_router([low_score_review])
        reviewer = ReviewerAgent(bus, llm_router=router)
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id)
        await reviewer._handle_review_requested(msg)

        review = captured[0].payload["review"]
        assert review["approved"] is False
        assert review["score"] == pytest.approx(0.3)

        reviewer.stop()

    async def test_parse_error_fallback_no_crash(self):
        """Parse error in LLM response → fallback review, no crash."""
        bus = MessageBus()
        run_id = "run-reviewer-004"
        router = _make_router(["this is not valid json at all!!!"])
        reviewer = ReviewerAgent(bus, llm_router=router)
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id)
        await reviewer._handle_review_requested(msg)

        assert len(captured) == 1
        review = captured[0].payload["review"]
        assert review["approved"] is True
        assert review["score"] == pytest.approx(0.75)
        assert "LLM review unavailable" in review["summary"]

        reviewer.stop()

    async def test_provider_unavailable_fallback_no_crash(self):
        """LLMProviderUnavailableError → fallback review, no crash."""
        bus = MessageBus()
        run_id = "run-reviewer-005"
        provider = MockProvider(responses=["ignored"], fail_after=0)
        registry = ProviderRegistry()
        registry.register(provider)
        router = LLMRouter(registry=registry)
        reviewer = ReviewerAgent(bus, llm_router=router)
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id)
        await reviewer._handle_review_requested(msg)

        assert len(captured) == 1
        review = captured[0].payload["review"]
        assert review["approved"] is True

        reviewer.stop()

    async def test_record_score_called_with_builder_provider(self):
        """provider_name in metadata → record_score called for CODE_GEN."""
        bus = MessageBus()
        run_id = "run-reviewer-006"

        mock_router = MagicMock()
        mock_response = MagicMock()
        mock_response.content = MOCK_REVIEW
        mock_response.provider = "mock"
        mock_router.complete = AsyncMock(return_value=mock_response)
        mock_router.record_score = AsyncMock()

        reviewer = ReviewerAgent(bus, llm_router=mock_router)
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(
            run_id,
            metadata={"provider_name": "openai", "run_id": "run-001"},
        )
        await reviewer._handle_review_requested(msg)

        assert len(captured) == 1
        calls = mock_router.record_score.call_args_list
        assert any(
            call.kwargs.get("provider_name") == "openai"
            and call.kwargs.get("task_type") == TaskType.CODE_GEN
            for call in calls
        )

        reviewer.stop()

    async def test_record_score_for_review_provider(self):
        """record_score called with TaskType.CODE_REVIEW for the review provider."""
        bus = MessageBus()
        run_id = "run-reviewer-007"

        mock_router = MagicMock()
        mock_response = MagicMock()
        mock_response.content = MOCK_REVIEW
        mock_response.provider = "mock"
        mock_router.complete = AsyncMock(return_value=mock_response)
        mock_router.record_score = AsyncMock()

        reviewer = ReviewerAgent(bus, llm_router=mock_router)
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id)
        await reviewer._handle_review_requested(msg)

        calls = mock_router.record_score.call_args_list
        assert any(
            call.kwargs.get("provider_name") == "mock"
            and call.kwargs.get("task_type") == TaskType.CODE_REVIEW
            for call in calls
        )

        reviewer.stop()

    async def test_without_llm_router_stub_behaviour(self):
        """Without llm_router but with code in payload → stub review, approved=True."""
        bus = MessageBus()
        run_id = "run-reviewer-008"
        reviewer = ReviewerAgent(bus)  # no llm_router
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id)
        await reviewer._handle_review_requested(msg)

        assert len(captured) == 1
        review = captured[0].payload["review"]
        assert review["approved"] is True
        assert review["score"] == pytest.approx(0.75)
        assert "auto-approved" in review["summary"]

        reviewer.stop()


# ---------------------------------------------------------------------------
# Tests — Security check
# ---------------------------------------------------------------------------


class TestReviewerAgentSecurity:

    async def test_dangerous_code_eval_rejected(self):
        """Code with eval() → approved=False, score=0.0."""
        bus = MessageBus()
        run_id = "run-reviewer-sec-001"
        reviewer = ReviewerAgent(bus, llm_router=_make_router([MOCK_REVIEW]))
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id, code='x = eval("1+1")')
        await reviewer._handle_review_requested(msg)

        review = captured[0].payload["review"]
        assert review["approved"] is False
        assert review["score"] == pytest.approx(0.0)
        assert any("eval(" in issue for issue in review["issues"])

        reviewer.stop()

    async def test_dangerous_code_os_system_rejected(self):
        """Code with os.system() → approved=False, score=0.0."""
        bus = MessageBus()
        run_id = "run-reviewer-sec-002"
        reviewer = ReviewerAgent(bus, llm_router=_make_router([MOCK_REVIEW]))
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id, code=_DANGEROUS_CODE)
        await reviewer._handle_review_requested(msg)

        review = captured[0].payload["review"]
        assert review["approved"] is False
        assert review["score"] == pytest.approx(0.0)

        reviewer.stop()

    async def test_safe_code_not_rejected(self):
        """Clean code → security check passes, LLM review proceeds."""
        bus = MessageBus()
        run_id = "run-reviewer-sec-003"
        router = _make_router([MOCK_REVIEW])
        reviewer = ReviewerAgent(bus, llm_router=router)
        reviewer.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_REVIEW_COMPLETED, "capture", capture)

        msg = _review_requested_message(run_id, code=_SIMPLE_CODE)
        await reviewer._handle_review_requested(msg)

        review = captured[0].payload["review"]
        assert review["approved"] is True
        assert review["score"] == pytest.approx(0.88)

        reviewer.stop()


# ---------------------------------------------------------------------------
# Tests — _parse_review_response unit tests
# ---------------------------------------------------------------------------


class TestParseReviewResponse:

    def _agent(self):
        return ReviewerAgent(MessageBus())

    def test_valid_json_parsed(self):
        agent = self._agent()
        result = agent._parse_review_response(MOCK_REVIEW)
        assert result["approved"] is True
        assert result["score"] == pytest.approx(0.88)
        assert result["issues"] == []
        assert result["suggestions"] == ["Add type hints"]
        assert result["summary"] == "Good code"

    def test_markdown_json_fence_stripped(self):
        agent = self._agent()
        content = f"```json\n{MOCK_REVIEW}\n```"
        result = agent._parse_review_response(content)
        assert result["score"] == pytest.approx(0.88)

    def test_markdown_plain_fence_stripped(self):
        agent = self._agent()
        content = f"```\n{MOCK_REVIEW}\n```"
        result = agent._parse_review_response(content)
        assert result["score"] == pytest.approx(0.88)

    def test_invalid_json_returns_fallback(self):
        agent = self._agent()
        result = agent._parse_review_response("not json")
        assert result["approved"] is True
        assert result["score"] == pytest.approx(0.75)

    def test_missing_fields_use_defaults(self):
        agent = self._agent()
        result = agent._parse_review_response('{"approved": false}')
        assert result["approved"] is False
        assert result["score"] == pytest.approx(0.75)
        assert result["issues"] == []
        assert result["suggestions"] == []
        assert result["summary"] == ""


# ---------------------------------------------------------------------------
# Tests — _check_security unit tests
# ---------------------------------------------------------------------------


class TestCheckSecurity:

    def _agent(self):
        return ReviewerAgent(MessageBus())

    def test_clean_code_no_issues(self):
        agent = self._agent()
        assert agent._check_security(_SIMPLE_CODE) == []

    def test_eval_detected(self):
        agent = self._agent()
        issues = agent._check_security('x = eval("1+1")')
        assert len(issues) == 1
        assert "eval(" in issues[0]

    def test_exec_detected(self):
        agent = self._agent()
        issues = agent._check_security('exec("import os")')
        assert any("exec(" in i for i in issues)

    def test_os_system_detected(self):
        agent = self._agent()
        issues = agent._check_security('os.system("ls")')
        assert any("os.system(" in i for i in issues)

    def test_multiple_patterns_detected(self):
        agent = self._agent()
        code = 'eval("x"); exec("y")'
        issues = agent._check_security(code)
        assert len(issues) == 2

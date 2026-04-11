"""Unit tests for PlannerAgent with LLM support (Phase 10c).

All tests use MockProvider — no real API calls are made.
"""

import json
import pytest

from genus.communication.message_bus import MessageBus
from genus.dev import events, topics
from genus.dev.agents.planner_agent import PlannerAgent
from genus.llm.exceptions import LLMProviderUnavailableError, LLMResponseParseError
from genus.llm.models import LLMMessage, LLMRole
from genus.llm.providers.mock_provider import MockProvider
from genus.llm.providers.registry import ProviderRegistry
from genus.llm.router import LLMRouter, TaskType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_router(responses: list) -> LLMRouter:
    """Create an LLMRouter backed by a MockProvider with the given responses."""
    provider = MockProvider(responses=responses)
    registry = ProviderRegistry()
    registry.register(provider)
    return LLMRouter(registry=registry)


def _plan_requested_message(run_id: str, requirements=None, constraints=None, metadata=None):
    """Build a dev.plan.requested message."""
    return events.dev_plan_requested_message(
        run_id,
        "TestOrchestrator",
        requirements=requirements or [],
        constraints=constraints or [],
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Tests — LLM-backed planning
# ---------------------------------------------------------------------------

class TestPlannerAgentLLM:

    async def test_llm_called_and_steps_returned(self):
        """dev.plan.requested → LLM is called → dev.plan.completed with LLM steps."""
        bus = MessageBus()
        run_id = "run-test-001"
        llm_response = json.dumps({
            "steps": ["step1", "step2"],
            "plan_summary": "test plan",
        })
        router = _make_router([llm_response])
        planner = PlannerAgent(bus, llm_router=router)
        planner.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_PLAN_COMPLETED, "capture", capture)

        msg = _plan_requested_message(run_id, requirements=["req1"])
        await planner._handle_plan_requested(msg)

        assert len(captured) == 1
        plan = captured[0].payload["plan"]
        assert plan["steps"] == ["step1", "step2"]
        assert plan["plan_summary"] == "test plan"

        planner.stop()

    async def test_plan_summary_populated(self):
        """plan_summary is correctly included in the plan payload."""
        bus = MessageBus()
        run_id = "run-test-002"
        llm_response = json.dumps({
            "steps": ["do something"],
            "plan_summary": "My detailed summary",
        })
        router = _make_router([llm_response])
        planner = PlannerAgent(bus, llm_router=router)
        planner.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_PLAN_COMPLETED, "capture", capture)

        msg = _plan_requested_message(run_id)
        await planner._handle_plan_requested(msg)

        plan = captured[0].payload["plan"]
        assert plan["plan_summary"] == "My detailed summary"

        planner.stop()

    async def test_markdown_fences_stripped(self):
        """Markdown code fences around JSON are correctly stripped."""
        bus = MessageBus()
        run_id = "run-test-003"
        inner = json.dumps({"steps": ["step-from-markdown"], "plan_summary": "ok"})
        llm_response = f"```json\n{inner}\n```"
        router = _make_router([llm_response])
        planner = PlannerAgent(bus, llm_router=router)
        planner.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_PLAN_COMPLETED, "capture", capture)

        msg = _plan_requested_message(run_id)
        await planner._handle_plan_requested(msg)

        plan = captured[0].payload["plan"]
        assert plan["steps"] == ["step-from-markdown"]

        planner.stop()

    async def test_invalid_json_fallback(self):
        """Invalid JSON from LLM → fallback response, no crash."""
        bus = MessageBus()
        run_id = "run-test-004"
        router = _make_router(["this is not valid json!!!"])
        planner = PlannerAgent(bus, llm_router=router)
        planner.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_PLAN_COMPLETED, "capture", capture)

        msg = _plan_requested_message(run_id)
        await planner._handle_plan_requested(msg)

        # Should still publish plan.completed (fallback)
        assert len(captured) == 1
        plan = captured[0].payload["plan"]
        assert "steps" in plan
        # Fallback steps from parse-error path
        assert plan["steps"] == ["implement as specified"]
        assert plan["plan_summary"] == "LLM parse error, using fallback"

        planner.stop()

    async def test_provider_unavailable_fallback(self):
        """LLMProviderUnavailableError → stub fallback, no crash."""
        bus = MessageBus()
        run_id = "run-test-005"
        # fail_after=0 means it fails immediately
        provider = MockProvider(responses=["ignored"], fail_after=0)
        registry = ProviderRegistry()
        registry.register(provider)
        router = LLMRouter(registry=registry)

        planner = PlannerAgent(bus, llm_router=router)
        planner.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_PLAN_COMPLETED, "capture", capture)

        msg = _plan_requested_message(run_id)
        await planner._handle_plan_requested(msg)

        # Should still publish plan.completed with stub steps
        assert len(captured) == 1
        plan = captured[0].payload["plan"]
        assert len(plan["steps"]) > 0

        planner.stop()

    async def test_without_llm_router_stub_behaviour(self):
        """Without llm_router → original stub behaviour (backward compatible)."""
        bus = MessageBus()
        run_id = "run-test-006"
        planner = PlannerAgent(bus)  # no llm_router
        planner.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_PLAN_COMPLETED, "capture", capture)

        msg = _plan_requested_message(run_id, requirements=["do something"])
        await planner._handle_plan_requested(msg)

        assert len(captured) == 1
        plan = captured[0].payload["plan"]
        # Stub returns the four default steps
        assert len(plan["steps"]) == 4
        assert "plan_summary" not in plan  # no summary in stub mode

        planner.stop()

    async def test_agent_spec_template_used_in_prompt(self):
        """agent_spec_template and domain from metadata are included in prompt."""
        bus = MessageBus()
        run_id = "run-test-007"
        captured_requests = []

        class RecordingProvider(MockProvider):
            async def complete(self, request):
                captured_requests.append(request)
                return await super().complete(request)

        provider = RecordingProvider(
            responses=[json.dumps({"steps": ["s1"], "plan_summary": "ok"})]
        )
        registry = ProviderRegistry()
        registry.register(provider)
        router = LLMRouter(registry=registry)

        planner = PlannerAgent(bus, llm_router=router)
        planner.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_PLAN_COMPLETED, "capture", capture)

        msg = _plan_requested_message(
            run_id,
            metadata={
                "agent_spec_template": {"name": "CalendarAgent", "description": "Manages calendar"},
                "domain": "productivity",
            },
        )
        await planner._handle_plan_requested(msg)

        assert len(captured_requests) == 1
        req = captured_requests[0]
        user_content = req.messages[-1].content
        assert "CalendarAgent" in user_content
        assert "productivity" in user_content

        planner.stop()


# ---------------------------------------------------------------------------
# Tests — _parse_plan_response unit tests
# ---------------------------------------------------------------------------

class TestParsePlanResponse:

    def _agent(self):
        return PlannerAgent(MessageBus())

    def test_valid_json(self):
        agent = self._agent()
        result = agent._parse_plan_response(
            '{"steps": ["a", "b"], "plan_summary": "summary"}'
        )
        assert result["steps"] == ["a", "b"]
        assert result["plan_summary"] == "summary"

    def test_markdown_json_fence(self):
        agent = self._agent()
        content = '```json\n{"steps": ["x"], "plan_summary": "s"}\n```'
        result = agent._parse_plan_response(content)
        assert result["steps"] == ["x"]

    def test_markdown_plain_fence(self):
        agent = self._agent()
        content = '```\n{"steps": ["y"], "plan_summary": "t"}\n```'
        result = agent._parse_plan_response(content)
        assert result["steps"] == ["y"]

    def test_missing_fields_fallback(self):
        agent = self._agent()
        result = agent._parse_plan_response('{}')
        assert result["steps"] == []
        assert result["plan_summary"] == ""

    def test_invalid_json_raises(self):
        agent = self._agent()
        with pytest.raises(LLMResponseParseError):
            agent._parse_plan_response("not json at all")

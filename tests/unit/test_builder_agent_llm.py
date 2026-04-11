"""Unit tests for BuilderAgent with LLM support (Phase 10c).

All tests use MockProvider — no real API calls are made.
"""

import json
import pytest

from genus.communication.message_bus import MessageBus
from genus.dev import events, topics
from genus.dev.agents.builder_agent import BuilderAgent
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


def _implement_requested_message(
    run_id: str,
    plan: dict = None,
    metadata: dict = None,
):
    """Build a dev.implement.requested message."""
    return events.dev_implement_requested_message(
        run_id,
        "TestOrchestrator",
        plan=plan or {"steps": ["implement it"]},
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Tests — LLM-backed code generation
# ---------------------------------------------------------------------------

class TestBuilderAgentLLM:

    async def test_llm_called_and_code_returned(self):
        """dev.implement.requested → LLM is called → dev.implement.completed with code."""
        bus = MessageBus()
        run_id = "run-builder-001"
        router = _make_router([_VALID_AGENT_CODE])
        builder = BuilderAgent(bus, llm_router=router)
        builder.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_IMPLEMENT_COMPLETED, "capture", capture)

        msg = _implement_requested_message(run_id)
        await builder._handle_implement_requested(msg)

        assert len(captured) == 1
        payload = captured[0].payload
        assert "code" in payload
        assert "class MyAgent" in payload["code"]
        assert payload["language"] == "python"
        assert payload["filename"].endswith(".py")

        builder.stop()

    async def test_markdown_code_fences_stripped(self):
        """Markdown ```python fences are stripped from generated code."""
        bus = MessageBus()
        run_id = "run-builder-002"
        fenced_code = f"```python\n{_VALID_AGENT_CODE}\n```"
        router = _make_router([fenced_code])
        builder = BuilderAgent(bus, llm_router=router)
        builder.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_IMPLEMENT_COMPLETED, "capture", capture)

        msg = _implement_requested_message(run_id)
        await builder._handle_implement_requested(msg)

        payload = captured[0].payload
        # Code should not contain the fence markers
        assert not payload["code"].startswith("```")

        builder.stop()

    async def test_syntax_error_fallback(self):
        """Code with syntax errors → fallback stub, no crash."""
        bus = MessageBus()
        run_id = "run-builder-003"
        bad_code = "class BrokenAgent(\n    # intentional syntax error"
        router = _make_router([bad_code])
        builder = BuilderAgent(bus, llm_router=router)
        builder.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_IMPLEMENT_COMPLETED, "capture", capture)

        msg = _implement_requested_message(run_id)
        await builder._handle_implement_requested(msg)

        # Should still publish implement.completed (stub fallback)
        assert len(captured) == 1
        payload = captured[0].payload
        assert payload["code"] == "# stub"

        builder.stop()

    async def test_provider_unavailable_fallback(self):
        """LLMProviderUnavailableError → stub fallback, no crash."""
        bus = MessageBus()
        run_id = "run-builder-004"
        provider = MockProvider(responses=["ignored"], fail_after=0)
        registry = ProviderRegistry()
        registry.register(provider)
        router = LLMRouter(registry=registry)

        builder = BuilderAgent(bus, llm_router=router)
        builder.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_IMPLEMENT_COMPLETED, "capture", capture)

        msg = _implement_requested_message(run_id)
        await builder._handle_implement_requested(msg)

        # Should still publish implement.completed (stub fallback)
        assert len(captured) == 1

        builder.stop()

    async def test_without_llm_router_stub_behaviour(self):
        """Without llm_router → original stub behaviour (backward compatible)."""
        bus = MessageBus()
        run_id = "run-builder-005"
        builder = BuilderAgent(bus)  # no llm_router
        builder.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_IMPLEMENT_COMPLETED, "capture", capture)

        msg = _implement_requested_message(run_id)
        await builder._handle_implement_requested(msg)

        assert len(captured) == 1
        payload = captured[0].payload
        # Stub mode: no code key in payload
        assert "code" not in payload
        assert payload["patch_summary"] == "Implemented planned changes (placeholder)"

        builder.stop()

    async def test_agent_spec_template_sets_filename(self):
        """agent_spec_template.name is used to derive the output filename."""
        bus = MessageBus()
        run_id = "run-builder-006"
        router = _make_router([_VALID_AGENT_CODE])
        builder = BuilderAgent(bus, llm_router=router)
        builder.start()

        captured = []

        async def capture(msg):
            captured.append(msg)

        bus.subscribe(topics.DEV_IMPLEMENT_COMPLETED, "capture", capture)

        msg = _implement_requested_message(
            run_id,
            metadata={
                "agent_spec_template": {
                    "name": "CalendarAgent",
                    "topics": ["calendar.event.created"],
                }
            },
        )
        await builder._handle_implement_requested(msg)

        payload = captured[0].payload
        assert payload["filename"] == "calendar_agent.py"

        builder.stop()


# ---------------------------------------------------------------------------
# Tests — _parse_code_response unit tests
# ---------------------------------------------------------------------------

class TestParseCodeResponse:

    def _agent(self):
        return BuilderAgent(MessageBus())

    def test_valid_code_parsed(self):
        agent = self._agent()
        result = agent._parse_code_response(_VALID_AGENT_CODE, "MyAgent")
        assert "class MyAgent" in result["code"]
        assert result["filename"] == "my_agent.py"
        assert result["language"] == "python"

    def test_markdown_python_fence_stripped(self):
        agent = self._agent()
        content = f"```python\n{_VALID_AGENT_CODE}\n```"
        result = agent._parse_code_response(content, "MyAgent")
        assert not result["code"].startswith("```")

    def test_markdown_plain_fence_stripped(self):
        agent = self._agent()
        content = f"```\n{_VALID_AGENT_CODE}\n```"
        result = agent._parse_code_response(content, "MyAgent")
        assert not result["code"].startswith("```")

    def test_syntax_error_raises(self):
        agent = self._agent()
        with pytest.raises(LLMResponseParseError):
            agent._parse_code_response(
                "class Broken(\n    # no closing paren", "Broken"
            )

    def test_camel_case_filename_conversion(self):
        agent = self._agent()
        result = agent._parse_code_response("x = 1", "FamilyCalendarAgent")
        assert result["filename"] == "family_calendar_agent.py"

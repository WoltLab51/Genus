"""Unit tests for ConversationAgent — Phase 13."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from genus.communication.message_bus import Message, MessageBus
from genus.conversation.conversation_agent import (
    ConversationAgent,
    ConversationResponse,
    Intent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_bus_spy() -> MagicMock:
    bus = MagicMock(spec=MessageBus)
    bus.publish = AsyncMock()
    return bus


def make_agent(bus=None, llm_router=None, tmp_path=None) -> ConversationAgent:
    if bus is None:
        bus = make_bus_spy()
    from pathlib import Path
    conversations_dir = tmp_path if tmp_path is not None else Path("/tmp/genus-test-convs")
    agent = ConversationAgent(
        message_bus=bus,
        llm_router=llm_router,
        conversations_dir=conversations_dir,
    )
    return agent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConversationAgentNoLLM:
    async def test_no_llm_router_friendly_fallback(self, tmp_path):
        """Without llm_router → friendly message, no crash."""
        agent = make_agent(tmp_path=tmp_path)
        response = await agent.process_user_message(
            text="Hey GENUS, wie geht's?",
            user_id="user-001",
            session_id="sess-001",
        )
        assert isinstance(response, ConversationResponse)
        assert len(response.text) > 0
        assert "LLM" in response.text or "konfiguriert" in response.text.lower() or "denken" in response.text.lower()

    async def test_no_crash_on_empty_text_after_classify(self, tmp_path):
        """Very short text should classify as CHAT and return fallback."""
        agent = make_agent(tmp_path=tmp_path)
        response = await agent.process_user_message(
            text="Hi",
            user_id="anon",
            session_id="sess-002",
        )
        assert isinstance(response, ConversationResponse)


class TestConversationAgentSystemCommand:
    async def test_system_command_publishes_kill_switch(self, tmp_path):
        """SYSTEM_COMMAND → kill-switch topic is published on MessageBus."""
        bus = make_bus_spy()
        agent = make_agent(bus=bus, tmp_path=tmp_path)

        response = await agent.process_user_message(
            text="Stopp alles!",
            user_id="operator",
            session_id="sess-cmd",
        )

        assert response.intent == Intent.SYSTEM_COMMAND.value
        bus.publish.assert_called_once()
        msg: Message = bus.publish.call_args[0][0]
        from genus.conversation.conversation_agent import TOPIC_SYSTEM_KILL_SWITCH
        assert msg.topic == TOPIC_SYSTEM_KILL_SWITCH
        assert "kill_switch_requested" in response.actions_taken


class TestConversationAgentDevRequest:
    async def test_dev_request_publishes_dev_run_requested(self, tmp_path):
        """DEV_REQUEST → dev.run.requested topic is published."""
        bus = make_bus_spy()
        agent = make_agent(bus=bus, tmp_path=tmp_path)

        response = await agent.process_user_message(
            text="Bau mir einen neuen Monitoring-Agent",
            user_id="user-dev",
            session_id="sess-dev",
        )

        assert response.intent == Intent.DEV_REQUEST.value
        assert response.run_id is not None
        assert response.run_id.startswith("conv_sess-dev_")

        bus.publish.assert_called_once()
        msg: Message = bus.publish.call_args[0][0]
        from genus.conversation.conversation_agent import TOPIC_DEV_RUN_REQUESTED
        assert msg.topic == TOPIC_DEV_RUN_REQUESTED
        assert msg.payload["goal"] == "Bau mir einen neuen Monitoring-Agent"
        assert "dev_loop_started" in response.actions_taken[0]


class TestConversationAgentMemory:
    async def test_memory_updated_after_message(self, tmp_path):
        """Memory contains both user message and assistant response after exchange."""
        agent = make_agent(tmp_path=tmp_path)
        await agent.process_user_message(
            text="Hey GENUS",
            user_id="user",
            session_id="sess-mem",
        )
        memory = agent._get_or_create_memory("sess-mem")
        ctx = memory.get_context()
        assert len(ctx) == 2
        assert ctx[0]["role"] == "user"
        assert ctx[0]["content"] == "Hey GENUS"
        assert ctx[1]["role"] == "assistant"

    async def test_same_session_accumulates_history(self, tmp_path):
        """Multiple messages to the same session accumulate in memory."""
        agent = make_agent(tmp_path=tmp_path)
        for i in range(3):
            await agent.process_user_message(
                text=f"Nachricht {i}",
                user_id="user",
                session_id="sess-hist",
            )
        memory = agent._get_or_create_memory("sess-hist")
        ctx = memory.get_context()
        # 3 user messages + 3 assistant responses = 6 entries (capped to max_history=20)
        assert len(ctx) == 6

    async def test_different_sessions_isolated(self, tmp_path):
        """Two sessions do not share memory."""
        agent = make_agent(tmp_path=tmp_path)
        await agent.process_user_message(
            text="Session A message",
            user_id="user",
            session_id="sess-A",
        )
        await agent.process_user_message(
            text="Session B message",
            user_id="user",
            session_id="sess-B",
        )
        mem_a = agent._get_or_create_memory("sess-A")
        mem_b = agent._get_or_create_memory("sess-B")
        assert all(
            e["content"] != "Session B message" for e in mem_a.get_context()
        )
        assert all(
            e["content"] != "Session A message" for e in mem_b.get_context()
        )


class TestConversationAgentLLMTemperature:
    async def test_temperature_passed_to_llm_router(self, tmp_path):
        """strategy.temperature must be forwarded exactly to llm_router.complete() — Fix 1."""
        from genus.llm.models import LLMResponse
        from genus.conversation.prompt_strategy import PromptStrategy
        from genus.llm.router import TaskType

        sentinel_temperature = 0.123
        fixed_strategy = PromptStrategy(
            task_type=TaskType.GENERAL,
            max_tokens=512,
            temperature=sentinel_temperature,
            context_depth=10,
            include_profile=True,
            include_episodic=False,
        )
        mock_response = LLMResponse(
            content="Hallo!",
            model="mock",
            provider="mock",
        )
        llm_router = MagicMock()
        llm_router.complete = AsyncMock(return_value=mock_response)

        agent = make_agent(llm_router=llm_router, tmp_path=tmp_path)
        with patch(
            "genus.conversation.prompt_strategy.resolve_prompt_strategy",
            return_value=fixed_strategy,
        ):
            await agent.process_user_message(
                text="Erzähl mir etwas",
                user_id="user-001",
                session_id="sess-temp",
            )

        llm_router.complete.assert_called_once()
        call_kwargs = llm_router.complete.call_args.kwargs
        assert "temperature" in call_kwargs, "temperature must be forwarded to llm_router.complete()"
        assert call_kwargs["temperature"] == sentinel_temperature, (
            f"Expected temperature={sentinel_temperature}, got {call_kwargs['temperature']}"
        )


class TestConversationAgentLifecycle:
    async def test_initialize_and_start(self, tmp_path):
        """ConversationAgent can be initialized and started without errors."""
        from genus.core.agent import AgentState
        agent = make_agent(tmp_path=tmp_path)
        await agent.initialize()
        await agent.start()
        assert agent.state == AgentState.RUNNING

    async def test_stop(self, tmp_path):
        from genus.core.agent import AgentState
        agent = make_agent(tmp_path=tmp_path)
        await agent.initialize()
        await agent.start()
        await agent.stop()
        assert agent.state == AgentState.STOPPED


# ---------------------------------------------------------------------------
# Phase 15a — ResonanceLayer + InnerMonologue
# ---------------------------------------------------------------------------


class TestConversationAgentPhase15aBackwardCompat:
    async def test_no_memory_stores_still_works(self, tmp_path):
        """ConversationAgent without memory stores — backward compatible."""
        agent = make_agent(tmp_path=tmp_path)
        assert agent._episode_store is None
        assert agent._fact_store is None
        assert agent._inner_monologue is None

    async def test_no_llm_no_inner_monologue_fallback(self, tmp_path):
        """No LLM + inner_monologue provided → fallback response, no crash."""
        from unittest.mock import MagicMock
        im = MagicMock()
        im.get_current.return_value = None
        im.set.return_value = MagicMock()
        bus = make_bus_spy()
        from genus.conversation.conversation_agent import ConversationAgent
        from pathlib import Path
        agent = ConversationAgent(
            message_bus=bus,
            inner_monologue=im,
            conversations_dir=tmp_path,
        )
        response = await agent.process_user_message(
            text="Hey GENUS",
            user_id="user1",
            session_id="sess-compat",
        )
        assert isinstance(response.text, str)
        assert len(response.text) > 0


class TestConversationAgentMemoryRequest:
    async def test_memory_request_calls_handle_memory_request(self, tmp_path):
        """MEMORY_REQUEST → _handle_memory_request is called (via LLM or fallback)."""
        from genus.llm.models import LLMResponse
        from unittest.mock import MagicMock, AsyncMock, patch

        mock_response = LLMResponse(content="Ich erinnere mich...", model="mock", provider="mock")
        llm_router = MagicMock()
        llm_router.complete = AsyncMock(return_value=mock_response)

        bus = make_bus_spy()
        from genus.conversation.conversation_agent import ConversationAgent
        agent = ConversationAgent(
            message_bus=bus,
            llm_router=llm_router,
            conversations_dir=tmp_path,
        )

        response = await agent.process_user_message(
            text="Was haben wir letzte Woche besprochen?",
            user_id="user1",
            session_id="sess-mem-req",
        )
        # Should get a response (not crash), LLM was called
        assert isinstance(response.text, str)
        assert llm_router.complete.called


class TestConversationAgentResonanceLayer:
    async def test_resonance_block_injected_when_episode_store_present(self, tmp_path):
        """When episode_store returns episodes, resonance block appears in LLM messages."""
        from genus.llm.models import LLMResponse, LLMMessage
        from unittest.mock import MagicMock, AsyncMock

        # Capture LLM messages
        captured_messages: list[list[LLMMessage]] = []

        async def capture_complete(messages, **kwargs):
            captured_messages.append(list(messages))
            return LLMResponse(content="Antwort", model="mock", provider="mock")

        llm_router = MagicMock()
        llm_router.complete = AsyncMock(side_effect=capture_complete)

        # Episode store with one episode
        from genus.memory.episode_store import Episode
        ep = Episode.create(
            user_id="user1",
            summary="Wir haben Solar besprochen",
            topics=["solar"],
            session_ids=["s1"],
            message_count=5,
        )
        from genus.memory.episode_store import EpisodeStore
        ep_store = EpisodeStore(base_dir=str(tmp_path / "episodes"))
        ep_store.append(ep)

        bus = make_bus_spy()
        from genus.conversation.conversation_agent import ConversationAgent
        agent = ConversationAgent(
            message_bus=bus,
            llm_router=llm_router,
            episode_store=ep_store,
            conversations_dir=tmp_path,
        )

        await agent.process_user_message(
            text="Erzähl mir etwas",
            user_id="user1",
            session_id="sess-resonance",
        )

        assert captured_messages, "LLM must have been called"
        messages = captured_messages[0]
        # Find resonance block
        contents = [m.content for m in messages]
        resonance_found = any("GENUS Gedächtnis" in c for c in contents)
        assert resonance_found, "Resonance block must appear in LLM messages"


class TestConversationAgentInnerMonologue:
    async def test_stress_keyword_sets_inner_note(self, tmp_path):
        """User message with stress keyword → InnerMonologue.set is called."""
        from unittest.mock import MagicMock

        im = MagicMock()
        im.get_current.return_value = None
        im.set.return_value = MagicMock()

        bus = make_bus_spy()
        from genus.conversation.conversation_agent import ConversationAgent
        agent = ConversationAgent(
            message_bus=bus,
            inner_monologue=im,
            conversations_dir=tmp_path,
        )

        await agent.process_user_message(
            text="Ich hab so viel Stress wegen der Arbeit heute",
            user_id="user1",
            session_id="sess-stress",
        )

        im.set.assert_called_once()
        call_args = im.set.call_args
        assert call_args[0][0] == "user1"  # user_id
        assert "angespannt" in call_args[0][1].lower() or "stress" in call_args[0][1].lower()

    async def test_system_command_does_not_set_inner_note(self, tmp_path):
        """SYSTEM_COMMAND → InnerMonologue.set is NOT called."""
        from unittest.mock import MagicMock

        im = MagicMock()
        im.set.return_value = MagicMock()

        bus = make_bus_spy()
        from genus.conversation.conversation_agent import ConversationAgent
        agent = ConversationAgent(
            message_bus=bus,
            inner_monologue=im,
            conversations_dir=tmp_path,
        )

        await agent.process_user_message(
            text="Stopp alles, stress gibt es viel",
            user_id="user1",
            session_id="sess-kill",
        )

        im.set.assert_not_called()

    async def test_short_text_does_not_set_inner_note(self, tmp_path):
        """Message <= 20 chars → InnerMonologue.set is NOT called."""
        from unittest.mock import MagicMock

        im = MagicMock()
        im.set.return_value = MagicMock()

        bus = make_bus_spy()
        from genus.conversation.conversation_agent import ConversationAgent
        agent = ConversationAgent(
            message_bus=bus,
            inner_monologue=im,
            conversations_dir=tmp_path,
        )

        await agent.process_user_message(
            text="Hallo",  # <= 20 chars
            user_id="user1",
            session_id="sess-short",
        )

        im.set.assert_not_called()


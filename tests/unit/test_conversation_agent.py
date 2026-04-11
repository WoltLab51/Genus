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

"""Unit tests for GrowthBridge LLM router injection (Phase 11a).

Verifies that:
- GrowthBridge accepts llm_router parameter (backward compatible: default None)
- GrowthBridge passes llm_router to DevLoopOrchestrator when spawning runs
"""

import asyncio
import pytest
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

from genus.communication.message_bus import Message, MessageBus
from genus.growth.growth_bridge import GrowthBridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_payload(
    need_id: str = "need-llm-001",
    domain: str = "test",
    need_description: str = "test LLM router injection",
) -> dict:
    return {
        "need_id": need_id,
        "domain": domain,
        "need_description": need_description,
        "gate_verdict": "PASS",
        "gate_total_score": 0.85,
        "agent_spec_template": {
            "name": "TestAgent",
            "description": need_description,
        },
    }


def _collect(bus: MessageBus, topic: str) -> List[Message]:
    collected: List[Message] = []

    async def _cb(msg: Message) -> None:
        collected.append(msg)

    bus.subscribe(topic, f"__collector_{topic}__", _cb)
    return collected


def _make_mock_router():
    return MagicMock(name="MockLLMRouter")


# ---------------------------------------------------------------------------
# Tests — backward compatibility (no llm_router)
# ---------------------------------------------------------------------------

class TestGrowthBridgeNoLLM:
    def test_default_llm_router_is_none(self, tmp_path: Path) -> None:
        """GrowthBridge without llm_router → _llm_router is None."""
        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)

        assert bridge._llm_router is None

    def test_explicit_none_accepted(self, tmp_path: Path) -> None:
        """GrowthBridge(llm_router=None) is valid."""
        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path, llm_router=None)

        assert bridge._llm_router is None


# ---------------------------------------------------------------------------
# Tests — llm_router injection into GrowthBridge
# ---------------------------------------------------------------------------

class TestGrowthBridgeWithLLM:
    def test_llm_router_stored(self, tmp_path: Path) -> None:
        """GrowthBridge stores the provided llm_router."""
        bus = MessageBus()
        mock_router = _make_mock_router()
        bridge = GrowthBridge(
            message_bus=bus,
            journal_base_path=tmp_path,
            llm_router=mock_router,
        )

        assert bridge._llm_router is mock_router

    async def test_llm_router_passed_to_orchestrator(self, tmp_path: Path) -> None:
        """GrowthBridge passes llm_router to DevLoopOrchestrator when spawning."""
        bus = MessageBus()
        mock_router = _make_mock_router()
        bridge = GrowthBridge(
            message_bus=bus,
            journal_base_path=tmp_path,
            llm_router=mock_router,
        )

        with patch(
            "genus.growth.growth_bridge.DevLoopOrchestrator",
            autospec=True,
        ) as mock_orch_cls:
            # Make the mock orchestrator's run() return a coroutine immediately
            mock_instance = MagicMock()

            async def _noop_run(**kwargs):
                pass

            mock_instance.run = _noop_run
            mock_orch_cls.return_value = mock_instance

            await bridge.initialize()
            await bridge.start()
            await bus.publish(
                Message(
                    topic="growth.build.requested",
                    payload=_valid_payload(),
                    sender_id="test",
                )
            )
            await asyncio.sleep(0)

            # Verify DevLoopOrchestrator was constructed with llm_router
            assert mock_orch_cls.called, "DevLoopOrchestrator should have been constructed"
            call_kwargs = mock_orch_cls.call_args.kwargs
            assert call_kwargs.get("llm_router") is mock_router, (
                f"Expected llm_router={mock_router!r} in DevLoopOrchestrator constructor, "
                f"got kwargs={call_kwargs!r}"
            )

    async def test_build_requested_with_llm_router_publishes_loop_started(
        self, tmp_path: Path
    ) -> None:
        """growth.build.requested with llm_router still publishes growth.loop.started."""
        bus = MessageBus()
        mock_router = _make_mock_router()
        bridge = GrowthBridge(
            message_bus=bus,
            journal_base_path=tmp_path,
            llm_router=mock_router,
        )
        started: List[Message] = _collect(bus, "growth.loop.started")

        await bridge.initialize()
        await bridge.start()

        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=_valid_payload(),
                sender_id="test",
            )
        )
        await asyncio.sleep(0)

        assert len(started) == 1, "Expected exactly one growth.loop.started message"

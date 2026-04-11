"""
Integration Tests — Full Growth Cycle (Phase 6)

Tests the complete signal flow from ``growth.build.requested`` through to
``agent.bootstrapped`` using:
  - :class:`~genus.growth.growth_bridge.GrowthBridge`
  - :class:`~genus.growth.stub_dev_agent.StubDevAgent`
  - :class:`~genus.growth.bootstrapper.AgentBootstrapper`

These tests prove that the signal path introduced in Phase 6 is complete:

    growth.build.requested
        → GrowthBridge spawns DevLoopOrchestrator (with StubDevAgent responding)
        → dev.loop.completed (enriched by GrowthBridge)
        → AgentBootstrapper receives enriched payload
        → agent.bootstrapped published

All components are real implementations — no mocks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.communication.topic_registry import TopicRegistry
from genus.growth.bootstrapper import AgentBootstrapper
from genus.growth.growth_bridge import GrowthBridge
from genus.growth.stub_dev_agent import StubDevAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_payload(
    need_id: str = "need-integration-001",
    domain: str = "calendar",
    need_description: str = "remind me about meetings",
) -> dict:
    return {
        "need_id": need_id,
        "domain": domain,
        "need_description": need_description,
        "gate_verdict": "PASS",
        "gate_total_score": 0.88,
        "agent_spec_template": {
            "name": f"{domain.title()}Agent",
            "description": need_description,
        },
    }


def _collect(bus: MessageBus, topic: str) -> List[Message]:
    captured: List[Message] = []

    async def _cb(msg: Message) -> None:
        captured.append(msg)

    bus.subscribe(topic, f"__integ_collector_{topic}__", _cb)
    return captured


async def _setup_all(tmp_path: Path):
    """Create and start all agents.  Returns (bus, stub_agent, bootstrapper, bridge)."""
    bus = MessageBus()
    registry = TopicRegistry()

    stub_agent = StubDevAgent(message_bus=bus)
    bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
    bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)

    await stub_agent.initialize()
    await stub_agent.start()
    await bootstrapper.initialize()
    await bootstrapper.start()
    await bridge.initialize()
    await bridge.start()

    return bus, stub_agent, bootstrapper, bridge


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullGrowthCycle:
    async def test_build_requested_leads_to_agent_bootstrapped(self, tmp_path: Path) -> None:
        """Full cycle: growth.build.requested → agent.bootstrapped."""
        bus, stub_agent, bootstrapper, bridge = await _setup_all(tmp_path)
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")

        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=_build_payload(),
                sender_id="GrowthOrchestrator",
            )
        )

        # Allow the entire async chain to complete
        await asyncio.sleep(0.5)

        assert len(bootstrapped) >= 1, (
            "Expected at least one agent.bootstrapped event after the full growth cycle"
        )

    async def test_bootstrapped_payload_has_agent_name(self, tmp_path: Path) -> None:
        """agent.bootstrapped payload contains agent_name."""
        bus, stub_agent, bootstrapper, bridge = await _setup_all(tmp_path)
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")

        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=_build_payload(domain="finance", need_description="expense tracking"),
                sender_id="GrowthOrchestrator",
            )
        )
        await asyncio.sleep(0.5)

        assert len(bootstrapped) >= 1
        assert bootstrapped[-1].payload.get("agent_name"), "agent_name should be non-empty"

    async def test_bootstrapped_payload_has_domain(self, tmp_path: Path) -> None:
        """agent.bootstrapped payload contains domain."""
        bus, stub_agent, bootstrapper, bridge = await _setup_all(tmp_path)
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")

        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=_build_payload(domain="health", need_description="bp tracking"),
                sender_id="GrowthOrchestrator",
            )
        )
        await asyncio.sleep(0.5)

        assert len(bootstrapped) >= 1
        assert bootstrapped[-1].payload.get("domain") == "health"

    async def test_second_build_same_name_triggers_agent_deprecated(
        self, tmp_path: Path
    ) -> None:
        """Second build of the same agent name triggers agent.deprecated."""
        bus, stub_agent, bootstrapper, bridge = await _setup_all(tmp_path)
        deprecated: List[Message] = _collect(bus, "agent.deprecated")

        payload = _build_payload(domain="calendar", need_description="meeting reminders")

        # First build
        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=payload,
                sender_id="GrowthOrchestrator",
            )
        )
        await asyncio.sleep(0.5)

        # Second build with the same agent name (CalendarAgent)
        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=_build_payload(
                    domain="calendar",
                    need_description="meeting reminders",
                    need_id="need-integration-002",
                ),
                sender_id="GrowthOrchestrator",
            )
        )
        await asyncio.sleep(0.5)

        assert len(deprecated) >= 1, (
            "Expected agent.deprecated when bootstrapping a second agent with the same name"
        )

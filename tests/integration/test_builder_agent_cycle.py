"""
Integration Tests — Full Growth Cycle with TemplateBuilderAgent (Phase 7)

Tests the complete signal flow from ``growth.build.requested`` through to
``agent.bootstrapped`` using:

  - :class:`~genus.growth.growth_bridge.GrowthBridge`
  - :class:`~genus.dev.agents.template_builder_agent.TemplateBuilderAgent`
  - :class:`~genus.growth.bootstrapper.AgentBootstrapper`

These tests prove that Phase 7 is complete:

    growth.build.requested
        → GrowthBridge spawns DevLoopOrchestrator
          (with TemplateBuilderAgent responding)
        → TemplateBuilderAgent generates a real .py file on disk
        → dev.loop.completed (enriched by GrowthBridge)
        → AgentBootstrapper receives enriched payload
        → agent.bootstrapped published

All components are real implementations — no mocks.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import List

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.communication.topic_registry import TopicRegistry
from genus.dev.agents.template_builder_agent import TemplateBuilderAgent
from genus.growth.bootstrapper import AgentBootstrapper
from genus.growth.growth_bridge import GrowthBridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_payload(
    need_id: str = "need-phase7-001",
    domain: str = "calendar",
    need_description: str = "remind me about meetings",
    agent_name: str = "CalendarAgent",
    topics: list = None,
) -> dict:
    return {
        "need_id": need_id,
        "domain": domain,
        "need_description": need_description,
        "gate_verdict": "PASS",
        "gate_total_score": 0.88,
        "agent_spec_template": {
            "name": agent_name,
            "description": need_description,
            "topics": topics or ["calendar.event.requested"],
        },
    }


def _collect(bus: MessageBus, topic: str) -> List[Message]:
    captured: List[Message] = []

    async def _cb(msg: Message) -> None:
        captured.append(msg)

    bus.subscribe(topic, f"__integ7_collector_{topic}__", _cb)
    return captured


async def _setup_all(tmp_path: Path):
    """Create and start all agents.  Returns (bus, builder, bootstrapper, bridge)."""
    bus = MessageBus()
    registry = TopicRegistry()

    builder = TemplateBuilderAgent(
        message_bus=bus,
        output_base_path=tmp_path / "generated",
    )
    bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
    bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path / "journals")

    await builder.initialize()
    await builder.start()
    await bootstrapper.initialize()
    await bootstrapper.start()
    await bridge.initialize()
    await bridge.start()

    return bus, builder, bootstrapper, bridge


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuilderAgentCycle:
    async def test_build_requested_leads_to_agent_bootstrapped(self, tmp_path: Path) -> None:
        """Full cycle: growth.build.requested → agent.bootstrapped."""
        bus, builder, bootstrapper, bridge = await _setup_all(tmp_path)
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")

        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=_build_payload(),
                sender_id="GrowthOrchestrator",
            )
        )

        await asyncio.sleep(0.5)

        assert len(bootstrapped) >= 1, (
            "Expected at least one agent.bootstrapped event after the full growth cycle"
        )

    async def test_generated_file_exists_on_disk(self, tmp_path: Path) -> None:
        """After the cycle a .py file is written to the generated directory."""
        bus, builder, bootstrapper, bridge = await _setup_all(tmp_path)

        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=_build_payload(domain="family", agent_name="FamilyAgent"),
                sender_id="GrowthOrchestrator",
            )
        )

        await asyncio.sleep(0.5)

        generated_dir = tmp_path / "generated"
        py_files = [f for f in generated_dir.glob("*.py") if f.name != "__init__.py"]
        assert len(py_files) >= 1, (
            f"Expected at least one generated .py file in {generated_dir}. "
            f"Found: {list(generated_dir.iterdir()) if generated_dir.exists() else '(dir missing)'}"
        )

    async def test_generated_file_content_is_valid_python(self, tmp_path: Path) -> None:
        """The generated file contains syntactically valid Python code."""
        bus, builder, bootstrapper, bridge = await _setup_all(tmp_path)

        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=_build_payload(domain="health", agent_name="HealthAgent"),
                sender_id="GrowthOrchestrator",
            )
        )

        await asyncio.sleep(0.5)

        generated_dir = tmp_path / "generated"
        py_files = [f for f in generated_dir.glob("*.py") if f.name != "__init__.py"]
        assert len(py_files) >= 1, "No generated file found"

        content = py_files[0].read_text(encoding="utf-8")
        # Should not raise SyntaxError
        ast.parse(content)

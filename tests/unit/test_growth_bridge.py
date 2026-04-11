"""
Unit Tests for GrowthBridge

Verifies the GrowthBridge behaviour in isolation (no full DevLoop execution):
- growth.build.requested → growth.loop.started is published
- Missing required payload fields → no loop started, no growth.loop.started
- growth.loop.started payload contains run_id, need_id, domain, goal
- GrowthBridge._active_runs is cleared after loop completes
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.growth.growth_bridge import GrowthBridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_payload(
    need_id: str = "need-001",
    domain: str = "calendar",
    need_description: str = "schedule reminders",
) -> dict:
    return {
        "need_id": need_id,
        "domain": domain,
        "need_description": need_description,
        "gate_verdict": "PASS",
        "gate_total_score": 0.85,
        "agent_spec_template": {
            "name": "CalendarAgent",
            "description": need_description,
        },
    }


def _collect(bus: MessageBus, topic: str) -> List[Message]:
    collected: List[Message] = []

    async def _cb(msg: Message) -> None:
        collected.append(msg)

    bus.subscribe(topic, f"__collector_{topic}__", _cb)
    return collected


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGrowthBridgeLoopStarted:
    async def test_build_requested_publishes_loop_started(self, tmp_path: Path) -> None:
        """growth.build.requested → growth.loop.started is published."""
        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)
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
        # Allow any spawned tasks to progress
        await asyncio.sleep(0)

        assert len(started) == 1, "Expected exactly one growth.loop.started message"

    async def test_missing_need_description_no_loop_started(self, tmp_path: Path) -> None:
        """Missing need_description → no loop started, no growth.loop.started."""
        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)
        started: List[Message] = _collect(bus, "growth.loop.started")

        await bridge.initialize()
        await bridge.start()

        payload = _valid_payload()
        payload["need_description"] = ""  # missing

        await bus.publish(
            Message(topic="growth.build.requested", payload=payload, sender_id="test")
        )
        await asyncio.sleep(0)

        assert len(started) == 0

    async def test_missing_need_id_no_loop_started(self, tmp_path: Path) -> None:
        """Missing need_id → no loop started, no growth.loop.started."""
        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)
        started: List[Message] = _collect(bus, "growth.loop.started")

        await bridge.initialize()
        await bridge.start()

        payload = _valid_payload()
        payload["need_id"] = ""

        await bus.publish(
            Message(topic="growth.build.requested", payload=payload, sender_id="test")
        )
        await asyncio.sleep(0)

        assert len(started) == 0

    async def test_missing_domain_no_loop_started(self, tmp_path: Path) -> None:
        """Missing domain → no loop started, no growth.loop.started."""
        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)
        started: List[Message] = _collect(bus, "growth.loop.started")

        await bridge.initialize()
        await bridge.start()

        payload = _valid_payload()
        payload["domain"] = ""

        await bus.publish(
            Message(topic="growth.build.requested", payload=payload, sender_id="test")
        )
        await asyncio.sleep(0)

        assert len(started) == 0


class TestGrowthBridgeLoopStartedPayload:
    async def test_loop_started_payload_contains_run_id(self, tmp_path: Path) -> None:
        """growth.loop.started payload contains run_id."""
        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)
        started: List[Message] = _collect(bus, "growth.loop.started")

        await bridge.initialize()
        await bridge.start()

        await bus.publish(
            Message(topic="growth.build.requested", payload=_valid_payload(), sender_id="test")
        )
        await asyncio.sleep(0)

        assert started[0].payload.get("run_id"), "run_id should be present and non-empty"

    async def test_loop_started_payload_contains_need_id(self, tmp_path: Path) -> None:
        """growth.loop.started payload contains need_id."""
        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)
        started: List[Message] = _collect(bus, "growth.loop.started")

        await bridge.initialize()
        await bridge.start()

        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=_valid_payload(need_id="need-xyz"),
                sender_id="test",
            )
        )
        await asyncio.sleep(0)

        assert started[0].payload["need_id"] == "need-xyz"

    async def test_loop_started_payload_contains_domain(self, tmp_path: Path) -> None:
        """growth.loop.started payload contains domain."""
        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)
        started: List[Message] = _collect(bus, "growth.loop.started")

        await bridge.initialize()
        await bridge.start()

        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=_valid_payload(domain="finance"),
                sender_id="test",
            )
        )
        await asyncio.sleep(0)

        assert started[0].payload["domain"] == "finance"

    async def test_loop_started_payload_contains_goal(self, tmp_path: Path) -> None:
        """growth.loop.started payload contains goal derived from need_description and domain."""
        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)
        started: List[Message] = _collect(bus, "growth.loop.started")

        await bridge.initialize()
        await bridge.start()

        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=_valid_payload(need_description="track expenses", domain="finance"),
                sender_id="test",
            )
        )
        await asyncio.sleep(0)

        goal: str = started[0].payload.get("goal", "")
        assert "track expenses" in goal
        assert "finance" in goal


class TestGrowthBridgeActiveRunsCleanup:
    async def test_active_runs_cleared_after_loop_completed(self, tmp_path: Path) -> None:
        """_active_runs is cleared when dev.loop.completed fires for the run."""
        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)
        started: List[Message] = _collect(bus, "growth.loop.started")

        await bridge.initialize()
        await bridge.start()

        await bus.publish(
            Message(topic="growth.build.requested", payload=_valid_payload(), sender_id="test")
        )
        await asyncio.sleep(0)

        # Grab the run_id that was assigned
        assert len(started) == 1
        run_id: str = started[0].payload["run_id"]
        assert run_id in bridge._active_runs

        # Simulate the DevLoop completing for this run
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload={"summary": "done"},
                sender_id="DevLoopOrchestrator",
                metadata={"run_id": run_id},
            )
        )
        # Give the one-shot handler time to run
        await asyncio.sleep(0.05)

        assert run_id not in bridge._active_runs

    async def test_enriched_dev_loop_completed_published(self, tmp_path: Path) -> None:
        """GrowthBridge re-publishes dev.loop.completed with agent_name, agent_id, domain."""
        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)
        started: List[Message] = _collect(bus, "growth.loop.started")
        loop_completed: List[Message] = _collect(bus, "dev.loop.completed")

        await bridge.initialize()
        await bridge.start()

        await bus.publish(
            Message(
                topic="growth.build.requested",
                payload=_valid_payload(domain="health", need_description="blood pressure tracking"),
                sender_id="test",
            )
        )
        await asyncio.sleep(0)

        run_id: str = started[0].payload["run_id"]

        # Simulate DevLoopOrchestrator completing
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload={"summary": "Dev loop completed successfully."},
                sender_id="DevLoopOrchestrator",
                metadata={"run_id": run_id},
            )
        )
        await asyncio.sleep(0.05)

        # There should be TWO dev.loop.completed messages:
        # 1) the original from DevLoopOrchestrator (no agent_name)
        # 2) the enriched one from GrowthBridge
        enriched = [m for m in loop_completed if m.payload.get("agent_name")]
        assert len(enriched) == 1
        assert enriched[0].payload["agent_id"] == run_id
        assert enriched[0].payload["domain"] == "health"


class TestGrowthBridgeRunDevloopContext:
    """Unit tests for _run_devloop() context propagation."""

    async def test_run_devloop_passes_context_to_orchestrator(self, tmp_path: Path) -> None:
        """_run_devloop() passes agent_spec_template, domain, need_id from _active_runs to orchestrator."""
        from unittest.mock import AsyncMock, MagicMock

        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)

        run_id = "run-ctx-001"
        goal = "build a test agent"
        agent_spec_template = {"name": "TestAgent", "topics": ["test.topic"]}
        bridge._active_runs[run_id] = {
            "agent_spec_template": agent_spec_template,
            "domain": "test-domain",
            "need_id": "need-ctx-001",
        }

        orchestrator = MagicMock()
        orchestrator.run = AsyncMock()

        await bridge._run_devloop(run_id, goal, orchestrator)

        orchestrator.run.assert_awaited_once()
        call_kwargs = orchestrator.run.call_args.kwargs
        assert call_kwargs["run_id"] == run_id
        assert call_kwargs["goal"] == goal
        context = call_kwargs["context"]
        assert context["agent_spec_template"] == agent_spec_template
        assert context["domain"] == "test-domain"
        assert context["need_id"] == "need-ctx-001"

    async def test_run_devloop_context_does_not_mutate_active_runs(self, tmp_path: Path) -> None:
        """_run_devloop() builds a new context dict and does not mutate _active_runs."""
        from unittest.mock import AsyncMock, MagicMock

        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)

        run_id = "run-ctx-002"
        original_template = {"name": "ImmutableAgent"}
        bridge._active_runs[run_id] = {
            "agent_spec_template": original_template,
            "domain": "immutable",
            "need_id": "need-imm-001",
        }

        orchestrator = MagicMock()
        orchestrator.run = AsyncMock()

        await bridge._run_devloop(run_id, "immutable goal", orchestrator)

        # original_template must not have been mutated
        assert original_template == {"name": "ImmutableAgent"}

    async def test_run_devloop_empty_active_runs_uses_defaults(self, tmp_path: Path) -> None:
        """_run_devloop() uses empty defaults when run_id not in _active_runs."""
        from unittest.mock import AsyncMock, MagicMock

        bus = MessageBus()
        bridge = GrowthBridge(message_bus=bus, journal_base_path=tmp_path)

        orchestrator = MagicMock()
        orchestrator.run = AsyncMock()

        await bridge._run_devloop("missing-run-id", "some goal", orchestrator)

        call_kwargs = orchestrator.run.call_args.kwargs
        context = call_kwargs["context"]
        assert context["agent_spec_template"] == {}
        assert context["domain"] == ""
        assert context["need_id"] == ""

"""
Unit Tests — AgentBootstrapper Phase 9 (agent loading + starting)

Verifies:
- AgentBootstrapper starts a real agent when dev.loop.completed is received
  with a matching agent_name and a valid .py file in generated_agents_path
- Second bootstrap of the same name stops the old instance
- Import error (broken generated code) → agent.bootstrap_failed, no crash
- _active_agents contains the running instance after successful bootstrap
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import List

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.communication.topic_registry import TopicRegistry
from genus.core.agent import AgentState
from genus.growth.bootstrapper import AgentBootstrapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bus() -> MessageBus:
    return MessageBus()


def _make_registry() -> TopicRegistry:
    return TopicRegistry()


def _collect(bus: MessageBus, topic: str) -> List[Message]:
    collected: List[Message] = []

    async def _handler(msg: Message) -> None:
        collected.append(msg)

    bus.subscribe(topic, f"__collector_{topic}__", _handler)
    return collected


def _payload(
    agent_name: str = "DemoAgent",
    agent_id: str = "agent-demo-001",
    domain: str = "test",
    topics: list = None,
) -> dict:
    p: dict = {"agent_name": agent_name, "agent_id": agent_id, "domain": domain}
    if topics is not None:
        p["topics"] = topics
    return p


def _write_valid_agent(path: Path, class_name: str, domain: str = "test") -> None:
    """Write a minimal, syntactically valid generated agent to *path*."""
    code = textwrap.dedent(
        f"""\
        from __future__ import annotations
        from typing import Optional
        from genus.communication.message_bus import Message, MessageBus
        from genus.core.agent import Agent, AgentState

        class {class_name}(Agent):
            def __init__(
                self,
                message_bus: MessageBus,
                agent_id: Optional[str] = None,
                name: Optional[str] = None,
            ) -> None:
                super().__init__(agent_id=agent_id, name=name or "{class_name}")
                self._bus = message_bus

            async def initialize(self) -> None:
                self._transition_state(AgentState.INITIALIZED)

            async def start(self) -> None:
                self._transition_state(AgentState.RUNNING)

            async def stop(self) -> None:
                self._bus.unsubscribe_all(self.id)
                self._transition_state(AgentState.STOPPED)

            async def process_message(self, message: Message) -> None:
                pass
        """
    )
    path.write_text(code, encoding="utf-8")


def _write_broken_agent(path: Path) -> None:
    """Write a Python file that causes a SyntaxError on import."""
    path.write_text("this is not valid python !!!", encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests — successful load and start
# ---------------------------------------------------------------------------

class TestAgentBootstrapperStart:
    async def test_bootstrapper_starts_real_agent(self, tmp_path: Path) -> None:
        """dev.loop.completed → agent class loaded and started (RUNNING)."""
        agent_file = tmp_path / "demo_agent.py"
        _write_valid_agent(agent_file, "DemoAgent")

        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=registry,
            generated_agents_path=tmp_path,
        )
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")
        await bootstrapper.initialize()

        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="DemoAgent", agent_id="demo-001"),
                sender_id="test",
            )
        )

        assert len(bootstrapped) == 1
        entry = bootstrapper._active_agents.get("DemoAgent")
        assert entry is not None
        assert entry["instance"] is not None
        assert entry["instance"].state == AgentState.RUNNING

    async def test_active_agents_contains_instance_after_bootstrap(
        self, tmp_path: Path
    ) -> None:
        """_active_agents stores agent_id and domain in addition to instance."""
        agent_file = tmp_path / "widget_agent.py"
        _write_valid_agent(agent_file, "WidgetAgent", domain="widgets")

        bus = _make_bus()
        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="WidgetAgent", agent_id="wid-42", domain="widgets"),
                sender_id="test",
            )
        )

        entry = bootstrapper._active_agents["WidgetAgent"]
        assert entry["agent_id"] == "wid-42"
        assert entry["domain"] == "widgets"
        assert entry["instance"] is not None

    async def test_no_class_found_still_publishes_bootstrapped(
        self, tmp_path: Path
    ) -> None:
        """When no .py file exists, agent.bootstrapped is still published (backward compat)."""
        bus = _make_bus()
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")
        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,  # empty dir
        )
        await bootstrapper.initialize()
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="GhostAgent"),
                sender_id="test",
            )
        )

        assert len(bootstrapped) == 1
        entry = bootstrapper._active_agents.get("GhostAgent")
        assert entry is not None
        assert entry["instance"] is None


# ---------------------------------------------------------------------------
# Tests — second bootstrap stops old instance
# ---------------------------------------------------------------------------

class TestAgentBootstrapperReplacement:
    async def test_second_bootstrap_stops_old_instance(self, tmp_path: Path) -> None:
        """Second bootstrap of same name stops old instance before starting new one."""
        agent_file = tmp_path / "relay_agent.py"
        _write_valid_agent(agent_file, "RelayAgent")

        bus = _make_bus()
        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()

        # First bootstrap
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="RelayAgent", agent_id="relay-v1"),
                sender_id="test",
            )
        )
        first_instance = bootstrapper._active_agents["RelayAgent"]["instance"]
        assert first_instance is not None
        assert first_instance.state == AgentState.RUNNING

        # Second bootstrap
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="RelayAgent", agent_id="relay-v2"),
                sender_id="test",
            )
        )

        assert first_instance.state == AgentState.STOPPED
        second_instance = bootstrapper._active_agents["RelayAgent"]["instance"]
        assert second_instance is not None
        assert second_instance is not first_instance
        assert second_instance.state == AgentState.RUNNING

    async def test_second_bootstrap_publishes_deprecated(self, tmp_path: Path) -> None:
        """Second bootstrap publishes agent.deprecated with correct IDs."""
        agent_file = tmp_path / "relay_agent.py"
        _write_valid_agent(agent_file, "RelayAgent")

        bus = _make_bus()
        deprecated: List[Message] = _collect(bus, "agent.deprecated")
        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()

        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="RelayAgent", agent_id="relay-v1"),
                sender_id="test",
            )
        )
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="RelayAgent", agent_id="relay-v2"),
                sender_id="test",
            )
        )

        assert len(deprecated) == 1
        assert deprecated[0].payload["previous_agent_id"] == "relay-v1"
        assert deprecated[0].payload["replaced_by"] == "relay-v2"


# ---------------------------------------------------------------------------
# Tests — import error handling
# ---------------------------------------------------------------------------

class TestAgentBootstrapperImportError:
    async def test_broken_module_publishes_bootstrap_failed(
        self, tmp_path: Path
    ) -> None:
        """A broken generated .py file → agent.bootstrap_failed, no crash."""
        broken_file = tmp_path / "broken_agent.py"
        _write_broken_agent(broken_file)

        bus = _make_bus()
        failed: List[Message] = _collect(bus, "agent.bootstrap_failed")
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")
        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()

        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="BrokenAgent", agent_id="broken-001"),
                sender_id="test",
            )
        )

        assert len(failed) == 1, "Expected agent.bootstrap_failed event"
        assert failed[0].payload["agent_name"] == "BrokenAgent"
        assert len(bootstrapped) == 0, "agent.bootstrapped must NOT be published on import error"

    async def test_broken_module_does_not_update_active_agents(
        self, tmp_path: Path
    ) -> None:
        """_active_agents is not updated when import fails."""
        broken_file = tmp_path / "broken_agent.py"
        _write_broken_agent(broken_file)

        bus = _make_bus()
        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()

        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="BrokenAgent"),
                sender_id="test",
            )
        )

        assert "BrokenAgent" not in bootstrapper._active_agents

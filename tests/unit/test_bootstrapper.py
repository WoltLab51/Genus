"""
Tests for genus.growth.bootstrapper (AgentBootstrapper)

Verifies:
- dev.loop.completed → agent.bootstrapped published
- Payload contains agent_name, agent_id, bootstrapped_at, topics_registered
- New agent with same name → agent.deprecated + agent.bootstrapped published
- Topics from payload are registered in TopicRegistry
- agent.deprecated payload contains previous_agent_id and replaced_by
"""

from typing import List

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.communication.topic_registry import TopicEntry, TopicRegistry
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

    def _handler(msg: Message) -> None:
        collected.append(msg)

    bus.subscribe(topic, f"__collector_{topic}__", _handler)
    return collected


def _payload(
    agent_name: str = "TestAgent",
    agent_id: str = "agent-001",
    domain: str = "system",
    topics: list = None,
) -> dict:
    p: dict = {"agent_name": agent_name, "agent_id": agent_id, "domain": domain}
    if topics is not None:
        p["topics"] = topics
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAgentBootstrapperBasic:
    async def test_dev_loop_completed_publishes_agent_bootstrapped(self):
        """dev.loop.completed triggers agent.bootstrapped."""
        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed", payload=_payload(), sender_id="test",
        ))
        assert len(bootstrapped) == 1

    async def test_bootstrapped_payload_contains_agent_name(self):
        """agent.bootstrapped payload has agent_name."""
        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(agent_name="FamilyAgent", agent_id="fam-001"),
            sender_id="test",
        ))
        assert bootstrapped[0].payload["agent_name"] == "FamilyAgent"

    async def test_bootstrapped_payload_contains_agent_id(self):
        """agent.bootstrapped payload has agent_id."""
        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(agent_id="uid-42"),
            sender_id="test",
        ))
        assert bootstrapped[0].payload["agent_id"] == "uid-42"

    async def test_bootstrapped_payload_contains_bootstrapped_at(self):
        """agent.bootstrapped payload has bootstrapped_at ISO 8601 timestamp."""
        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed", payload=_payload(), sender_id="test",
        ))
        assert "T" in bootstrapped[0].payload["bootstrapped_at"]  # ISO 8601

    async def test_bootstrapped_payload_contains_topics_registered(self):
        """agent.bootstrapped payload has topics_registered list."""
        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(topics=["family.calendar.updated"]),
            sender_id="test",
        ))
        assert bootstrapped[0].payload["topics_registered"] == ["family.calendar.updated"]


class TestAgentBootstrapperTopicRegistry:
    async def test_topics_registered_in_registry(self):
        """Topics from the payload are registered in the TopicRegistry."""
        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(agent_name="CalendarAgent", topics=["family.calendar.event.created"]),
            sender_id="test",
        ))
        assert registry.is_registered("family.calendar.event.created")

    async def test_already_registered_topic_not_duplicated(self):
        """A topic already in the registry is not registered again (no ValueError)."""
        bus = _make_bus()
        registry = _make_registry()
        registry.register(TopicEntry(
            topic="existing.topic",
            owner="OldOwner",
            direction="publish",
            domain="system",
            description="Pre-registered topic.",
        ))
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(topics=["existing.topic"]),
            sender_id="test",
        ))
        assert registry.is_registered("existing.topic")

    async def test_no_topics_in_payload(self):
        """dev.loop.completed without topics → topics_registered is empty list."""
        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed", payload=_payload(), sender_id="test",
        ))
        assert bootstrapped[0].payload["topics_registered"] == []


class TestAgentBootstrapperDeprecation:
    async def test_second_agent_same_name_triggers_deprecated(self):
        """Second bootstrap with same name emits agent.deprecated."""
        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        deprecated: List[Message] = _collect(bus, "agent.deprecated")
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(agent_name="SystemAgent", agent_id="sys-001"),
            sender_id="test",
        ))
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(agent_name="SystemAgent", agent_id="sys-002"),
            sender_id="test",
        ))
        assert len(deprecated) == 1

    async def test_deprecated_payload_has_previous_agent_id(self):
        """agent.deprecated payload contains previous_agent_id."""
        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        deprecated: List[Message] = _collect(bus, "agent.deprecated")
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(agent_name="SystemAgent", agent_id="sys-001"),
            sender_id="test",
        ))
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(agent_name="SystemAgent", agent_id="sys-002"),
            sender_id="test",
        ))
        assert deprecated[0].payload["previous_agent_id"] == "sys-001"

    async def test_deprecated_payload_has_replaced_by(self):
        """agent.deprecated payload contains replaced_by (new agent_id)."""
        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        deprecated: List[Message] = _collect(bus, "agent.deprecated")
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(agent_name="SystemAgent", agent_id="sys-001"),
            sender_id="test",
        ))
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(agent_name="SystemAgent", agent_id="sys-002"),
            sender_id="test",
        ))
        assert deprecated[0].payload["replaced_by"] == "sys-002"

    async def test_both_deprecated_and_bootstrapped_published_on_replacement(self):
        """Replacement emits both agent.deprecated and agent.bootstrapped."""
        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        deprecated: List[Message] = _collect(bus, "agent.deprecated")
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(agent_name="SystemAgent", agent_id="sys-001"),
            sender_id="test",
        ))
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(agent_name="SystemAgent", agent_id="sys-002"),
            sender_id="test",
        ))
        assert len(deprecated) == 1
        assert len(bootstrapped) == 2

    async def test_first_bootstrap_no_deprecated_event(self):
        """First bootstrap of a new agent name emits no agent.deprecated."""
        bus = _make_bus()
        registry = _make_registry()
        bootstrapper = AgentBootstrapper(message_bus=bus, topic_registry=registry)
        deprecated: List[Message] = _collect(bus, "agent.deprecated")
        await bootstrapper.initialize()
        await bus.publish(Message(
            topic="dev.loop.completed",
            payload=_payload(agent_name="BrandNewAgent", agent_id="new-001"),
            sender_id="test",
        ))
        assert len(deprecated) == 0

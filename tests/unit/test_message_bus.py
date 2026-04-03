"""Unit tests for MessageBus."""
import pytest
from genus.communication import MessageBus
from genus.core import Message


async def test_message_bus_creation():
    """Test creating a message bus."""
    bus = MessageBus()
    assert bus is not None
    assert bus.get_topics() == []


async def test_message_bus_subscribe():
    """Test subscribing to a topic."""
    bus = MessageBus()
    received = []

    async def handler(message):
        received.append(message)

    bus.subscribe("test.topic", handler)
    assert "test.topic" in bus.get_topics()


async def test_message_bus_publish():
    """Test publishing messages."""
    bus = MessageBus()
    received = []

    async def handler(message):
        received.append(message)

    bus.subscribe("test.topic", handler)

    message = Message(topic="test.topic", payload={"data": "test"})
    await bus.publish(message)

    assert len(received) == 1
    assert received[0].payload["data"] == "test"


async def test_message_bus_multiple_subscribers():
    """Test multiple subscribers to the same topic."""
    bus = MessageBus()
    received1 = []
    received2 = []

    async def handler1(message):
        received1.append(message)

    async def handler2(message):
        received2.append(message)

    bus.subscribe("test.topic", handler1)
    bus.subscribe("test.topic", handler2)

    message = Message(topic="test.topic", payload={"data": "test"})
    await bus.publish(message)

    assert len(received1) == 1
    assert len(received2) == 1


async def test_message_bus_unsubscribe():
    """Test unsubscribing from a topic."""
    bus = MessageBus()
    received = []

    async def handler(message):
        received.append(message)

    bus.subscribe("test.topic", handler)
    bus.unsubscribe("test.topic", handler)

    message = Message(topic="test.topic", payload={"data": "test"})
    await bus.publish(message)

    assert len(received) == 0
    assert "test.topic" not in bus.get_topics()


async def test_message_creation():
    """Test creating messages."""
    message = Message(topic="test.topic", payload={"key": "value"}, sender="sender-1")

    assert message.topic == "test.topic"
    assert message.payload["key"] == "value"
    assert message.sender == "sender-1"
    assert message.message_id is not None
    assert message.timestamp is not None


async def test_message_bus_topic_isolation():
    """Test that topics are isolated."""
    bus = MessageBus()
    received1 = []
    received2 = []

    async def handler1(message):
        received1.append(message)

    async def handler2(message):
        received2.append(message)

    bus.subscribe("topic1", handler1)
    bus.subscribe("topic2", handler2)

    message1 = Message(topic="topic1", payload={"data": "test1"})
    message2 = Message(topic="topic2", payload={"data": "test2"})

    await bus.publish(message1)
    await bus.publish(message2)

    assert len(received1) == 1
    assert len(received2) == 1
    assert received1[0].payload["data"] == "test1"
    assert received2[0].payload["data"] == "test2"

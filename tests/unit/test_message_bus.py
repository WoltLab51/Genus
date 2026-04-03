"""Unit tests for MessageBus."""
import pytest
from genus.communication import MessageBus, Message


async def test_message_bus_publish_subscribe():
    """Test basic publish-subscribe functionality."""
    bus = MessageBus()
    received_messages = []

    async def handler(message: Message):
        received_messages.append(message)

    bus.subscribe("test.topic", handler)
    await bus.publish("test.topic", {"key": "value"}, sender="test")

    assert len(received_messages) == 1
    assert received_messages[0].topic == "test.topic"
    assert received_messages[0].data == {"key": "value"}
    assert received_messages[0].sender == "test"


async def test_message_bus_multiple_subscribers():
    """Test multiple subscribers receive the same message."""
    bus = MessageBus()
    received_1 = []
    received_2 = []

    async def handler1(message: Message):
        received_1.append(message)

    async def handler2(message: Message):
        received_2.append(message)

    bus.subscribe("topic", handler1)
    bus.subscribe("topic", handler2)
    await bus.publish("topic", {"data": 1})

    assert len(received_1) == 1
    assert len(received_2) == 1


async def test_message_bus_unsubscribe():
    """Test unsubscribe functionality."""
    bus = MessageBus()
    received = []

    async def handler(message: Message):
        received.append(message)

    bus.subscribe("topic", handler)
    await bus.publish("topic", {"msg": 1})

    bus.unsubscribe("topic", handler)
    await bus.publish("topic", {"msg": 2})

    assert len(received) == 1
    assert received[0].data == {"msg": 1}


async def test_message_bus_history():
    """Test message history tracking."""
    bus = MessageBus()

    await bus.publish("topic1", {"data": 1})
    await bus.publish("topic2", {"data": 2})
    await bus.publish("topic1", {"data": 3})

    all_history = bus.get_message_history()
    assert len(all_history) == 3

    topic1_history = bus.get_message_history(topic="topic1")
    assert len(topic1_history) == 2


async def test_message_bus_history_limit():
    """Test message history limit."""
    bus = MessageBus()

    for i in range(10):
        await bus.publish("topic", {"count": i})

    history = bus.get_message_history(limit=5)
    assert len(history) == 5
    assert history[-1].data == {"count": 9}


async def test_message_bus_clear_history():
    """Test clearing message history."""
    bus = MessageBus()

    await bus.publish("topic", {"data": 1})
    assert len(bus.get_message_history()) == 1

    bus.clear_history()
    assert len(bus.get_message_history()) == 0

"""
Unit tests for MessageBus.
"""
import pytest
from genus.communication.message_bus import MessageBus, Message


async def test_message_bus_publish_subscribe():
    """Test basic publish-subscribe functionality."""
    bus = MessageBus()
    received_messages = []

    async def callback(message: Message):
        received_messages.append(message)

    # Subscribe
    bus.subscribe("test.topic", callback)

    # Publish
    await bus.publish("test.topic", {"key": "value"}, "sender")

    # Verify
    assert len(received_messages) == 1
    assert received_messages[0].topic == "test.topic"
    assert received_messages[0].data == {"key": "value"}
    assert received_messages[0].sender == "sender"


async def test_message_bus_multiple_subscribers():
    """Test multiple subscribers to the same topic."""
    bus = MessageBus()
    received_by_sub1 = []
    received_by_sub2 = []

    async def callback1(message: Message):
        received_by_sub1.append(message)

    async def callback2(message: Message):
        received_by_sub2.append(message)

    bus.subscribe("test.topic", callback1)
    bus.subscribe("test.topic", callback2)

    await bus.publish("test.topic", "data", "sender")

    assert len(received_by_sub1) == 1
    assert len(received_by_sub2) == 1


async def test_message_bus_unsubscribe():
    """Test unsubscribe functionality."""
    bus = MessageBus()
    received = []

    async def callback(message: Message):
        received.append(message)

    bus.subscribe("test.topic", callback)
    await bus.publish("test.topic", "data1", "sender")

    bus.unsubscribe("test.topic", callback)
    await bus.publish("test.topic", "data2", "sender")

    # Only first message should be received
    assert len(received) == 1
    assert received[0].data == "data1"


async def test_message_bus_history():
    """Test message history tracking."""
    bus = MessageBus()

    await bus.publish("topic1", "data1", "sender1")
    await bus.publish("topic2", "data2", "sender2")

    history = bus.get_message_history()
    assert len(history) == 2
    assert history[0]["topic"] == "topic1"
    assert history[1]["topic"] == "topic2"

    bus.clear_history()
    assert len(bus.get_message_history()) == 0

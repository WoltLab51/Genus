"""Unit tests for MessageBus."""

import pytest

from genus.communication.message_bus import MessageBus


async def test_message_bus_subscribe():
    """Test subscribing to topics."""
    bus = MessageBus()
    called = []

    async def callback(topic, message):
        called.append((topic, message))

    bus.subscribe("test.topic", callback)

    await bus.publish("test.topic", {"data": "test"})

    assert len(called) == 1
    assert called[0] == ("test.topic", {"data": "test"})


async def test_message_bus_unsubscribe():
    """Test unsubscribing from topics."""
    bus = MessageBus()
    called = []

    async def callback(topic, message):
        called.append((topic, message))

    bus.subscribe("test.topic", callback)
    bus.unsubscribe("test.topic", callback)

    await bus.publish("test.topic", {"data": "test"})

    assert len(called) == 0


async def test_message_bus_multiple_subscribers():
    """Test multiple subscribers receive messages."""
    bus = MessageBus()
    called1 = []
    called2 = []

    async def callback1(topic, message):
        called1.append((topic, message))

    async def callback2(topic, message):
        called2.append((topic, message))

    bus.subscribe("test.topic", callback1)
    bus.subscribe("test.topic", callback2)

    await bus.publish("test.topic", {"data": "test"})

    assert len(called1) == 1
    assert len(called2) == 1


async def test_message_bus_history():
    """Test message history tracking."""
    bus = MessageBus()

    await bus.publish("topic1", {"data": "message1"})
    await bus.publish("topic2", {"data": "message2"})

    history = bus.get_history()

    assert len(history) == 2
    assert history[0]["topic"] == "topic1"
    assert history[0]["message"] == {"data": "message1"}
    assert history[1]["topic"] == "topic2"
    assert history[1]["message"] == {"data": "message2"}


async def test_message_bus_clear_history():
    """Test clearing message history."""
    bus = MessageBus()

    await bus.publish("topic1", {"data": "message1"})
    await bus.publish("topic2", {"data": "message2"})

    bus.clear_history()

    history = bus.get_history()
    assert len(history) == 0


async def test_message_bus_error_handling():
    """Test error handling in callbacks."""
    bus = MessageBus()
    called_good = []

    async def bad_callback(topic, message):
        raise ValueError("Test error")

    async def good_callback(topic, message):
        called_good.append((topic, message))

    bus.subscribe("test.topic", bad_callback)
    bus.subscribe("test.topic", good_callback)

    # Should not raise, error is logged
    await bus.publish("test.topic", {"data": "test"})

    # Good callback should still be called
    assert len(called_good) == 1

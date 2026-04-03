"""
Test Message Bus

Tests for message bus communication system.
"""

import pytest
import asyncio
from genus.communication.message_bus import MessageBus, Message, MessagePriority


class TestMessageBus:
    """Test suite for MessageBus."""

    def test_message_creation(self):
        """Test message can be created."""
        msg = Message(
            topic="test.topic",
            payload={"data": "test"},
            sender_id="agent-1"
        )
        assert msg.topic == "test.topic"
        assert msg.payload["data"] == "test"
        assert msg.sender_id == "agent-1"
        assert msg.priority == MessagePriority.NORMAL
        assert msg.message_id is not None
        assert msg.timestamp is not None

    def test_message_bus_creation(self):
        """Test message bus can be created."""
        bus = MessageBus(max_queue_size=100)
        assert bus is not None
        assert len(bus.get_topics()) == 0

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self):
        """Test subscribing to topics and receiving messages."""
        bus = MessageBus()
        received_messages = []

        async def callback(message: Message):
            received_messages.append(message)

        # Subscribe
        bus.subscribe("test.topic", "subscriber-1", callback)

        # Publish
        msg = Message(
            topic="test.topic",
            payload={"data": "hello"},
            sender_id="publisher-1"
        )
        await bus.publish(msg)

        # Give time for async delivery
        await asyncio.sleep(0.1)

        # Verify
        assert len(received_messages) == 1
        assert received_messages[0].payload["data"] == "hello"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        """Test multiple subscribers receive messages."""
        bus = MessageBus()
        received_1 = []
        received_2 = []

        async def callback1(message: Message):
            received_1.append(message)

        async def callback2(message: Message):
            received_2.append(message)

        # Subscribe multiple
        bus.subscribe("test.topic", "sub-1", callback1)
        bus.subscribe("test.topic", "sub-2", callback2)

        # Publish
        msg = Message(
            topic="test.topic",
            payload={"data": "broadcast"},
            sender_id="publisher"
        )
        await bus.publish(msg)
        await asyncio.sleep(0.1)

        # Both should receive
        assert len(received_1) == 1
        assert len(received_2) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """Test unsubscribing from topics."""
        bus = MessageBus()
        received = []

        async def callback(message: Message):
            received.append(message)

        # Subscribe and publish
        bus.subscribe("test.topic", "sub-1", callback)
        msg1 = Message(topic="test.topic", payload={"n": 1}, sender_id="pub")
        await bus.publish(msg1)
        await asyncio.sleep(0.1)

        # Unsubscribe
        bus.unsubscribe("test.topic", "sub-1")

        # Publish again
        msg2 = Message(topic="test.topic", payload={"n": 2}, sender_id="pub")
        await bus.publish(msg2)
        await asyncio.sleep(0.1)

        # Should only have received first message
        assert len(received) == 1

    def test_message_history(self):
        """Test message history tracking."""
        bus = MessageBus()
        assert len(bus.get_message_history()) == 0

    def test_topic_listing(self):
        """Test getting list of topics."""
        bus = MessageBus()

        async def dummy_callback(msg):
            pass

        bus.subscribe("topic.a", "sub-1", dummy_callback)
        bus.subscribe("topic.b", "sub-2", dummy_callback)

        topics = bus.get_topics()
        assert "topic.a" in topics
        assert "topic.b" in topics
        assert len(topics) == 2

    def test_subscriber_count(self):
        """Test getting subscriber count for topics."""
        bus = MessageBus()

        async def dummy_callback(msg):
            pass

        assert bus.get_subscriber_count("test.topic") == 0

        bus.subscribe("test.topic", "sub-1", dummy_callback)
        assert bus.get_subscriber_count("test.topic") == 1

        bus.subscribe("test.topic", "sub-2", dummy_callback)
        assert bus.get_subscriber_count("test.topic") == 2

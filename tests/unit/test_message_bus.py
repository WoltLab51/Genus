"""Unit tests for MessageBus."""

import pytest
from genus.communication.message_bus import MessageBus, Message
from genus.core.system_state import SystemStateTracker


class TestMessageBus:
    """Test message bus functionality."""

    async def test_subscribe_and_publish(self):
        """Test subscribing to and publishing messages."""
        bus = MessageBus()
        received_messages = []

        async def handler(message: Message):
            received_messages.append(message)

        bus.subscribe("test_topic", handler)
        await bus.publish("test_topic", {"key": "value"})

        assert len(received_messages) == 1
        assert received_messages[0].topic == "test_topic"
        assert received_messages[0].data == {"key": "value"}

    async def test_multiple_subscribers(self):
        """Test multiple subscribers receive messages."""
        bus = MessageBus()
        received1 = []
        received2 = []

        async def handler1(message: Message):
            received1.append(message)

        async def handler2(message: Message):
            received2.append(message)

        bus.subscribe("test_topic", handler1)
        bus.subscribe("test_topic", handler2)
        await bus.publish("test_topic", "data")

        assert len(received1) == 1
        assert len(received2) == 1

    async def test_unsubscribe(self):
        """Test unsubscribing from topics."""
        bus = MessageBus()
        received = []

        async def handler(message: Message):
            received.append(message)

        bus.subscribe("test_topic", handler)
        await bus.publish("test_topic", "data1")

        bus.unsubscribe("test_topic", handler)
        await bus.publish("test_topic", "data2")

        assert len(received) == 1

    async def test_message_history(self):
        """Test message history tracking."""
        bus = MessageBus()
        await bus.publish("topic1", "data1")
        await bus.publish("topic2", "data2")

        history = bus.get_message_history()
        assert len(history) == 2
        assert history[0].topic == "topic1"
        assert history[1].topic == "topic2"

    async def test_message_history_by_topic(self):
        """Test filtering message history by topic."""
        bus = MessageBus()
        await bus.publish("topic1", "data1")
        await bus.publish("topic2", "data2")
        await bus.publish("topic1", "data3")

        history = bus.get_message_history(topic="topic1")
        assert len(history) == 2
        assert all(m.topic == "topic1" for m in history)

    async def test_handler_error_reported_to_state_tracker(self):
        """Test that handler errors are reported to state tracker."""
        tracker = SystemStateTracker()
        bus = MessageBus(state_tracker=tracker)

        async def failing_handler(message: Message):
            raise ValueError("Handler error")

        bus.subscribe("test_topic", failing_handler)
        await bus.publish("test_topic", "data")

        # Error should be reported to state tracker
        report = tracker.get_health_report()
        assert len(report["recent_errors"]["message_bus"]) == 1

    async def test_get_stats(self):
        """Test getting message bus statistics."""
        bus = MessageBus()

        async def handler(message: Message):
            pass

        bus.subscribe("topic1", handler)
        bus.subscribe("topic2", handler)
        await bus.publish("topic1", "data")
        await bus.publish("topic1", "data")
        await bus.publish("topic2", "data")

        stats = bus.get_stats()
        assert stats["total_messages"] == 3
        assert "topic1" in stats["topics"]
        assert "topic2" in stats["topics"]
        assert stats["message_counts"]["topic1"] == 2
        assert stats["message_counts"]["topic2"] == 1

    async def test_message_source_tracking(self):
        """Test tracking message sources."""
        bus = MessageBus()
        await bus.publish("test_topic", "data", source="test_agent")

        history = bus.get_message_history()
        assert history[0].source == "test_agent"

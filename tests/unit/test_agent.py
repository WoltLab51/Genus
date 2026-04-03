"""Unit tests for core agent functionality."""
import pytest
from genus.core import Agent, Message
from genus.communication import MessageBus


class MockAgent(Agent):
    """Mock agent implementation for testing."""

    def __init__(self, agent_id: str, message_bus: MessageBus):
        super().__init__(agent_id, message_bus)
        self.received_messages = []

    async def handle_message(self, message: Message):
        """Store received messages for testing."""
        self.received_messages.append(message)


async def test_agent_creation():
    """Test creating an agent."""
    message_bus = MessageBus()
    agent = MockAgent("test-agent-1", message_bus)

    assert agent.agent_id == "test-agent-1"
    assert agent.message_bus == message_bus
    assert agent.subscriptions == []


async def test_agent_subscription():
    """Test agent subscribing to topics."""
    message_bus = MessageBus()
    agent = MockAgent("test-agent-1", message_bus)

    agent.subscribe("test.topic")

    assert "test.topic" in agent.subscriptions
    assert "test.topic" in message_bus.get_topics()


async def test_agent_message_handling():
    """Test agent receiving and handling messages."""
    message_bus = MessageBus()
    agent = MockAgent("test-agent-1", message_bus)

    agent.subscribe("test.topic")

    # Publish a message
    message = Message(topic="test.topic", payload={"data": "test"}, sender="sender-1")
    await message_bus.publish(message)

    # Verify agent received the message
    assert len(agent.received_messages) == 1
    assert agent.received_messages[0].topic == "test.topic"
    assert agent.received_messages[0].payload["data"] == "test"


async def test_agent_publishing():
    """Test agent publishing messages."""
    message_bus = MessageBus()
    agent1 = MockAgent("agent-1", message_bus)
    agent2 = MockAgent("agent-2", message_bus)

    agent2.subscribe("test.publish")

    # Agent1 publishes a message
    await agent1.publish("test.publish", {"info": "hello"})

    # Verify agent2 received it
    assert len(agent2.received_messages) == 1
    assert agent2.received_messages[0].payload["info"] == "hello"
    assert agent2.received_messages[0].sender == "agent-1"

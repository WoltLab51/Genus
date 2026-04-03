"""Unit tests for Agent base class."""

import pytest

from genus.core.agent import Agent, AgentState


class MockAgent(Agent):
    """Mock agent implementation for testing."""

    def __init__(self, name: str = "MockAgent"):
        super().__init__(name)
        self.initialized = False
        self.messages_handled = []

    async def initialize(self) -> None:
        """Initialize test agent."""
        self.initialized = True

    async def handle_message(self, topic: str, message: dict) -> None:
        """Handle test message."""
        self.messages_handled.append((topic, message))


async def test_agent_initial_state():
    """Test agent starts in IDLE state."""
    agent = MockAgent()
    assert agent.state == AgentState.IDLE
    assert agent.get_state() == AgentState.IDLE


async def test_agent_lifecycle():
    """Test agent lifecycle transitions."""
    agent = MockAgent()

    # Initialize
    await agent.initialize()
    assert agent.initialized is True
    assert agent.state == AgentState.IDLE

    # Start
    await agent.start()
    assert agent.state == AgentState.RUNNING

    # Stop
    await agent.stop()
    assert agent.state == AgentState.STOPPED


async def test_agent_handle_message():
    """Test agent can handle messages."""
    agent = MockAgent()
    await agent.initialize()
    await agent.start()

    message = {"data": "test"}
    await agent.handle_message("test.topic", message)

    assert len(agent.messages_handled) == 1
    assert agent.messages_handled[0] == ("test.topic", message)


async def test_agent_name():
    """Test agent has correct name."""
    agent = MockAgent("CustomName")
    assert agent.name == "CustomName"

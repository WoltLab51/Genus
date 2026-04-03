"""Unit tests for Agent base class."""
import pytest
from genus.core.agent import Agent, AgentState


class TestAgent(Agent):
    """Concrete agent implementation for testing."""

    def __init__(self, agent_id: str):
        super().__init__(agent_id)
        self.initialized_called = False
        self.cleanup_called = False

    async def initialize(self):
        self.initialized_called = True
        self.state = AgentState.INITIALIZED

    async def _cleanup(self):
        self.cleanup_called = True


async def test_agent_lifecycle():
    """Test agent follows correct lifecycle."""
    agent = TestAgent("test-agent")

    # Initial state
    assert agent.state == AgentState.CREATED
    assert not agent.initialized_called

    # Initialize
    await agent.initialize()
    assert agent.state == AgentState.INITIALIZED
    assert agent.initialized_called

    # Start
    await agent.start()
    assert agent.state == AgentState.RUNNING

    # Stop
    await agent.stop()
    assert agent.state == AgentState.STOPPED
    assert agent.cleanup_called


async def test_agent_cannot_start_before_initialize():
    """Test agent cannot start without initialization."""
    agent = TestAgent("test-agent")

    with pytest.raises(RuntimeError) as exc_info:
        await agent.start()

    assert "must be initialized" in str(exc_info.value)


async def test_agent_get_status():
    """Test agent status reporting."""
    agent = TestAgent("test-agent-123")

    status = agent.get_status()
    assert status["agent_id"] == "test-agent-123"
    assert status["state"] == "created"

    await agent.initialize()
    status = agent.get_status()
    assert status["state"] == "initialized"

"""Unit tests for core Agent functionality."""

import pytest
from genus.core.agent import Agent, AgentState


class TestAgent(Agent):
    """Test implementation of Agent."""

    async def initialize(self) -> None:
        """Initialize test agent."""
        self.state = AgentState.INITIALIZED


class TestAgentLifecycle:
    """Test agent lifecycle management."""

    async def test_agent_creation(self):
        """Test agent is created in CREATED state."""
        agent = TestAgent("test_agent")
        assert agent.name == "test_agent"
        assert agent.state == AgentState.CREATED
        assert agent.error_count == 0
        assert agent.execution_count == 0

    async def test_agent_initialization(self):
        """Test agent initialization."""
        agent = TestAgent("test_agent")
        await agent.initialize()
        assert agent.state == AgentState.INITIALIZED

    async def test_agent_start(self):
        """Test agent start transitions to RUNNING."""
        agent = TestAgent("test_agent")
        await agent.initialize()
        await agent.start()
        assert agent.state == AgentState.RUNNING

    async def test_agent_start_without_init_fails(self):
        """Test starting agent without initialization fails."""
        agent = TestAgent("test_agent")
        with pytest.raises(RuntimeError, match="must be initialized"):
            await agent.start()

    async def test_agent_stop(self):
        """Test agent stop transitions to STOPPED."""
        agent = TestAgent("test_agent")
        await agent.initialize()
        await agent.start()
        await agent.stop()
        assert agent.state == AgentState.STOPPED

    async def test_record_success(self):
        """Test recording successful execution."""
        agent = TestAgent("test_agent")
        agent.record_success()
        assert agent.execution_count == 1
        assert agent.last_success is not None

    async def test_record_error(self):
        """Test recording execution errors."""
        agent = TestAgent("test_agent")
        agent.record_error("Test error")
        assert agent.error_count == 1
        assert agent.last_error == "Test error"

    async def test_multiple_errors_fail_agent(self):
        """Test that multiple errors transition agent to FAILED."""
        agent = TestAgent("test_agent")
        await agent.initialize()
        await agent.start()

        # Record 10 errors to trigger failure
        for i in range(10):
            agent.record_error(f"Error {i}")

        assert agent.state == AgentState.FAILED
        assert agent.error_count == 10

    async def test_get_status(self):
        """Test getting agent status."""
        agent = TestAgent("test_agent")
        await agent.initialize()
        await agent.start()
        agent.record_success()

        status = agent.get_status()
        assert status["name"] == "test_agent"
        assert status["state"] == "running"
        assert status["execution_count"] == 1
        assert status["error_count"] == 0
        assert status["last_success"] is not None

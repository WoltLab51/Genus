"""
Test Agent Base Classes

Tests for core agent functionality.
"""

import pytest
import asyncio
from genus.core.agent import Agent, AgentState


class TestAgent(Agent):
    """Concrete test agent implementation."""

    async def initialize(self):
        self._transition_state(AgentState.INITIALIZED)

    async def start(self):
        self._transition_state(AgentState.RUNNING)

    async def stop(self):
        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message):
        pass


class TestAgentBaseClass:
    """Test suite for Agent base class."""

    def test_agent_creation(self):
        """Test agent can be created with default values."""
        agent = TestAgent()
        assert agent.id is not None
        assert agent.name == "TestAgent"
        assert agent.state == AgentState.INITIALIZED

    def test_agent_creation_with_custom_values(self):
        """Test agent can be created with custom values."""
        agent = TestAgent(agent_id="test-123", name="CustomAgent")
        assert agent.id == "test-123"
        assert agent.name == "CustomAgent"

    def test_agent_metadata(self):
        """Test agent metadata management."""
        agent = TestAgent()
        agent.set_metadata("key1", "value1")
        agent.set_metadata("key2", 42)

        metadata = agent.metadata
        assert metadata["key1"] == "value1"
        assert metadata["key2"] == 42

    @pytest.mark.asyncio
    async def test_agent_lifecycle(self):
        """Test agent lifecycle state transitions."""
        agent = TestAgent()

        # Initially in INITIALIZED state (set by constructor)
        assert agent.state == AgentState.INITIALIZED

        # Initialize
        await agent.initialize()
        assert agent.state == AgentState.INITIALIZED

        # Start
        await agent.start()
        assert agent.state == AgentState.RUNNING

        # Stop
        await agent.stop()
        assert agent.state == AgentState.STOPPED

    def test_agent_repr(self):
        """Test agent string representation."""
        agent = TestAgent(agent_id="test-123", name="TestAgent")
        repr_str = repr(agent)
        assert "TestAgent" in repr_str
        assert "test-123" in repr_str
        assert "initialized" in repr_str.lower()

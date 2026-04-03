"""
Unit tests for core components.
"""
import pytest
from genus.core.agent import Agent, AgentState
from genus.core.config import Config
import os


class TestAgent(Agent):
    """Test agent implementation."""

    async def initialize(self) -> None:
        await super().initialize()

    async def start(self) -> None:
        await super().start()

    async def stop(self) -> None:
        await super().stop()


async def test_agent_lifecycle():
    """Test agent lifecycle transitions."""
    agent = TestAgent("test_agent")

    assert agent.state == AgentState.CREATED
    assert not agent.is_running()

    await agent.initialize()
    assert agent.state == AgentState.INITIALIZED

    await agent.start()
    assert agent.state == AgentState.RUNNING
    assert agent.is_running()

    await agent.stop()
    assert agent.state == AgentState.STOPPED
    assert not agent.is_running()


async def test_agent_cannot_start_without_initialization():
    """Test that agent cannot start before initialization."""
    agent = TestAgent("test_agent")

    with pytest.raises(RuntimeError):
        await agent.start()


def test_config_requires_api_key():
    """Test that Config requires API_KEY environment variable."""
    # Remove API_KEY if it exists
    old_api_key = os.environ.pop("API_KEY", None)

    with pytest.raises(ValueError, match="API_KEY environment variable is required"):
        Config()

    # Restore API_KEY
    if old_api_key:
        os.environ["API_KEY"] = old_api_key


def test_config_with_api_key():
    """Test Config initialization with API_KEY."""
    os.environ["API_KEY"] = "test_key"
    config = Config()

    assert config.api_key == "test_key"
    assert config.database_url is not None
    assert isinstance(config.debug, bool)

"""Unit tests for the Agent base class and AgentState."""

import pytest
from genus.core.agent import Agent, AgentState


class StubAgent(Agent):
    """Minimal concrete agent for testing."""

    async def initialize(self):
        self._transition_state(AgentState.INITIALIZED)

    async def start(self):
        self._transition_state(AgentState.RUNNING)

    async def stop(self):
        self._transition_state(AgentState.STOPPED)

    async def execute(self, payload=None):
        return {"echo": payload}


class TestAgentCreation:

    def test_auto_id(self):
        a = StubAgent()
        assert a.id is not None
        assert a.state == AgentState.INITIALIZED

    def test_custom_id_and_name(self):
        a = StubAgent(agent_id="x", name="Xavier")
        assert a.id == "x"
        assert a.name == "Xavier"

    def test_default_name_is_class_name(self):
        a = StubAgent()
        assert a.name == "StubAgent"


class TestAgentMetadata:

    def test_set_and_get(self):
        a = StubAgent()
        a.set_metadata("k", 42)
        assert a.metadata["k"] == 42

    def test_metadata_is_a_copy(self):
        a = StubAgent()
        a.set_metadata("k", 1)
        m = a.metadata
        m["k"] = 999
        assert a.metadata["k"] == 1


class TestAgentLifecycle:

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        a = StubAgent()
        assert a.state == AgentState.INITIALIZED

        await a.initialize()
        assert a.state == AgentState.INITIALIZED

        await a.start()
        assert a.state == AgentState.RUNNING

        await a.stop()
        assert a.state == AgentState.STOPPED


class TestGetStatus:

    def test_status_dict(self):
        a = StubAgent(agent_id="s1", name="S1")
        s = a.get_status()
        assert s["agent_id"] == "s1"
        assert s["name"] == "S1"
        assert s["state"] == "initialized"


class TestRepr:

    def test_repr(self):
        a = StubAgent(agent_id="r", name="Repr")
        assert "Repr" in repr(a) and "r" in repr(a)

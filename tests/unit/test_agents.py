"""Unit tests for agents."""

import pytest
from genus.communication.message_bus import MessageBus
from genus.storage.memory_store import MemoryStore
from genus.storage.decision_store import DecisionStore
from genus.agents.data_collector import DataCollectorAgent
from genus.agents.analysis import AnalysisAgent
from genus.agents.decision import DecisionAgent


class TestDataCollectorAgent:
    """Test DataCollectorAgent functionality."""

    async def test_agent_initialization(self):
        """Test agent can be initialized."""
        bus = MessageBus()
        store = MemoryStore()
        agent = DataCollectorAgent(bus, store)

        assert agent.name == "data_collector"
        await agent.initialize()
        assert agent.state.value == "initialized"

    async def test_agent_processes_raw_data(self):
        """Test agent processes raw data messages."""
        bus = MessageBus()
        store = MemoryStore()
        agent = DataCollectorAgent(bus, store)
        await agent.initialize()
        await agent.start()

        # Capture published messages
        processed = []

        async def capture(message):
            processed.append(message)

        bus.subscribe("data.processed", capture)

        # Publish raw data
        await bus.publish("data.raw", {"test": "data"})

        # Verify processing
        assert len(processed) == 1
        assert processed[0].data["processed"] is True
        assert agent.execution_count == 1


class TestAnalysisAgent:
    """Test AnalysisAgent functionality."""

    async def test_agent_initialization(self):
        """Test agent can be initialized."""
        bus = MessageBus()
        store = MemoryStore()
        agent = AnalysisAgent(bus, store)

        assert agent.name == "analysis"
        await agent.initialize()
        assert agent.state.value == "initialized"

    async def test_agent_analyzes_data(self):
        """Test agent analyzes processed data."""
        bus = MessageBus()
        store = MemoryStore()
        agent = AnalysisAgent(bus, store)
        await agent.initialize()
        await agent.start()

        # Capture analysis results
        results = []

        async def capture(message):
            results.append(message)

        bus.subscribe("analysis.complete", capture)

        # Publish processed data
        await bus.publish("data.processed", {"data": "test"})

        # Verify analysis
        assert len(results) == 1
        assert "insights" in results[0].data
        assert agent.execution_count == 1


class TestDecisionAgent:
    """Test DecisionAgent functionality."""

    async def test_agent_initialization(self):
        """Test agent can be initialized."""
        bus = MessageBus()
        store = DecisionStore()
        agent = DecisionAgent(bus, store)

        assert agent.name == "decision"
        await agent.initialize()
        assert agent.state.value == "initialized"

    async def test_agent_makes_decisions(self):
        """Test agent makes decisions based on analysis."""
        bus = MessageBus()
        store = DecisionStore()
        agent = DecisionAgent(bus, store)
        await agent.initialize()
        await agent.start()

        # Capture decisions
        decisions = []

        async def capture(message):
            decisions.append(message)

        bus.subscribe("decision.made", capture)

        # Publish analysis
        await bus.publish("analysis.complete", {
            "confidence": 0.9,
            "insights": ["insight1", "insight2"]
        })

        # Verify decision
        assert len(decisions) == 1
        assert "decision_id" in decisions[0].data
        assert decisions[0].data["action"] == "approve"
        assert agent.execution_count == 1

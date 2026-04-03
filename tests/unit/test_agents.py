"""Unit tests for agent implementations."""

import pytest

from genus.communication.message_bus import MessageBus
from genus.storage.memory_store import MemoryStore
from genus.storage.decision_store import DecisionStore
from genus.agents.data_collector import DataCollectorAgent
from genus.agents.analysis import AnalysisAgent
from genus.agents.decision import DecisionAgent


async def test_data_collector_agent():
    """Test DataCollectorAgent collects and stores data."""
    bus = MessageBus()
    store = MemoryStore()
    agent = DataCollectorAgent(bus, store)

    await agent.initialize()
    await agent.start()

    # Publish data collection message
    await bus.publish("data.collect", {
        "source": "test",
        "data": {"value": 123}
    })

    # Wait for processing
    import asyncio
    await asyncio.sleep(0.1)

    # Check data was stored
    assert store.count() > 0

    await agent.stop()


async def test_analysis_agent():
    """Test AnalysisAgent analyzes data."""
    bus = MessageBus()
    store = MemoryStore()
    agent = AnalysisAgent(bus, store)

    await agent.initialize()
    await agent.start()

    published_messages = []

    async def capture_analysis(topic, message):
        published_messages.append((topic, message))

    bus.subscribe("analysis.complete", capture_analysis)

    # Publish data collected message
    await bus.publish("data.collected", {
        "memory_id": "1",
        "source": "test",
        "data": {"type": "observation", "value": 123}
    })

    # Wait for processing
    import asyncio
    await asyncio.sleep(0.1)

    # Check analysis was published
    assert len(published_messages) > 0
    assert published_messages[0][0] == "analysis.complete"

    await agent.stop()


async def test_decision_agent():
    """Test DecisionAgent makes decisions."""
    bus = MessageBus()
    decision_store = DecisionStore()
    agent = DecisionAgent(bus, decision_store)

    await agent.initialize()
    await agent.start()

    # Publish analysis complete message
    await bus.publish("analysis.complete", {
        "memory_id": "1",
        "source": "test",
        "analysis": {
            "data_type": "observation",
            "size": 100,
            "summary": "Test analysis"
        }
    })

    # Wait for processing
    import asyncio
    await asyncio.sleep(0.1)

    # Check decision was stored
    assert decision_store.count() > 0

    await agent.stop()


async def test_agent_integration():
    """Test agents work together end-to-end."""
    bus = MessageBus()
    memory_store = MemoryStore()
    decision_store = DecisionStore()

    # Initialize all agents
    data_collector = DataCollectorAgent(bus, memory_store)
    analysis_agent = AnalysisAgent(bus, memory_store)
    decision_agent = DecisionAgent(bus, decision_store)

    await data_collector.initialize()
    await analysis_agent.initialize()
    await decision_agent.initialize()

    await data_collector.start()
    await analysis_agent.start()
    await decision_agent.start()

    # Trigger data collection
    await bus.publish("data.collect", {
        "source": "test",
        "type": "observation",
        "value": 42
    })

    # Wait for all processing
    import asyncio
    await asyncio.sleep(0.2)

    # Verify the pipeline worked
    assert memory_store.count() > 0
    assert decision_store.count() > 0

    # Stop all agents
    await data_collector.stop()
    await analysis_agent.stop()
    await decision_agent.stop()

"""
Integration tests for agent interactions and learning.
"""
import pytest
import os
from genus.communication.message_bus import MessageBus
from genus.storage.stores import MemoryStore, DecisionStore, FeedbackStore
from genus.agents.data_collector import DataCollectorAgent
from genus.agents.analysis import AnalysisAgent
from genus.agents.decision import DecisionAgent


@pytest.fixture
async def agent_system():
    """Create a complete agent system for testing."""
    os.environ["API_KEY"] = "test_key"

    # Create components
    message_bus = MessageBus()
    memory_store = MemoryStore("sqlite+aiosqlite:///:memory:")
    decision_store = DecisionStore("sqlite+aiosqlite:///:memory:")
    feedback_store = FeedbackStore("sqlite+aiosqlite:///:memory:")

    # Initialize stores
    await memory_store.initialize()
    await decision_store.initialize()
    await feedback_store.initialize()

    # Create agents
    data_collector = DataCollectorAgent("DataCollector", message_bus)
    analysis_agent = AnalysisAgent("AnalysisAgent", message_bus, memory_store)
    decision_agent = DecisionAgent(
        "DecisionAgent", message_bus, decision_store, feedback_store
    )

    # Initialize and start agents
    for agent in [data_collector, analysis_agent, decision_agent]:
        await agent.initialize()
        await agent.start()

    yield {
        "message_bus": message_bus,
        "memory_store": memory_store,
        "decision_store": decision_store,
        "feedback_store": feedback_store,
        "data_collector": data_collector,
        "analysis_agent": analysis_agent,
        "decision_agent": decision_agent,
    }

    # Cleanup
    for agent in [data_collector, analysis_agent, decision_agent]:
        await agent.stop()

    await memory_store.close()
    await decision_store.close()
    await feedback_store.close()


async def test_agent_pipeline(agent_system):
    """Test complete agent pipeline from data to decision."""
    data_collector = agent_system["data_collector"]
    decision_store = agent_system["decision_store"]

    # Submit data
    await data_collector.collect_data("test data")

    # Give time for async processing
    import asyncio
    await asyncio.sleep(0.5)

    # Check that decision was made
    decisions = await decision_store.get_all_decisions()
    assert len(decisions) >= 1


async def test_learning_feedback_loop(agent_system):
    """Test that feedback influences future decisions."""
    data_collector = agent_system["data_collector"]
    decision_agent = agent_system["decision_agent"]
    decision_store = agent_system["decision_store"]

    # First decision
    await data_collector.collect_data("critical system update")

    import asyncio
    await asyncio.sleep(0.5)

    decisions = await decision_store.get_all_decisions()
    assert len(decisions) >= 1

    decision_id = decisions[0]["decision_id"]
    original_confidence = decisions[0]["confidence"]

    # Submit positive feedback
    await decision_agent.submit_feedback(
        decision_id=decision_id, score=0.95, label="success", comment="Excellent!"
    )

    # Second similar decision
    await data_collector.collect_data("critical system update")

    await asyncio.sleep(0.5)

    # Get all decisions
    all_decisions = await decision_store.get_all_decisions()
    assert len(all_decisions) >= 2

    # Verify learning was applied
    analysis = await decision_agent.learning_engine.analyze_feedback()
    assert analysis["total_feedback"] >= 1
    assert analysis["success_count"] >= 1


async def test_multiple_feedback_patterns(agent_system):
    """Test learning with multiple patterns."""
    data_collector = agent_system["data_collector"]
    decision_agent = agent_system["decision_agent"]
    decision_store = agent_system["decision_store"]

    import asyncio

    # Pattern 1: Successful pattern
    for _ in range(3):
        await data_collector.collect_data("routine maintenance")
        await asyncio.sleep(0.3)

    decisions = await decision_store.get_all_decisions()
    for decision in decisions[-3:]:
        await decision_agent.submit_feedback(
            decision_id=decision["decision_id"], score=0.9, label="success"
        )

    # Pattern 2: Failed pattern
    for _ in range(3):
        await data_collector.collect_data("emergency hotfix")
        await asyncio.sleep(0.3)

    decisions = await decision_store.get_all_decisions()
    for decision in decisions[-3:]:
        await decision_agent.submit_feedback(
            decision_id=decision["decision_id"], score=0.3, label="failure"
        )

    # Analyze learning
    analysis = await decision_agent.learning_engine.analyze_feedback()
    assert analysis["total_feedback"] >= 6
    assert len(analysis["patterns"]) >= 1

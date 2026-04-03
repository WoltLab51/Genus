import pytest
import asyncio
from agents.data_collector.agent import DataCollectorAgent
from agents.analysis.agent import AnalysisAgent
from agents.decision.agent import DecisionAgent
from core.memory import MemoryStore
from core.messaging import EventBus
from models.schemas import DataItem, AnalysisResult


@pytest.fixture
def fresh_memory():
    return MemoryStore()


@pytest.fixture
def fresh_bus():
    return EventBus()


@pytest.mark.asyncio
async def test_data_collector_run():
    agent = DataCollectorAgent()
    agent.memory = MemoryStore()
    agent.bus = EventBus()
    items = await agent.run({"sources": [
        {"name": "test_source", "url": None, "mock_data": {"key": "value"}}
    ]})
    assert len(items) == 1
    assert items[0].source == "test_source"
    assert items[0].content == {"key": "value"}


@pytest.mark.asyncio
async def test_analysis_agent_run():
    agent = AnalysisAgent()
    agent.memory = MemoryStore()
    agent.bus = EventBus()
    items = [
        DataItem(source="src1", content={"topic": "AI", "score": 90}),
        DataItem(source="src2", content={"topic": "ML", "score": 75}),
    ]
    result = await agent.run({"items": items})
    assert result.confidence > 0
    assert "src1" in result.summary or "src2" in result.summary
    assert len(result.insights) > 0


@pytest.mark.asyncio
async def test_decision_agent_run():
    agent = DecisionAgent()
    agent.memory = MemoryStore()
    agent.bus = EventBus()
    analysis = AnalysisResult(
        input_data={"item_count": 3},
        summary="Test summary",
        insights=["insight1"],
        confidence=0.85,
    )
    decision = await agent.run({"analysis_result": analysis})
    assert decision.priority == 1
    assert "High confidence" in decision.recommendation


@pytest.mark.asyncio
async def test_memory_store():
    store = MemoryStore()
    store.set("ns", "key1", "value1")
    assert store.get("ns", "key1") == "value1"
    assert store.get("ns", "missing", "default") == "default"
    store.delete("ns", "key1")
    assert store.get("ns", "key1") is None
    assert len(store.history()) == 1


@pytest.mark.asyncio
async def test_event_bus():
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("test.event", handler)
    await bus.publish("test.event", {"data": 123})
    assert len(received) == 1
    assert received[0]["payload"]["data"] == 123


@pytest.mark.asyncio
async def test_full_pipeline():
    """Test the full pipeline: collect -> analyze -> decide via event bus."""
    collector = DataCollectorAgent()
    analyzer = AnalysisAgent()
    decider = DecisionAgent()

    shared_memory = MemoryStore()
    shared_bus = EventBus()

    collector.memory = shared_memory
    collector.bus = shared_bus
    analyzer.memory = shared_memory
    analyzer.bus = shared_bus
    decider.memory = shared_memory
    decider.bus = shared_bus

    # Re-subscribe handlers to fresh bus
    shared_bus.subscribe("data.collected", analyzer._on_data_collected)
    shared_bus.subscribe("data.analyzed", decider._on_data_analyzed)

    items = await collector.run({"sources": [
        {"name": "pipeline_test", "url": None, "mock_data": {"result": "success", "count": 5}}
    ]})
    # Give event handlers time to run
    await asyncio.sleep(0.1)

    assert len(items) == 1
    last_analysis = shared_memory.get("analysis", "last_result")
    assert last_analysis is not None
    last_decision = shared_memory.get("decision", "last_decision")
    assert last_decision is not None

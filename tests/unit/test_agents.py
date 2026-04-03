"""Unit tests for the three pipeline agents.

Tests are isolated: each test creates its own MessageBus, MemoryStore,
and agent instances — no singletons involved.
"""

import asyncio
import pytest

from genus.communication.message_bus import MessageBus
from genus.storage.memory import MemoryStore
from genus.agents.data_collector import DataCollectorAgent
from genus.agents.analysis import AnalysisAgent
from genus.agents.decision import DecisionAgent


# -- helpers ----------------------------------------------------------------

def _make_bus_memory():
    return MessageBus(), MemoryStore()


# -- DataCollectorAgent -----------------------------------------------------

class TestDataCollector:

    @pytest.mark.asyncio
    async def test_collect_mock_data(self):
        bus, mem = _make_bus_memory()
        agent = DataCollectorAgent(bus, mem)
        await agent.initialize()
        await agent.start()

        items = await agent.execute({
            "sources": [
                {"name": "src", "url": None, "mock_data": {"key": "val"}}
            ]
        })
        assert len(items) == 1
        assert items[0]["source"] == "src"
        assert items[0]["content"] == {"key": "val"}

    @pytest.mark.asyncio
    async def test_publishes_event(self):
        bus, mem = _make_bus_memory()
        agent = DataCollectorAgent(bus, mem)
        await agent.initialize()

        received = []

        async def _capture(m):
            received.append(m)

        bus.subscribe("data.collected", _capture)

        await agent.execute()
        # asyncio.gather in publish is awaited inline so handler fires
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_stores_in_memory(self):
        bus, mem = _make_bus_memory()
        agent = DataCollectorAgent(bus, mem)
        await agent.initialize()
        await agent.execute()
        assert mem.get("data_collector", "last_collection") is not None


# -- AnalysisAgent ----------------------------------------------------------

class TestAnalysis:

    @pytest.mark.asyncio
    async def test_direct_execute(self):
        bus, mem = _make_bus_memory()
        agent = AnalysisAgent(bus, mem)
        await agent.initialize()

        items = [
            {"source": "s1", "content": {"topic": "AI", "score": 90}},
            {"source": "s2", "content": {"topic": "ML", "score": 75}},
        ]
        result = await agent.execute({"items": items})
        assert result["confidence"] > 0
        assert "s1" in result["summary"] or "s2" in result["summary"]

    @pytest.mark.asyncio
    async def test_subscribes_to_data_collected(self):
        bus, mem = _make_bus_memory()
        agent = AnalysisAgent(bus, mem)
        await agent.initialize()

        received = []

        async def _capture(m):
            received.append(m)

        bus.subscribe("data.analyzed", _capture)

        await bus.publish_event("data.collected", {
            "items": [{"source": "x", "content": {"a": 1}}]
        })
        assert len(received) == 1


# -- DecisionAgent ----------------------------------------------------------

class TestDecision:

    @pytest.mark.asyncio
    async def test_direct_execute(self):
        bus, mem = _make_bus_memory()
        agent = DecisionAgent(bus, mem)
        await agent.initialize()

        analysis = {
            "summary": "Test",
            "insights": ["i1"],
            "confidence": 0.85,
        }
        decision = await agent.execute({"analysis_result": analysis})
        assert decision["priority"] == 1
        assert "High confidence" in decision["recommendation"]

    @pytest.mark.asyncio
    async def test_subscribes_to_data_analyzed(self):
        bus, mem = _make_bus_memory()
        agent = DecisionAgent(bus, mem)
        await agent.initialize()

        received = []

        async def _capture(m):
            received.append(m)

        bus.subscribe("decision.made", _capture)

        await bus.publish_event("data.analyzed", {
            "result": {"summary": "S", "insights": [], "confidence": 0.5}
        })
        assert len(received) == 1


# -- Full pipeline ----------------------------------------------------------

class TestFullPipeline:

    @pytest.mark.asyncio
    async def test_collect_analyze_decide(self):
        bus, mem = _make_bus_memory()
        collector = DataCollectorAgent(bus, mem)
        analyzer = AnalysisAgent(bus, mem)
        decider = DecisionAgent(bus, mem)

        await collector.initialize()
        await analyzer.initialize()
        await decider.initialize()
        await collector.start()
        await analyzer.start()
        await decider.start()

        items = await collector.execute({
            "sources": [
                {"name": "pipe", "url": None, "mock_data": {"result": "ok", "count": 5}}
            ]
        })
        assert len(items) == 1

        # event handlers are awaited synchronously inside publish
        assert mem.get("analysis", "last_result") is not None
        assert mem.get("decision", "last_decision") is not None

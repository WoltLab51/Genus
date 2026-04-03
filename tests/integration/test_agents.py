"""Integration tests for agent communication and state tracking."""

import pytest
from genus.communication.message_bus import MessageBus
from genus.core.system_state import SystemStateTracker
from genus.storage.memory_store import MemoryStore
from genus.storage.decision_store import DecisionStore
from genus.agents.data_collector import DataCollectorAgent
from genus.agents.analysis import AnalysisAgent
from genus.agents.decision import DecisionAgent
import asyncio


class TestAgentIntegration:
    """Test agents working together."""

    async def test_complete_pipeline(self):
        """Test complete data processing pipeline through all agents."""
        # Set up infrastructure
        tracker = SystemStateTracker()
        bus = MessageBus(state_tracker=tracker)
        memory_store = MemoryStore()
        decision_store = DecisionStore()

        # Create and initialize agents
        collector = DataCollectorAgent(bus, memory_store)
        analyzer = AnalysisAgent(bus, memory_store)
        decider = DecisionAgent(bus, decision_store)

        await collector.initialize()
        await analyzer.initialize()
        await decider.initialize()

        await collector.start()
        await analyzer.start()
        await decider.start()

        # Track decisions
        decisions = []

        async def track_decisions(message):
            decisions.append(message)

        bus.subscribe("decision.made", track_decisions)

        # Inject raw data
        await bus.publish("data.raw", {"test": "data"})

        # Wait for async processing
        await asyncio.sleep(0.1)

        # Verify pipeline executed
        assert collector.execution_count == 1
        assert analyzer.execution_count == 1
        assert decider.execution_count == 1

        # Verify decision was made
        assert len(decisions) == 1

        # Clean up
        await collector.stop()
        await analyzer.stop()
        await decider.stop()

    async def test_agent_error_tracking(self):
        """Test that agent errors are tracked in system state."""
        tracker = SystemStateTracker()
        bus = MessageBus(state_tracker=tracker)
        memory_store = MemoryStore()

        agent = DataCollectorAgent(bus, memory_store)
        await agent.initialize()
        await agent.start()

        # Simulate error
        agent.record_error("Test error")

        # Update tracker
        tracker.update_agent_state(agent.name, agent.state.value, agent.last_success)
        tracker.record_agent_error(agent.name, "Test error")

        # Verify error is tracked
        report = tracker.get_health_report()
        assert agent.name in report["recent_errors"]["agents"]

        await agent.stop()

    async def test_message_bus_error_reporting(self):
        """Test that message bus errors are reported to state tracker."""
        tracker = SystemStateTracker()
        bus = MessageBus(state_tracker=tracker)

        # Create failing handler
        async def failing_handler(message):
            raise ValueError("Handler failed")

        bus.subscribe("test_topic", failing_handler)
        await bus.publish("test_topic", "data")

        # Verify error was reported
        report = tracker.get_health_report()
        assert len(report["recent_errors"]["message_bus"]) > 0

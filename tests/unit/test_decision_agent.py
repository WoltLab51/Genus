"""
Test Decision Agent

Tests for exploration/exploitation logic in SimpleDecisionAgent.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from genus.agents.decision_agent import (
    SimpleDecisionAgent,
    _compute_exploration_rate,
    _MIN_EXPLORATION_RATE,
    _MAX_EXPLORATION_RATE,
    _BUY_THRESHOLD,
)
from genus.communication.message_bus import MessageBus, Message


# ---------------------------------------------------------------------------
# _compute_exploration_rate helper
# ---------------------------------------------------------------------------

class TestComputeExplorationRate:
    """Tests for the exploration rate helper function."""

    def test_high_good_ratio_gives_low_exploration(self):
        """High good_ratio should produce a low exploration rate."""
        rate = _compute_exploration_rate(0.9)
        assert rate == pytest.approx(0.1)  # clamped to minimum

    def test_low_good_ratio_gives_high_exploration(self):
        """Low good_ratio should produce a high exploration rate."""
        rate = _compute_exploration_rate(0.1)
        assert rate == pytest.approx(0.9)  # clamped to maximum

    def test_medium_good_ratio(self):
        """Middle good_ratio should return 1 - good_ratio."""
        rate = _compute_exploration_rate(0.5)
        assert rate == pytest.approx(0.5)

    def test_clamp_minimum(self):
        """exploration_rate is never below _MIN_EXPLORATION_RATE."""
        rate = _compute_exploration_rate(1.0)
        assert rate >= _MIN_EXPLORATION_RATE

    def test_clamp_maximum(self):
        """exploration_rate is never above _MAX_EXPLORATION_RATE."""
        rate = _compute_exploration_rate(0.0)
        assert rate <= _MAX_EXPLORATION_RATE

    def test_monotone_decreasing(self):
        """Higher good_ratio should produce lower or equal exploration_rate."""
        rates = [_compute_exploration_rate(r / 10) for r in range(11)]
        for current, nxt in zip(rates, rates[1:]):
            assert current >= nxt


# ---------------------------------------------------------------------------
# SimpleDecisionAgent
# ---------------------------------------------------------------------------

def _make_message(payload: dict) -> Message:
    return Message(topic="data.analyzed", payload=payload, sender_id="analysis")


def _make_agent(bus: MessageBus) -> SimpleDecisionAgent:
    return SimpleDecisionAgent("decision", bus)


class TestSimpleDecisionAgent:
    """Tests for SimpleDecisionAgent exploration/exploitation behaviour."""

    @pytest.mark.asyncio
    async def test_exploit_buy_when_score_above_threshold(self):
        """In exploitation mode a high score should produce BUY."""
        bus = MessageBus()
        agent = _make_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        good_stats = {"good_ratio": 0.9, "total": 10}  # low exploration rate
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=good_stats):
            with patch("genus.agents.decision_agent.random.random", return_value=0.99):
                await agent.handle_message(_make_message({"score": 80}))

        assert len(received) == 1
        assert received[0].payload["decision"] == "BUY"
        assert received[0].payload["reason"] == "exploit"

    @pytest.mark.asyncio
    async def test_exploit_wait_when_score_below_threshold(self):
        """In exploitation mode a low score should produce WAIT."""
        bus = MessageBus()
        agent = _make_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        good_stats = {"good_ratio": 0.9, "total": 10}
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=good_stats):
            with patch("genus.agents.decision_agent.random.random", return_value=0.99):
                await agent.handle_message(_make_message({"score": 20}))

        assert len(received) == 1
        assert received[0].payload["decision"] == "WAIT"
        assert received[0].payload["reason"] == "exploit"

    @pytest.mark.asyncio
    async def test_explore_produces_buy_or_wait(self):
        """In exploration mode the decision is BUY or WAIT."""
        bus = MessageBus()
        agent = _make_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        low_stats = {"good_ratio": 0.1, "total": 10}  # high exploration rate
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=low_stats):
            with patch("genus.agents.decision_agent.random.random", return_value=0.0):
                with patch("genus.agents.decision_agent.random.choice", return_value="BUY"):
                    await agent.handle_message(_make_message({"score": 50}))

        assert len(received) == 1
        assert received[0].payload["decision"] in {"BUY", "WAIT"}
        assert received[0].payload["reason"] == "explore"

    @pytest.mark.asyncio
    async def test_payload_contains_action_field(self):
        """Published payload must include both 'decision' and 'action' fields."""
        bus = MessageBus()
        agent = _make_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        stats = {"good_ratio": 0.5, "total": 5}
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=stats):
            with patch("genus.agents.decision_agent.random.random", return_value=0.99):
                await agent.handle_message(_make_message({"score": 80}))

        payload = received[0].payload
        assert "decision" in payload
        assert "action" in payload
        assert payload["decision"] == payload["action"]

    @pytest.mark.asyncio
    async def test_classification_fallback_high(self):
        """'classification: high' should map to a score that produces BUY."""
        bus = MessageBus()
        agent = _make_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        stats = {"good_ratio": 0.9, "total": 10}
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=stats):
            with patch("genus.agents.decision_agent.random.random", return_value=0.99):
                await agent.handle_message(_make_message({"classification": "high"}))

        assert received[0].payload["decision"] == "BUY"

    @pytest.mark.asyncio
    async def test_classification_fallback_low(self):
        """'classification: low' should map to a score that produces WAIT."""
        bus = MessageBus()
        agent = _make_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        stats = {"good_ratio": 0.9, "total": 10}
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=stats):
            with patch("genus.agents.decision_agent.random.random", return_value=0.99):
                await agent.handle_message(_make_message({"classification": "low"}))

        assert received[0].payload["decision"] == "WAIT"

    @pytest.mark.asyncio
    async def test_empty_memory_uses_default_good_ratio(self):
        """When memory is empty the agent should fall back to good_ratio=0.5."""
        bus = MessageBus()
        agent = _make_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        # Simulate empty memory (no 'good_ratio' key)
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value={"total": 0}):
            with patch("genus.agents.decision_agent.random.random", return_value=0.99):
                await agent.handle_message(_make_message({"score": 80}))

        assert len(received) == 1
        assert received[0].payload["decision"] in {"BUY", "WAIT"}

    @pytest.mark.asyncio
    async def test_publishes_to_decision_made_topic(self):
        """Agent must publish on 'decision.made' topic."""
        bus = MessageBus()
        agent = _make_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        stats = {"good_ratio": 0.5, "total": 5}
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=stats):
            await agent.handle_message(_make_message({"score": 60}))

        assert len(received) == 1
        assert received[0].topic == "decision.made"

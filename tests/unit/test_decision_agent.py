"""
Test Decision Agent

Part 1 – backward-compatible tests for the legacy SimpleDecisionAgent
         (BUY / WAIT exploration/exploitation semantics).

Part 2 – tests for the new DecisionAgent with GENUS-generic decision
         semantics: accept | retry | replan | escalate | delegate.
"""

import pytest
from unittest.mock import patch

from genus.agents.decision_agent import (
    DecisionAgent,
    SimpleDecisionAgent,
    _compute_exploration_rate,
    _MIN_EXPLORATION_RATE,
    _MAX_EXPLORATION_RATE,
    _BUY_THRESHOLD,
)
from genus.communication.message_bus import MessageBus, Message


# ===========================================================================
# Part 1 – Legacy SimpleDecisionAgent (BUY / WAIT)
# ===========================================================================

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

def _make_legacy_message(payload: dict) -> Message:
    return Message(topic="data.analyzed", payload=payload, sender_id="analysis")


def _make_legacy_agent(bus: MessageBus) -> SimpleDecisionAgent:
    return SimpleDecisionAgent("decision", bus)


class TestSimpleDecisionAgent:
    """Tests for SimpleDecisionAgent exploration/exploitation behaviour."""

    @pytest.mark.asyncio
    async def test_exploit_buy_when_score_above_threshold(self):
        """In exploitation mode a high score should produce BUY."""
        bus = MessageBus()
        agent = _make_legacy_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        good_stats = {"good_ratio": 0.9, "total": 10}  # low exploration rate
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=good_stats):
            with patch("genus.agents.decision_agent.random.random", return_value=0.99):
                await agent.handle_message(_make_legacy_message({"score": 80}))

        assert len(received) == 1
        assert received[0].payload["decision"] == "BUY"
        assert received[0].payload["reason"] == "exploit"

    @pytest.mark.asyncio
    async def test_exploit_wait_when_score_below_threshold(self):
        """In exploitation mode a low score should produce WAIT."""
        bus = MessageBus()
        agent = _make_legacy_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        good_stats = {"good_ratio": 0.9, "total": 10}
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=good_stats):
            with patch("genus.agents.decision_agent.random.random", return_value=0.99):
                await agent.handle_message(_make_legacy_message({"score": 20}))

        assert len(received) == 1
        assert received[0].payload["decision"] == "WAIT"
        assert received[0].payload["reason"] == "exploit"

    @pytest.mark.asyncio
    async def test_explore_produces_buy_or_wait(self):
        """In exploration mode the decision is BUY or WAIT."""
        bus = MessageBus()
        agent = _make_legacy_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        low_stats = {"good_ratio": 0.1, "total": 10}  # high exploration rate
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=low_stats):
            with patch("genus.agents.decision_agent.random.random", return_value=0.0):
                with patch("genus.agents.decision_agent.random.choice", return_value="BUY"):
                    await agent.handle_message(_make_legacy_message({"score": 50}))

        assert len(received) == 1
        assert received[0].payload["decision"] in {"BUY", "WAIT"}
        assert received[0].payload["reason"] == "explore"

    @pytest.mark.asyncio
    async def test_payload_contains_action_field(self):
        """Published payload must include both 'decision' and 'action' fields."""
        bus = MessageBus()
        agent = _make_legacy_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        stats = {"good_ratio": 0.5, "total": 5}
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=stats):
            with patch("genus.agents.decision_agent.random.random", return_value=0.99):
                await agent.handle_message(_make_legacy_message({"score": 80}))

        payload = received[0].payload
        assert "decision" in payload
        assert "action" in payload
        assert payload["decision"] == payload["action"]

    @pytest.mark.asyncio
    async def test_classification_fallback_high(self):
        """'classification: high' should map to a score that produces BUY."""
        bus = MessageBus()
        agent = _make_legacy_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        stats = {"good_ratio": 0.9, "total": 10}
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=stats):
            with patch("genus.agents.decision_agent.random.random", return_value=0.99):
                await agent.handle_message(_make_legacy_message({"classification": "high"}))

        assert received[0].payload["decision"] == "BUY"

    @pytest.mark.asyncio
    async def test_classification_fallback_low(self):
        """'classification: low' should map to a score that produces WAIT."""
        bus = MessageBus()
        agent = _make_legacy_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        stats = {"good_ratio": 0.9, "total": 10}
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=stats):
            with patch("genus.agents.decision_agent.random.random", return_value=0.99):
                await agent.handle_message(_make_legacy_message({"classification": "low"}))

        assert received[0].payload["decision"] == "WAIT"

    @pytest.mark.asyncio
    async def test_empty_memory_uses_default_good_ratio(self):
        """When memory is empty the agent should fall back to good_ratio=0.5."""
        bus = MessageBus()
        agent = _make_legacy_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        # Simulate empty memory (no 'good_ratio' key)
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value={"total": 0}):
            with patch("genus.agents.decision_agent.random.random", return_value=0.99):
                await agent.handle_message(_make_legacy_message({"score": 80}))

        assert len(received) == 1
        assert received[0].payload["decision"] in {"BUY", "WAIT"}

    @pytest.mark.asyncio
    async def test_publishes_to_decision_made_topic(self):
        """Agent must publish on 'decision.made' topic."""
        bus = MessageBus()
        agent = _make_legacy_agent(bus)
        received = []

        async def capture(msg: Message):
            received.append(msg)

        bus.subscribe("decision.made", "test", capture)

        stats = {"good_ratio": 0.5, "total": 5}
        with patch("genus.agents.decision_agent.Memory.get_stats", return_value=stats):
            await agent.handle_message(_make_legacy_message({"score": 60}))

        assert len(received) == 1
        assert received[0].topic == "decision.made"


# ===========================================================================
# Part 2 – New DecisionAgent (GENUS generic semantics)
# ===========================================================================

RUN_ID = "2026-04-05T14-07-12Z__test__abc123"


def _make_message(
    topic: str,
    payload: dict,
    run_id: str = RUN_ID,
    sender_id: str = "test-sender",
) -> Message:
    """Build a Message with run_id in metadata."""
    metadata = {"run_id": run_id} if run_id is not None else {}
    return Message(topic=topic, payload=payload, sender_id=sender_id, metadata=metadata)


def _make_analysis_msg(quality_score: float, context: dict = None, run_id: str = RUN_ID) -> Message:
    payload = {"quality_score": quality_score}
    if context:
        payload["context"] = context
    return _make_message("analysis.completed", payload, run_id=run_id)


def _make_quality_msg(quality_score: float, run_id: str = RUN_ID) -> Message:
    return _make_message("quality.scored", {"quality_score": quality_score}, run_id=run_id)


async def _run_agent_with_messages(bus: MessageBus, *messages: Message):
    """Initialize agent, send messages, return captured decision.made payloads."""
    agent = DecisionAgent(message_bus=bus, name="decision-test")
    received = []

    async def capture(msg: Message):
        received.append(msg)

    bus.subscribe("decision.made", "test-capture", capture)
    await agent.initialize()
    await agent.start()

    for msg in messages:
        await agent.process_message(msg)

    return received


class TestDecisionAgentMissingRunId:
    """Missing run_id must produce an escalate decision."""

    @pytest.mark.asyncio
    async def test_missing_run_id_produces_escalate(self):
        bus = MessageBus()
        msg = Message(
            topic="analysis.completed",
            payload={"quality_score": 0.9},
            sender_id="analysis",
            metadata={},  # no run_id
        )
        received = await _run_agent_with_messages(bus, msg)

        assert len(received) == 1
        p = received[0].payload
        assert p["decision"] == "escalate"
        assert "missing run_id" in p["reason"]

    @pytest.mark.asyncio
    async def test_escalate_message_carries_run_id_in_metadata(self):
        """decision.made for missing run_id must still carry run_id='unknown' in metadata."""
        bus = MessageBus()
        msg = Message(
            topic="analysis.completed",
            payload={"quality_score": 0.9},
            sender_id="analysis",
            metadata={},
        )
        received = await _run_agent_with_messages(bus, msg)
        assert received[0].metadata.get("run_id") == "unknown"


class TestDecisionAgentAccept:
    """Accept when quality >= min_quality (default 0.8)."""

    @pytest.mark.asyncio
    async def test_accept_at_default_threshold(self):
        bus = MessageBus()
        received = await _run_agent_with_messages(bus, _make_analysis_msg(0.85))
        assert len(received) == 1
        p = received[0].payload
        assert p["decision"] == "accept"
        assert p["requirements_met"] is True

    @pytest.mark.asyncio
    async def test_accept_exactly_at_threshold(self):
        bus = MessageBus()
        received = await _run_agent_with_messages(bus, _make_analysis_msg(0.8))
        assert received[0].payload["decision"] == "accept"

    @pytest.mark.asyncio
    async def test_accept_with_explicit_min_quality(self):
        """Explicit requirements.min_quality=0.7 should lower the bar."""
        bus = MessageBus()
        msg = _make_analysis_msg(0.75, context={"requirements": {"min_quality": 0.7}})
        received = await _run_agent_with_messages(bus, msg)
        assert received[0].payload["decision"] == "accept"


class TestDecisionAgentQMPreferred:
    """quality.scored message must be preferred over analysis fallback."""

    @pytest.mark.asyncio
    async def test_qm_overrides_analysis_fallback(self):
        """Send analysis (q=0.75, would retry) then quality.scored (q=0.9) → accept."""
        bus = MessageBus()
        analysis_msg = _make_analysis_msg(0.75)
        quality_msg = _make_quality_msg(0.9)
        received = await _run_agent_with_messages(bus, analysis_msg, quality_msg)

        # The last decision should use the QM score
        last = received[-1].payload
        assert last["decision"] == "accept"
        assert last["evidence"][0]["source"] == "qm"
        assert last["confidence"] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_analysis_used_when_no_qm(self):
        """When only analysis is available it is used as fallback."""
        bus = MessageBus()
        received = await _run_agent_with_messages(bus, _make_analysis_msg(0.85))
        p = received[0].payload
        assert p["decision"] == "accept"
        assert p["evidence"][0]["source"] == "analysis"
        assert p["confidence"] == pytest.approx(0.7)


class TestDecisionAgentRetry:
    """Retry when quality is just below threshold and budget is available."""

    @pytest.mark.asyncio
    async def test_retry_just_below_threshold(self):
        """quality=0.78 (just within retry_margin=0.05 of 0.8) → retry."""
        bus = MessageBus()
        received = await _run_agent_with_messages(bus, _make_analysis_msg(0.78))
        assert received[0].payload["decision"] == "retry"
        assert received[0].payload["requirements_met"] is False

    @pytest.mark.asyncio
    async def test_retry_with_custom_max_retries(self):
        """Custom max_retries=5 should still allow retry at attempt=4."""
        bus = MessageBus()
        ctx = {"limits": {"max_retries": 5}, "attempt": 4}
        msg = _make_analysis_msg(0.78, context=ctx)
        received = await _run_agent_with_messages(bus, msg)
        assert received[0].payload["decision"] == "retry"

    @pytest.mark.asyncio
    async def test_escalate_when_budget_exhausted(self):
        """attempt >= max_retries → escalate (budget exhausted)."""
        bus = MessageBus()
        ctx = {"limits": {"max_retries": 3}, "attempt": 3}
        msg = _make_analysis_msg(0.78, context=ctx)
        received = await _run_agent_with_messages(bus, msg)
        p = received[0].payload
        assert p["decision"] == "escalate"
        assert "budget" in p["reason"]


class TestDecisionAgentReplan:
    """Replan when quality is far below threshold."""

    @pytest.mark.asyncio
    async def test_replan_far_below_threshold(self):
        """quality=0.6 is well below 0.8-0.05=0.75 → replan."""
        bus = MessageBus()
        received = await _run_agent_with_messages(bus, _make_analysis_msg(0.6))
        assert received[0].payload["decision"] == "replan"

    @pytest.mark.asyncio
    async def test_replan_when_no_quality_evidence(self):
        """Message without quality_score in payload → replan (no evidence)."""
        bus = MessageBus()
        msg = _make_message("analysis.completed", {})  # no quality_score
        received = await _run_agent_with_messages(bus, msg)
        assert received[0].payload["decision"] == "replan"
        assert "no quality evidence" in received[0].payload["reason"]


class TestDecisionAgentCriticalGate:
    """Critical/high-risk without explicit requirements → escalate."""

    @pytest.mark.asyncio
    async def test_risk_high_without_requirements_escalates(self):
        """risk=high and no explicit min_quality → escalate even if quality is fine."""
        bus = MessageBus()
        msg = _make_analysis_msg(0.95, context={"risk": "high"})
        received = await _run_agent_with_messages(bus, msg)
        p = received[0].payload
        assert p["decision"] == "escalate"
        assert "critical" in p["reason"] or "requirements" in p["reason"]

    @pytest.mark.asyncio
    async def test_critical_true_without_requirements_escalates(self):
        """critical=True without explicit requirements → escalate."""
        bus = MessageBus()
        msg = _make_analysis_msg(0.95, context={"critical": True})
        received = await _run_agent_with_messages(bus, msg)
        assert received[0].payload["decision"] == "escalate"

    @pytest.mark.asyncio
    async def test_risk_high_with_explicit_requirements_accepts(self):
        """risk=high but explicit requirements provided → accept if quality ok."""
        bus = MessageBus()
        ctx = {"risk": "high", "requirements": {"min_quality": 0.8}}
        msg = _make_analysis_msg(0.9, context=ctx)
        received = await _run_agent_with_messages(bus, msg)
        assert received[0].payload["decision"] == "accept"

    @pytest.mark.asyncio
    async def test_risk_normal_without_requirements_accepts(self):
        """risk=normal (not critical) without explicit requirements → accept if quality ok."""
        bus = MessageBus()
        msg = _make_analysis_msg(0.85, context={"risk": "normal"})
        received = await _run_agent_with_messages(bus, msg)
        assert received[0].payload["decision"] == "accept"


class TestDecisionAgentDelegate:
    """needs_expert=True overrides other decisions → delegate."""

    @pytest.mark.asyncio
    async def test_delegate_when_needs_expert(self):
        bus = MessageBus()
        ctx = {"needs_expert": True}
        msg = _make_analysis_msg(0.9, context=ctx)
        received = await _run_agent_with_messages(bus, msg)
        assert received[0].payload["decision"] == "delegate"

    @pytest.mark.asyncio
    async def test_delegate_overrides_accept(self):
        """needs_expert wins even when quality is high."""
        bus = MessageBus()
        ctx = {"needs_expert": True, "requirements": {"min_quality": 0.5}}
        msg = _make_analysis_msg(0.99, context=ctx)
        received = await _run_agent_with_messages(bus, msg)
        assert received[0].payload["decision"] == "delegate"


class TestDecisionAgentRunIdInOutput:
    """decision.made message must carry run_id in both payload and metadata."""

    @pytest.mark.asyncio
    async def test_run_id_in_payload(self):
        bus = MessageBus()
        received = await _run_agent_with_messages(bus, _make_analysis_msg(0.85))
        assert received[0].payload["run_id"] == RUN_ID

    @pytest.mark.asyncio
    async def test_run_id_in_metadata(self):
        bus = MessageBus()
        received = await _run_agent_with_messages(bus, _make_analysis_msg(0.85))
        assert received[0].metadata.get("run_id") == RUN_ID

    @pytest.mark.asyncio
    async def test_alias_topic_data_analyzed_accepted(self):
        """data.analyzed (legacy alias) should be processed same as analysis.completed."""
        bus = MessageBus()
        msg = _make_message("data.analyzed", {"quality_score": 0.85})
        received = await _run_agent_with_messages(bus, msg)
        assert len(received) == 1
        assert received[0].payload["decision"] == "accept"

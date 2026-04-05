"""
Tests for QualityAgent and QualityScorecard.

Covers:
- publishes quality.scored when analysis has quality_score and run_id
- run_id propagation to output metadata
- requirements_met computed correctly
- behavior when missing run_id
- behavior when missing quality signals (quality_score None)
- score normalisation (0-100 → 0-1)
- confidence fallback
"""

import pytest

from genus.agents.quality_agent import QualityAgent, _normalise_score
from genus.communication.message_bus import Message, MessageBus
from genus.quality.scorecard import QualityScorecard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = "2026-04-05T14-07-12Z__test__abc123"


def _make_message(
    payload: dict,
    topic: str = "analysis.completed",
    run_id: str = RUN_ID,
    sender_id: str = "analysis",
) -> Message:
    metadata = {"run_id": run_id} if run_id is not None else {}
    return Message(topic=topic, payload=payload, sender_id=sender_id, metadata=metadata)


async def _run_agent(*messages: Message) -> list:
    """Initialize QualityAgent, send messages, return captured quality.scored payloads."""
    bus = MessageBus()
    agent = QualityAgent(message_bus=bus, name="quality-test")
    received: list = []

    async def capture(msg: Message):
        received.append(msg)

    bus.subscribe("quality.scored", "test-capture", capture)
    await agent.initialize()
    await agent.start()

    for msg in messages:
        await agent.process_message(msg)

    return received


# ===========================================================================
# QualityScorecard
# ===========================================================================

class TestQualityScorecard:
    def test_to_payload_contains_quality_score(self):
        sc = QualityScorecard(overall=0.85)
        p = sc.to_payload()
        assert p["quality_score"] == pytest.approx(0.85)

    def test_to_payload_quality_score_none_when_no_signal(self):
        sc = QualityScorecard(overall=None, evidence=[{"source": "no_signal"}])
        p = sc.to_payload()
        assert p["quality_score"] is None

    def test_to_payload_includes_dimensions_and_evidence(self):
        sc = QualityScorecard(
            overall=0.9,
            dimensions={"accuracy": 0.95},
            evidence=[{"source": "analysis_fallback"}],
        )
        p = sc.to_payload()
        assert p["dimensions"]["accuracy"] == pytest.approx(0.95)
        assert p["evidence"][0]["source"] == "analysis_fallback"

    def test_default_dimensions_and_evidence_are_empty(self):
        sc = QualityScorecard(overall=0.5)
        assert sc.dimensions == {}
        assert sc.evidence == []


# ===========================================================================
# _normalise_score
# ===========================================================================

class TestNormaliseScore:
    def test_value_in_0_1_unchanged(self):
        assert _normalise_score(0.75) == pytest.approx(0.75)

    def test_zero_unchanged(self):
        assert _normalise_score(0.0) == pytest.approx(0.0)

    def test_one_unchanged(self):
        assert _normalise_score(1.0) == pytest.approx(1.0)

    def test_0_to_100_converted(self):
        assert _normalise_score(85.0) == pytest.approx(0.85)

    def test_100_converted_to_1(self):
        assert _normalise_score(100.0) == pytest.approx(1.0)

    def test_negative_clamped_to_0(self):
        assert _normalise_score(-5.0) == pytest.approx(0.0)

    def test_above_100_clamped_to_1(self):
        assert _normalise_score(150.0) == pytest.approx(1.0)


# ===========================================================================
# QualityAgent – publishes quality.scored with run_id
# ===========================================================================

class TestQualityAgentPublishesWithRunId:
    @pytest.mark.asyncio
    async def test_publishes_quality_scored_topic(self):
        received = await _run_agent(_make_message({"quality_score": 0.9}))
        assert len(received) == 1
        assert received[0].topic == "quality.scored"

    @pytest.mark.asyncio
    async def test_run_id_in_output_metadata(self):
        received = await _run_agent(_make_message({"quality_score": 0.9}))
        assert received[0].metadata.get("run_id") == RUN_ID

    @pytest.mark.asyncio
    async def test_quality_score_in_payload(self):
        received = await _run_agent(_make_message({"quality_score": 0.85}))
        assert received[0].payload["quality_score"] == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_evidence_source_is_analysis_fallback(self):
        received = await _run_agent(_make_message({"quality_score": 0.85}))
        evidence = received[0].payload["evidence"]
        assert any(e["source"] == "analysis_fallback" for e in evidence)

    @pytest.mark.asyncio
    async def test_alias_topic_data_analyzed_accepted(self):
        msg = _make_message({"quality_score": 0.9}, topic="data.analyzed")
        received = await _run_agent(msg)
        assert len(received) == 1
        assert received[0].payload["quality_score"] == pytest.approx(0.9)


# ===========================================================================
# QualityAgent – score derivation from 'score' field
# ===========================================================================

class TestQualityAgentScoreNormalisation:
    @pytest.mark.asyncio
    async def test_score_0_to_100_normalised(self):
        """score=85 should become quality_score=0.85."""
        received = await _run_agent(_make_message({"score": 85}))
        assert received[0].payload["quality_score"] == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_score_0_to_1_kept(self):
        """score=0.75 should remain quality_score=0.75."""
        received = await _run_agent(_make_message({"score": 0.75}))
        assert received[0].payload["quality_score"] == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_score_source_is_score_normalised(self):
        received = await _run_agent(_make_message({"score": 80}))
        evidence = received[0].payload["evidence"]
        assert any(e["source"] == "score_normalised" for e in evidence)

    @pytest.mark.asyncio
    async def test_quality_score_preferred_over_score(self):
        """If both quality_score and score are present, quality_score wins."""
        received = await _run_agent(_make_message({"quality_score": 0.9, "score": 50}))
        assert received[0].payload["quality_score"] == pytest.approx(0.9)
        evidence = received[0].payload["evidence"]
        assert any(e["source"] == "analysis_fallback" for e in evidence)


# ===========================================================================
# QualityAgent – confidence fallback
# ===========================================================================

class TestQualityAgentConfidenceFallback:
    @pytest.mark.asyncio
    async def test_confidence_used_when_no_other_signal(self):
        received = await _run_agent(_make_message({"confidence": 0.7}))
        assert received[0].payload["quality_score"] == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_confidence_source_in_evidence(self):
        received = await _run_agent(_make_message({"confidence": 0.7}))
        evidence = received[0].payload["evidence"]
        assert any(e["source"] == "confidence" for e in evidence)


# ===========================================================================
# QualityAgent – no signal → quality_score None
# ===========================================================================

class TestQualityAgentNoSignal:
    @pytest.mark.asyncio
    async def test_quality_score_none_when_no_signal(self):
        received = await _run_agent(_make_message({}))
        assert received[0].payload["quality_score"] is None

    @pytest.mark.asyncio
    async def test_evidence_source_no_signal(self):
        received = await _run_agent(_make_message({}))
        evidence = received[0].payload["evidence"]
        assert any(e["source"] == "no_signal" for e in evidence)

    @pytest.mark.asyncio
    async def test_still_publishes_when_no_signal(self):
        """Agent must always publish, even without quality signals."""
        received = await _run_agent(_make_message({}))
        assert len(received) == 1
        assert received[0].topic == "quality.scored"


# ===========================================================================
# QualityAgent – missing run_id
# ===========================================================================

class TestQualityAgentMissingRunId:
    @pytest.mark.asyncio
    async def test_publishes_when_run_id_missing(self):
        """Agent must still publish quality.scored even if run_id is absent."""
        msg = Message(
            topic="analysis.completed",
            payload={"quality_score": 0.9},
            sender_id="analysis",
            metadata={},  # no run_id
        )
        received = await _run_agent(msg)
        assert len(received) == 1
        assert received[0].topic == "quality.scored"

    @pytest.mark.asyncio
    async def test_quality_score_none_when_run_id_missing(self):
        msg = Message(
            topic="analysis.completed",
            payload={"quality_score": 0.9},
            sender_id="analysis",
            metadata={},
        )
        received = await _run_agent(msg)
        assert received[0].payload["quality_score"] is None

    @pytest.mark.asyncio
    async def test_metadata_run_id_is_unknown_when_missing(self):
        msg = Message(
            topic="analysis.completed",
            payload={"quality_score": 0.9},
            sender_id="analysis",
            metadata={},
        )
        received = await _run_agent(msg)
        assert received[0].metadata.get("run_id") == "unknown"

    @pytest.mark.asyncio
    async def test_evidence_source_missing_run_id(self):
        msg = Message(
            topic="analysis.completed",
            payload={"quality_score": 0.9},
            sender_id="analysis",
            metadata={},
        )
        received = await _run_agent(msg)
        evidence = received[0].payload["evidence"]
        assert any(e["source"] == "missing_run_id" for e in evidence)


# ===========================================================================
# QualityAgent – requirements_met
# ===========================================================================

class TestQualityAgentRequirementsMet:
    @pytest.mark.asyncio
    async def test_requirements_met_true_when_above_threshold(self):
        msg = _make_message(
            {"quality_score": 0.9, "context": {"requirements": {"min_quality": 0.8}}}
        )
        received = await _run_agent(msg)
        assert received[0].payload["requirements_met"] is True

    @pytest.mark.asyncio
    async def test_requirements_met_false_when_below_threshold(self):
        msg = _make_message(
            {"quality_score": 0.7, "context": {"requirements": {"min_quality": 0.8}}}
        )
        received = await _run_agent(msg)
        assert received[0].payload["requirements_met"] is False

    @pytest.mark.asyncio
    async def test_requirements_met_not_in_payload_when_no_min_quality(self):
        """requirements_met should be absent if no requirements.min_quality in context."""
        received = await _run_agent(_make_message({"quality_score": 0.9}))
        assert "requirements_met" not in received[0].payload

    @pytest.mark.asyncio
    async def test_requirements_met_not_in_payload_when_quality_score_none(self):
        """requirements_met should be absent if quality_score is None."""
        msg = _make_message({"context": {"requirements": {"min_quality": 0.8}}})
        received = await _run_agent(msg)
        assert "requirements_met" not in received[0].payload

    @pytest.mark.asyncio
    async def test_requirements_met_exactly_at_threshold(self):
        msg = _make_message(
            {"quality_score": 0.8, "context": {"requirements": {"min_quality": 0.8}}}
        )
        received = await _run_agent(msg)
        assert received[0].payload["requirements_met"] is True

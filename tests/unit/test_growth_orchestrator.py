"""
Tests for genus.growth.growth_orchestrator (GrowthOrchestrator)

Verifies:
- need.identified → PASS: growth.build.requested published
- need.identified → BLOCK (QualityGate): need.rejected published, reason = "quality_blocked"
- Cooldown active → need.rejected published, reason = "cooldown_active"
- After successful build: cooldown for (domain, need) set
- growth.build.requested payload contains agent_spec_template
- need.rejected payload contains reason and details
- cooldown_same_domain_per_need=True: same domain, different needs → no cooldown conflict
- cooldown_same_domain_per_need=False: same domain → cooldown applies to all needs
"""

from typing import List
from pathlib import Path

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.growth.growth_orchestrator import GrowthOrchestrator
from genus.growth.identity_profile import StabilityRules
from genus.growth.need_record import NeedRecord
from genus.quality.gate import QualityGate, GateResult, GateVerdict
from genus.quality.history import QualityHistory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bus() -> MessageBus:
    return MessageBus()


def _make_rules(**kwargs) -> StabilityRules:
    defaults = dict(
        cooldown_same_domain_s=3600,
        min_trigger_count_before_build=2,
        cooldown_same_domain_per_need=True,
    )
    defaults.update(kwargs)
    return StabilityRules(**defaults)


def _make_need(domain: str = "system", desc: str = "run_failure") -> NeedRecord:
    nr = NeedRecord(domain=domain, need_description=desc)
    nr.status = "queued"
    return nr


def _collect(bus: MessageBus, topic: str) -> List[Message]:
    collected: List[Message] = []

    def _handler(msg: Message) -> None:
        collected.append(msg)

    bus.subscribe(topic, f"__collector_{topic}__", _handler)
    return collected


def _make_orchestrator(
    bus: MessageBus,
    rules: StabilityRules,
    tmp_path: Path,
) -> GrowthOrchestrator:
    gate = QualityGate()
    history = QualityHistory(path=tmp_path / "quality_history.jsonl")
    return GrowthOrchestrator(
        message_bus=bus,
        stability_rules=rules,
        quality_gate=gate,
        quality_history=history,
    )


# ---------------------------------------------------------------------------
# Tests: basic PASS flow
# ---------------------------------------------------------------------------

class TestGrowthOrchestratorPass:
    async def test_pass_publishes_build_requested(self, tmp_path):
        """A need.identified with baseline scores → growth.build.requested published."""
        bus = _make_bus()
        rules = _make_rules()
        orch = _make_orchestrator(bus, rules, tmp_path)
        build_msgs: List[Message] = _collect(bus, "growth.build.requested")
        await orch.initialize()
        need = _make_need()
        await bus.publish(Message(
            topic="need.identified",
            payload=need.to_payload(),
            sender_id="test",
        ))
        assert len(build_msgs) == 1

    async def test_build_requested_payload_has_agent_spec_template(self, tmp_path):
        """growth.build.requested payload contains agent_spec_template."""
        bus = _make_bus()
        rules = _make_rules()
        orch = _make_orchestrator(bus, rules, tmp_path)
        build_msgs: List[Message] = _collect(bus, "growth.build.requested")
        await orch.initialize()
        need = _make_need(domain="family", desc="missing_calendar")
        await bus.publish(Message(
            topic="need.identified",
            payload=need.to_payload(),
            sender_id="test",
        ))
        assert len(build_msgs) == 1
        payload = build_msgs[0].payload
        assert "agent_spec_template" in payload
        tpl = payload["agent_spec_template"]
        assert tpl["name"] == "FamilyAgent"
        assert tpl["description"] == "missing_calendar"
        assert tpl["morphology"]["domain"] == "family"
        assert tpl["morphology"]["replaceable"] is True

    async def test_build_requested_payload_has_gate_fields(self, tmp_path):
        """growth.build.requested payload has gate_verdict and gate_total_score."""
        bus = _make_bus()
        rules = _make_rules()
        orch = _make_orchestrator(bus, rules, tmp_path)
        build_msgs: List[Message] = _collect(bus, "growth.build.requested")
        await orch.initialize()
        need = _make_need()
        await bus.publish(Message(
            topic="need.identified",
            payload=need.to_payload(),
            sender_id="test",
        ))
        payload = build_msgs[0].payload
        assert "gate_verdict" in payload
        assert payload["gate_verdict"] in ("pass", "warn")
        assert "gate_total_score" in payload
        assert isinstance(payload["gate_total_score"], float)


# ---------------------------------------------------------------------------
# Tests: QualityGate BLOCK flow
# ---------------------------------------------------------------------------

class TestGrowthOrchestratorBlock:
    async def test_block_publishes_need_rejected(self, tmp_path):
        """When QualityGate returns BLOCK, need.rejected is published."""
        bus = _make_bus()
        rules = _make_rules()
        history = QualityHistory(path=tmp_path / "quality_history.jsonl")

        # Record a very low score so average_score() < 0.55
        history.record(GateResult(
            verdict=GateVerdict.BLOCK,
            total_score=0.10,
            dimension_scores={},
            failed_dimensions=["test_coverage"],
            reasons=["test_coverage below threshold"],
            run_id="test-run",
            evaluated_at="2026-01-01T00:00:00Z",
        ))

        gate = QualityGate()
        orch = GrowthOrchestrator(
            message_bus=bus,
            stability_rules=rules,
            quality_gate=gate,
            quality_history=history,
        )
        rejected_msgs: List[Message] = _collect(bus, "need.rejected")
        build_msgs: List[Message] = _collect(bus, "growth.build.requested")
        await orch.initialize()
        need = _make_need()
        await bus.publish(Message(
            topic="need.identified",
            payload=need.to_payload(),
            sender_id="test",
        ))
        assert len(rejected_msgs) == 1
        assert len(build_msgs) == 0

    async def test_block_reason_is_quality_blocked(self, tmp_path):
        """need.rejected payload has reason='quality_blocked'."""
        bus = _make_bus()
        rules = _make_rules()
        history = QualityHistory(path=tmp_path / "quality_history.jsonl")
        history.record(GateResult(
            verdict=GateVerdict.BLOCK,
            total_score=0.10,
            dimension_scores={},
            failed_dimensions=["security_compliance"],
            reasons=["security_compliance below hard-block threshold"],
            run_id="test-run",
            evaluated_at="2026-01-01T00:00:00Z",
        ))
        gate = QualityGate()
        orch = GrowthOrchestrator(
            message_bus=bus,
            stability_rules=rules,
            quality_gate=gate,
            quality_history=history,
        )
        rejected_msgs: List[Message] = _collect(bus, "need.rejected")
        await orch.initialize()
        need = _make_need()
        await bus.publish(Message(
            topic="need.identified",
            payload=need.to_payload(),
            sender_id="test",
        ))
        payload = rejected_msgs[0].payload
        assert payload["reason"] == "quality_blocked"
        assert "details" in payload

    async def test_rejected_payload_has_need_fields(self, tmp_path):
        """need.rejected payload contains need_id, domain, need_description."""
        bus = _make_bus()
        rules = _make_rules()
        history = QualityHistory(path=tmp_path / "quality_history.jsonl")
        history.record(GateResult(
            verdict=GateVerdict.BLOCK,
            total_score=0.10,
            dimension_scores={},
            failed_dimensions=["test_coverage"],
            reasons=["test_coverage blocked"],
            run_id="test-run",
            evaluated_at="2026-01-01T00:00:00Z",
        ))
        gate = QualityGate()
        orch = GrowthOrchestrator(
            message_bus=bus,
            stability_rules=rules,
            quality_gate=gate,
            quality_history=history,
        )
        rejected_msgs: List[Message] = _collect(bus, "need.rejected")
        await orch.initialize()
        need = _make_need(domain="quality", desc="low_quality_score")
        await bus.publish(Message(
            topic="need.identified",
            payload=need.to_payload(),
            sender_id="test",
        ))
        payload = rejected_msgs[0].payload
        assert "need_id" in payload
        assert payload["domain"] == "quality"
        assert payload["need_description"] == "low_quality_score"


# ---------------------------------------------------------------------------
# Tests: Cooldown
# ---------------------------------------------------------------------------

class TestGrowthOrchestratorCooldown:
    async def test_cooldown_blocks_second_request(self, tmp_path):
        """A second need.identified for the same need within cooldown → need.rejected."""
        bus = _make_bus()
        rules = _make_rules(cooldown_same_domain_s=9999)
        orch = _make_orchestrator(bus, rules, tmp_path)
        rejected_msgs: List[Message] = _collect(bus, "need.rejected")
        build_msgs: List[Message] = _collect(bus, "growth.build.requested")
        await orch.initialize()
        need = _make_need()
        # First request — should pass
        await bus.publish(Message(
            topic="need.identified",
            payload=need.to_payload(),
            sender_id="test",
        ))
        # Second request — should be in cooldown
        await bus.publish(Message(
            topic="need.identified",
            payload=need.to_payload(),
            sender_id="test",
        ))
        assert len(build_msgs) == 1
        assert len(rejected_msgs) == 1
        assert rejected_msgs[0].payload["reason"] == "cooldown_active"

    async def test_cooldown_reason_is_cooldown_active(self, tmp_path):
        """need.rejected reason is 'cooldown_active' during cooldown."""
        bus = _make_bus()
        rules = _make_rules(cooldown_same_domain_s=9999)
        orch = _make_orchestrator(bus, rules, tmp_path)
        rejected_msgs: List[Message] = _collect(bus, "need.rejected")
        await orch.initialize()
        need = _make_need()
        await bus.publish(Message(
            topic="need.identified",
            payload=need.to_payload(),
            sender_id="test",
        ))
        await bus.publish(Message(
            topic="need.identified",
            payload=need.to_payload(),
            sender_id="test",
        ))
        assert rejected_msgs[0].payload["reason"] == "cooldown_active"

    async def test_cooldown_recorded_after_successful_build(self, tmp_path):
        """After an approved build, the cooldown dict is populated."""
        bus = _make_bus()
        rules = _make_rules(cooldown_same_domain_s=9999, cooldown_same_domain_per_need=True)
        orch = _make_orchestrator(bus, rules, tmp_path)
        await orch.initialize()
        need = _make_need(domain="system", desc="run_failure")
        await bus.publish(Message(
            topic="need.identified",
            payload=need.to_payload(),
            sender_id="test",
        ))
        assert ("system", "run_failure") in orch._cooldowns

    async def test_per_need_cooldown_does_not_block_different_need(self, tmp_path):
        """cooldown_same_domain_per_need=True: different needs in same domain are independent."""
        bus = _make_bus()
        rules = _make_rules(cooldown_same_domain_s=9999, cooldown_same_domain_per_need=True)
        orch = _make_orchestrator(bus, rules, tmp_path)
        build_msgs: List[Message] = _collect(bus, "growth.build.requested")
        await orch.initialize()
        need1 = _make_need(domain="family", desc="calendar_missing")
        need2 = _make_need(domain="family", desc="budget_missing")
        await bus.publish(Message(
            topic="need.identified",
            payload=need1.to_payload(),
            sender_id="test",
        ))
        await bus.publish(Message(
            topic="need.identified",
            payload=need2.to_payload(),
            sender_id="test",
        ))
        # Both should get approved since they are different needs
        assert len(build_msgs) == 2

    async def test_domain_cooldown_blocks_different_need_when_per_need_false(self, tmp_path):
        """cooldown_same_domain_per_need=False: any need in same domain is blocked."""
        bus = _make_bus()
        rules = _make_rules(cooldown_same_domain_s=9999, cooldown_same_domain_per_need=False)
        orch = _make_orchestrator(bus, rules, tmp_path)
        build_msgs: List[Message] = _collect(bus, "growth.build.requested")
        rejected_msgs: List[Message] = _collect(bus, "need.rejected")
        await orch.initialize()
        need1 = _make_need(domain="family", desc="calendar_missing")
        need2 = _make_need(domain="family", desc="budget_missing")
        await bus.publish(Message(
            topic="need.identified",
            payload=need1.to_payload(),
            sender_id="test",
        ))
        await bus.publish(Message(
            topic="need.identified",
            payload=need2.to_payload(),
            sender_id="test",
        ))
        # First passes, second is blocked by domain-level cooldown
        assert len(build_msgs) == 1
        assert len(rejected_msgs) == 1
        assert rejected_msgs[0].payload["reason"] == "cooldown_active"

"""
Growth Orchestrator

Central decision-maker for GENUS self-directed growth.  The GrowthOrchestrator
receives ``need.identified`` events from the ``NeedObserver`` and decides
whether to commission a new agent build or reject the request.

Decision pipeline (all gates must pass):
    1. **KillSwitch check** — if the MessageBus kill-switch is active the
       orchestrator silently skips all actions.
    2. **Cooldown check** — enforces a minimum wait between consecutive build
       attempts for the same ``(domain, need_description)`` pair (or the same
       domain when ``StabilityRules.cooldown_same_domain_per_need`` is
       ``False``).
    3. **QualityGate** — evaluates baseline quality scores drawn from
       ``QualityHistory``.  A BLOCK verdict rejects the need; PASS or WARN
       allow the build to proceed.

Topics subscribed:
    - ``need.identified``

Topics published:
    - ``growth.build.requested`` — when the decision pipeline approves a build.
    - ``need.rejected`` — when a cooldown or quality gate blocks the build.
"""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.growth.identity_profile import StabilityRules
from genus.growth.need_record import NeedRecord
from genus.quality.gate import GateVerdict, QualityGate
from genus.quality.history import QualityHistory

# Topic constants
_TOPIC_NEED_IDENTIFIED = "need.identified"
_TOPIC_BUILD_REQUESTED = "growth.build.requested"
_TOPIC_NEED_REJECTED = "need.rejected"

# Default baseline scores when QualityHistory has no data
_DEFAULT_BASELINE = 0.72
# security_compliance is always a conservative constant
_SECURITY_COMPLIANCE_BASELINE = 0.92


class GrowthOrchestrator(Agent):
    """Orchestrates GENUS growth by evaluating identified needs and commissioning builds.

    The GrowthOrchestrator subscribes to ``need.identified`` events and runs each
    need through a strict decision pipeline.  Only needs that pass all checks
    result in a ``growth.build.requested`` event.

    Args:
        message_bus: The MessageBus to subscribe to and publish on.
        stability_rules: The :class:`~genus.growth.identity_profile.StabilityRules`
            governing cooldown periods.
        quality_gate: The :class:`~genus.quality.gate.QualityGate` used to
            evaluate baseline quality scores.
        quality_history: The :class:`~genus.quality.history.QualityHistory` used
            to derive baseline scores.
        agent_id: Optional custom agent ID.  Auto-generated if not provided.
        name: Optional human-readable agent name.  Defaults to
            ``"GrowthOrchestrator"``.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        stability_rules: StabilityRules,
        quality_gate: QualityGate,
        quality_history: QualityHistory,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name or "GrowthOrchestrator")
        self._bus = message_bus
        self._stability_rules = stability_rules
        self._quality_gate = quality_gate
        self._quality_history = quality_history
        # (domain, need_description OR "") → timestamp of last approved build
        self._cooldowns: Dict[Tuple[str, str], float] = {}

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Subscribe to ``need.identified``."""
        self._bus.subscribe(_TOPIC_NEED_IDENTIFIED, self.id, self.process_message)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Transition to RUNNING state."""
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        """Unsubscribe from all topics and transition to STOPPED state."""
        self._bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def process_message(self, message: Message) -> None:
        """Handle an incoming ``need.identified`` event.

        Runs the full decision pipeline and publishes either
        ``growth.build.requested`` or ``need.rejected``.

        Args:
            message: The incoming MessageBus message.
        """
        # KillSwitch check — bail out silently if the bus is shut down
        if self._is_killed():
            return

        if message.topic != _TOPIC_NEED_IDENTIFIED:
            return

        payload = message.payload if isinstance(message.payload, dict) else {}
        need = NeedRecord(
            need_id=payload.get("need_id", ""),
            domain=payload.get("domain", ""),
            need_description=payload.get("need_description", ""),
            trigger_count=payload.get("trigger_count", 0),
            first_seen_at=payload.get("first_seen_at", ""),
            last_seen_at=payload.get("last_seen_at", ""),
            status=payload.get("status", "queued"),
            source_topics=list(payload.get("source_topics", [])),
            metadata=dict(payload.get("metadata", {})),
        )

        # 1) Cooldown check
        if self._is_in_cooldown(need):
            await self._publish_rejected(
                need,
                reason="cooldown_active",
                details="Cooldown period has not expired for this need.",
            )
            return

        # 2) QualityGate check
        scores = self._build_baseline_scores()
        gate_result = self._quality_gate.evaluate(scores)

        if gate_result.verdict == GateVerdict.BLOCK:
            need.status = "quality_blocked"
            details = gate_result.reasons[0] if gate_result.reasons else "Quality gate blocked."
            await self._publish_rejected(need, reason="quality_blocked", details=details)
            return

        # All checks passed — approve the build
        self._record_cooldown(need)
        await self._publish_build_requested(need, gate_result.verdict, gate_result.total_score)

    # ------------------------------------------------------------------
    # Cooldown management
    # ------------------------------------------------------------------

    def _is_in_cooldown(self, need: NeedRecord) -> bool:
        """Return ``True`` if the cooldown period for this need is still active.

        Args:
            need: The need being evaluated.

        Returns:
            ``True`` when the cooldown has not yet expired.
        """
        if self._stability_rules.cooldown_same_domain_per_need:
            key: Tuple[str, str] = (need.domain, need.need_description)
        else:
            key = (need.domain, "")
        last_build = self._cooldowns.get(key)
        if last_build is None:
            return False
        return (time.time() - last_build) < self._stability_rules.cooldown_same_domain_s

    def _record_cooldown(self, need: NeedRecord) -> None:
        """Record the current timestamp as the last approved build for this need.

        Args:
            need: The need for which a build was approved.
        """
        if self._stability_rules.cooldown_same_domain_per_need:
            key: Tuple[str, str] = (need.domain, need.need_description)
        else:
            key = (need.domain, "")
        self._cooldowns[key] = time.time()

    # ------------------------------------------------------------------
    # Quality baseline
    # ------------------------------------------------------------------

    def _build_baseline_scores(self) -> Dict[str, float]:
        """Build a dict of baseline quality scores for the QualityGate.

        The baseline is derived from the average score in ``QualityHistory``
        when data is available, falling back to ``_DEFAULT_BASELINE`` (0.72)
        for all dimensions.  ``security_compliance`` is always set to the
        conservative ``_SECURITY_COMPLIANCE_BASELINE`` (0.92).

        Returns:
            A dict mapping dimension names to scores.
        """
        base = self._quality_history.average_score()
        if base is None:
            base = _DEFAULT_BASELINE
        return {
            "test_coverage": base,
            "security_compliance": _SECURITY_COMPLIANCE_BASELINE,
            "complexity_score": base,
            "feedback_history": base,
            "stability_score": base,
        }

    # ------------------------------------------------------------------
    # Publishing helpers
    # ------------------------------------------------------------------

    async def _publish_build_requested(
        self,
        need: NeedRecord,
        verdict: GateVerdict,
        total_score: float,
    ) -> None:
        """Publish ``growth.build.requested``.

        Args:
            need: The approved NeedRecord.
            verdict: The QualityGate verdict (PASS or WARN).
            total_score: The QualityGate total score.
        """
        domain = need.domain
        payload = {
            "need_id": need.need_id,
            "domain": domain,
            "need_description": need.need_description,
            "gate_verdict": verdict.value,
            "gate_total_score": total_score,
            "agent_spec_template": {
                "name": f"{domain.title()}Agent",
                "description": need.need_description,
                "morphology": {
                    "layer": "growth",
                    "domain": domain,
                    "replaceable": True,
                    "singleton": False,
                    "max_instances": 1,
                },
            },
        }
        await self._bus.publish(
            Message(
                topic=_TOPIC_BUILD_REQUESTED,
                payload=payload,
                sender_id=self.id,
            )
        )

    async def _publish_rejected(
        self,
        need: NeedRecord,
        reason: str,
        details: str,
    ) -> None:
        """Publish ``need.rejected``.

        Args:
            need: The rejected NeedRecord.
            reason: Machine-readable rejection reason.
            details: Human-readable explanation.
        """
        payload = {
            "need_id": need.need_id,
            "domain": need.domain,
            "need_description": need.need_description,
            "reason": reason,
            "details": details,
        }
        await self._bus.publish(
            Message(
                topic=_TOPIC_NEED_REJECTED,
                payload=payload,
                sender_id=self.id,
            )
        )

    # ------------------------------------------------------------------
    # Kill-switch helper
    # ------------------------------------------------------------------

    def _is_killed(self) -> bool:
        """Return ``True`` if the MessageBus kill-switch is active.

        Checks ``self._bus._kill_switch`` when present and calls
        ``assert_not_active()`` to determine whether publication is still
        permitted.  Falls back to ``False`` (permissive) when no kill-switch
        is attached.

        Returns:
            ``True`` when the kill-switch is active and the bus is shut down.
        """
        ks = getattr(self._bus, "_kill_switch", None)
        if ks is None:
            return False
        try:
            ks.assert_not_active()
            return False
        except Exception:
            return True

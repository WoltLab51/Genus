"""
Decision Agent

Contains the legacy SimpleDecisionAgent (kept for backward compatibility) and
the new clean-architecture DecisionAgent that implements GENUS-generic decision
semantics: accept | retry | replan | escalate | delegate.
"""

import random
from typing import Any, Dict, Optional

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.core.logger import Logger
from genus.core.memory import Memory
from genus.core.run import get_run_id


# ---------------------------------------------------------------------------
# Legacy SimpleDecisionAgent (BUY/WAIT) – kept for backward compatibility
# ---------------------------------------------------------------------------

_BUY_THRESHOLD = 50
_MIN_EXPLORATION_RATE = 0.1
_MAX_EXPLORATION_RATE = 0.9

# Map classification labels to numeric scores for backward compatibility
_CLASSIFICATION_SCORES = {"high": 80, "normal": 50, "low": 20}


def _compute_exploration_rate(good_ratio: float) -> float:
    """Return exploration rate derived from good_ratio.

    High good_ratio → less exploration (more exploitation).
    Low good_ratio  → more exploration.
    Result is clamped to [_MIN_EXPLORATION_RATE, _MAX_EXPLORATION_RATE].
    """
    rate = 1.0 - good_ratio
    return max(_MIN_EXPLORATION_RATE, min(_MAX_EXPLORATION_RATE, rate))


class SimpleDecisionAgent:
    def __init__(self, name, bus):
        self.name = name
        self.bus = bus

    async def handle_message(self, message):
        stats = Memory.get_stats()
        good_ratio = stats.get("good_ratio", 0.5)
        exploration_rate = _compute_exploration_rate(good_ratio)

        Logger.log(self.name, "making decision", {
            "input": message.payload,
            "good_ratio": good_ratio,
            "exploration_rate": round(exploration_rate, 2),
        })

        # Resolve score: use explicit 'score' if present, else derive from 'classification'
        payload = message.payload
        if "score" in payload:
            score = payload["score"]
        else:
            classification = payload.get("classification", "normal")
            score = _CLASSIFICATION_SCORES.get(classification, 50)

        # Exploration vs exploitation
        if random.random() < exploration_rate:
            decision = random.choice(["BUY", "WAIT"])
            reason = "explore"
        else:
            decision = "BUY" if score >= _BUY_THRESHOLD else "WAIT"
            reason = "exploit"

        Logger.log(
            self.name,
            f"decision = {decision} (reason={reason}, exploration_rate={exploration_rate:.2f})",
        )

        new_message = Message(
            topic="decision.made",
            payload={"decision": decision, "action": decision, "reason": reason},
            sender_id=self.name,
        )

        await self.bus.publish(new_message)


# ---------------------------------------------------------------------------
# New DecisionAgent – GENUS-generic decision semantics
# ---------------------------------------------------------------------------

_DEFAULT_MIN_QUALITY: float = 0.8
_DEFAULT_MAX_RETRIES: int = 3
_RETRY_MARGIN: float = 0.05

# Recognised input topics
_TOPIC_ANALYSIS = "analysis.completed"
_TOPIC_ANALYSIS_ALIAS = "data.analyzed"   # temporary backward-compat alias
_TOPIC_QUALITY = "quality.scored"
_TOPIC_DECISION = "decision.made"


class DecisionAgent(Agent):
    """GENUS-generic decision agent.

    Subscribes to ``analysis.completed`` (and the alias ``data.analyzed``)
    and ``quality.scored``.  For each ``run_id`` it caches the latest
    evidence and emits ``decision.made`` with one of::

        accept | retry | replan | escalate | delegate

    Decision policy (in priority order):

    1. **Delegate overlay** – ``context["needs_expert"] == True``
    2. **Missing quality** – no quality evidence available → ``replan``
    3. **Critical gate** – ``is_critical`` and no explicit ``min_quality``
       in context → ``escalate``
    4. **Accept** – ``quality_score >= min_quality``
    5. **Retry** – quality within retry margin and attempt budget available
    6. **Escalate by budget** – attempt >= max_retries
    7. **Replan** – default fallback

    ``is_critical`` is ``True`` when ``context["critical"] == True`` OR
    ``context["risk"] == "high"``.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        default_min_quality: float = _DEFAULT_MIN_QUALITY,
        default_max_retries: int = _DEFAULT_MAX_RETRIES,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name or "DecisionAgent")
        self._bus = message_bus
        self._default_min_quality = default_min_quality
        self._default_max_retries = default_max_retries

        # Per-run_id evidence cache
        self._last_analysis: Dict[str, Dict[str, Any]] = {}
        self._last_quality: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Subscribe to input topics."""
        self._bus.subscribe(_TOPIC_ANALYSIS, self.id, self.process_message)
        self._bus.subscribe(_TOPIC_ANALYSIS_ALIAS, self.id, self.process_message)
        self._bus.subscribe(_TOPIC_QUALITY, self.id, self.process_message)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        self._bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def process_message(self, message: Message) -> None:
        """Handle an incoming analysis or quality message."""
        run_id = get_run_id(message)
        if run_id is None:
            await self._publish_decision(
                run_id="unknown",
                decision="escalate",
                reason="missing run_id",
                requirements_met=False,
                min_quality=self._default_min_quality,
                quality_score=None,
                risk="normal",
                critical=False,
                attempt=0,
                max_retries=self._default_max_retries,
                confidence=0.0,
                evidence_source="none",
                original_metadata=message.metadata,
            )
            return

        topic = message.topic
        payload = message.payload or {}

        if topic in (_TOPIC_ANALYSIS, _TOPIC_ANALYSIS_ALIAS):
            self._last_analysis[run_id] = payload
        elif topic == _TOPIC_QUALITY:
            self._last_quality[run_id] = payload

        # Attempt to make a decision with current evidence
        context = payload.get("context") if isinstance(payload, dict) else None
        await self._decide(run_id=run_id, context=context, message_metadata=message.metadata)

    # ------------------------------------------------------------------
    # Decision logic
    # ------------------------------------------------------------------

    async def _decide(
        self,
        run_id: str,
        context: Dict[str, Any],
        message_metadata: Dict[str, Any],
    ) -> None:
        """Evaluate cached evidence and publish a decision."""
        # --- Quality source (QM preferred over analysis fallback) ---
        quality_score: Optional[float] = None
        evidence_source = "none"

        qm_payload = self._last_quality.get(run_id)
        if qm_payload is not None:
            quality_score = qm_payload.get("quality_score")
            if quality_score is not None:
                evidence_source = "qm"

        if quality_score is None:
            analysis_payload = self._last_analysis.get(run_id)
            if analysis_payload is not None:
                quality_score = analysis_payload.get("quality_score")
                if quality_score is not None:
                    evidence_source = "analysis"
                # Inherit context from analysis payload only when none was provided
                if context is None:
                    context = analysis_payload.get("context", {})

        # Normalise context to a dict once so later lookups are safe
        if not isinstance(context, dict):
            context = {}

        # --- Context resolution ---
        requirements: Dict[str, Any] = context.get("requirements", {})
        if not isinstance(requirements, dict):
            requirements = {}
        limits: Dict[str, Any] = context.get("limits", {})
        if not isinstance(limits, dict):
            limits = {}

        has_explicit_min_quality = "min_quality" in requirements
        min_quality: float = (
            requirements["min_quality"] if has_explicit_min_quality
            else self._default_min_quality
        )
        max_retries: int = limits.get("max_retries", self._default_max_retries)
        attempt: int = context.get("attempt", 0)

        risk: str = context.get("risk", "normal")
        critical_flag: bool = bool(context.get("critical", False))
        is_critical = critical_flag or (risk == "high")

        needs_expert: bool = bool(context.get("needs_expert", False))

        # --- Decision rules (in priority order) ---
        decision: str
        reason: str
        requirements_met = False
        confidence: float = 0.0

        # 1) Delegate overlay
        if needs_expert:
            decision = "delegate"
            reason = "explicit expert required"

        # 2) Missing quality evidence
        elif quality_score is None:
            decision = "replan"
            reason = "no quality evidence available"

        # 3) Critical gate
        elif is_critical and not has_explicit_min_quality:
            decision = "escalate"
            reason = "critical/high-risk without explicit requirements"

        # 4) Accept
        elif quality_score >= min_quality:
            decision = "accept"
            reason = "quality meets requirements"
            requirements_met = True
            confidence = 0.9 if evidence_source == "qm" else 0.7

        # 5) Retry (within margin, budget available)
        elif quality_score >= min_quality - _RETRY_MARGIN and attempt < max_retries:
            decision = "retry"
            reason = "quality just below threshold, retry budget available"

        # 6) Escalate by budget exhaustion
        elif attempt >= max_retries:
            decision = "escalate"
            reason = "retry budget exhausted"

        # 7) Replan (default)
        else:
            decision = "replan"
            reason = "quality below threshold"

        await self._publish_decision(
            run_id=run_id,
            decision=decision,
            reason=reason,
            requirements_met=requirements_met,
            min_quality=min_quality,
            quality_score=quality_score,
            risk=risk,
            critical=is_critical,
            attempt=attempt,
            max_retries=max_retries,
            confidence=confidence,
            evidence_source=evidence_source,
            original_metadata=message_metadata,
        )

    async def _publish_decision(
        self,
        run_id: str,
        decision: str,
        reason: str,
        requirements_met: bool,
        min_quality: float,
        quality_score: Optional[float],
        risk: str,
        critical: bool,
        attempt: int,
        max_retries: int,
        confidence: float,
        evidence_source: str,
        original_metadata: Dict[str, Any],
    ) -> None:
        """Publish a ``decision.made`` message."""
        metadata = dict(original_metadata)
        metadata["run_id"] = run_id

        msg = Message(
            topic=_TOPIC_DECISION,
            payload={
                "run_id": run_id,
                "decision": decision,
                "requirements_met": requirements_met,
                "min_quality": min_quality,
                "quality_score": quality_score,
                "risk": risk,
                "critical": critical,
                "attempt": attempt,
                "max_retries": max_retries,
                "reason": reason,
                "confidence": confidence,
                "evidence": [{"source": evidence_source}],
            },
            sender_id=self.id,
            metadata=metadata,
        )
        await self._bus.publish(msg)
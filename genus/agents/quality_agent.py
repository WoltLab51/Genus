"""
Quality Agent

Subscribes to ``analysis.completed`` (and the legacy alias ``data.analyzed``)
and publishes ``quality.scored`` events containing a :class:`QualityScorecard`.

Score derivation (deterministic, in priority order):

1. ``payload["quality_score"]``  numeric  → used as-is; source = ``analysis_fallback``
2. ``payload["score"]``          numeric  → normalised to [0, 1]:
   - value in (1, 100] → divided by 100
   - value in [0, 1]   → kept as-is
   - otherwise         → clamped to [0, 1]
   source = ``score_normalised``
3. ``payload["confidence"]``     numeric in [0, 1] → used as-is; source = ``confidence``
4. No recognisable signal        → ``quality_score = None``; source = ``no_signal``

If ``run_id`` is missing from ``message.metadata``, a ``quality.scored``
message with ``quality_score=None`` is still published (so that downstream
components remain unblocked) and the evidence records the missing run_id.
The output metadata carries ``run_id="unknown"`` in that case.

If the incoming payload carries a ``context.requirements.min_quality`` value
and ``quality_score`` is not ``None``, ``requirements_met`` is added to the
published payload.
"""

import logging
from typing import Any, Dict, Optional

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.core.run import get_run_id
from genus.quality.scorecard import QualityScorecard

logger = logging.getLogger(__name__)

_TOPIC_ANALYSIS = "analysis.completed"
_TOPIC_ANALYSIS_ALIAS = "data.analyzed"
_TOPIC_OUTPUT = "quality.scored"


def _normalise_score(raw: float) -> float:
    """Normalise *raw* to the range [0.0, 1.0].

    - If *raw* is in (1.0, 100.0] it is assumed to be a 0–100 percentage and
      is divided by 100.
    - If *raw* is already in [0.0, 1.0] it is returned unchanged.
    - Any other value (negative or > 100) is clamped to [0.0, 1.0].
    """
    if 0.0 <= raw <= 1.0:
        return raw
    if 1.0 < raw <= 100.0:
        return raw / 100.0
    # Clamp out-of-range values
    return max(0.0, min(1.0, raw))


def _derive_scorecard(payload: Dict[str, Any]) -> QualityScorecard:
    """Derive a :class:`QualityScorecard` from an analysis *payload*.

    The derivation follows the priority order documented in the module
    docstring.
    """
    # 1) Explicit quality_score
    if "quality_score" in payload:
        val = payload["quality_score"]
        if isinstance(val, (int, float)):
            return QualityScorecard(
                overall=float(val),
                evidence=[{"source": "analysis_fallback", "field": "quality_score"}],
            )

    # 2) score (normalise)
    if "score" in payload:
        val = payload["score"]
        if isinstance(val, (int, float)):
            normalised = _normalise_score(float(val))
            return QualityScorecard(
                overall=normalised,
                evidence=[
                    {
                        "source": "score_normalised",
                        "field": "score",
                        "raw": float(val),
                        "normalised": normalised,
                    }
                ],
            )

    # 3) confidence  –  confidence is always a ratio in [0, 1] by convention,
    #    so we only clamp (not convert from 0-100 like `score`).
    if "confidence" in payload:
        val = payload["confidence"]
        if isinstance(val, (int, float)):
            clamped = max(0.0, min(1.0, float(val)))
            return QualityScorecard(
                overall=clamped,
                evidence=[{"source": "confidence", "field": "confidence"}],
            )

    # 4) No signal
    return QualityScorecard(
        overall=None,
        evidence=[{"source": "no_signal", "note": "no recognisable quality signal in payload"}],
    )


class QualityAgent(Agent):
    """Minimal quality/evaluation agent.

    Listens for ``analysis.completed`` (and the legacy alias
    ``data.analyzed``) messages, derives a quality score from the payload,
    and publishes a ``quality.scored`` event.

    This agent is the preferred evidence source for ``DecisionAgent``
    (which prefers ``quality.scored`` over inline ``quality_score`` in
    analysis payloads).
    """

    def __init__(
        self,
        message_bus: MessageBus,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name or "QualityAgent")
        self._bus = message_bus

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Subscribe to analysis topics."""
        self._bus.subscribe(_TOPIC_ANALYSIS, self.id, self.process_message)
        self._bus.subscribe(_TOPIC_ANALYSIS_ALIAS, self.id, self.process_message)
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
        """Derive quality score and publish ``quality.scored``."""
        run_id = get_run_id(message)
        payload = message.payload if isinstance(message.payload, dict) else {}

        if run_id is None:
            logger.warning(
                "QualityAgent received message without run_id (message_id=%s); "
                "publishing quality.scored with quality_score=None",
                message.message_id,
            )
            scorecard = QualityScorecard(
                overall=None,
                evidence=[{"source": "missing_run_id", "note": "run_id absent from message metadata"}],
            )
            await self._publish(scorecard, run_id="unknown", context={}, original_metadata=message.metadata)
            return

        scorecard = _derive_scorecard(payload)
        context = payload.get("context") if isinstance(payload, dict) else {}
        if not isinstance(context, dict):
            context = {}

        await self._publish(scorecard, run_id=run_id, context=context, original_metadata=message.metadata)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def _publish(
        self,
        scorecard: QualityScorecard,
        run_id: str,
        context: Dict[str, Any],
        original_metadata: Dict[str, Any],
    ) -> None:
        """Build and publish the ``quality.scored`` message."""
        out_payload = scorecard.to_payload()

        # requirements_met (only when we have a score and explicit min_quality)
        requirements: Dict[str, Any] = context.get("requirements", {}) if context else {}
        if isinstance(requirements, dict) and "min_quality" in requirements and scorecard.overall is not None:
            out_payload["requirements_met"] = scorecard.overall >= requirements["min_quality"]

        metadata = dict(original_metadata)
        metadata["run_id"] = run_id

        msg = Message(
            topic=_TOPIC_OUTPUT,
            payload=out_payload,
            sender_id=self.id,
            metadata=metadata,
        )
        await self._bus.publish(msg)

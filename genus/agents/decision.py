"""
Decision Agent

Subscribes to ``data.analyzed`` events (during ``initialize()``).
Produces a recommendation string and priority, then publishes
``decision.made``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import MessageBus, Message
from genus.storage.memory import MemoryStore


class DecisionAgent(Agent):
    """Selects relevant outputs for the user based on analysis results."""

    def __init__(
        self,
        message_bus: MessageBus,
        memory: MemoryStore,
        *,
        agent_id: str = "decision",
        name: str = "Decision Agent",
    ) -> None:
        super().__init__(agent_id=agent_id, name=name)
        self._bus = message_bus
        self._memory = memory
        self._decisions: List[Dict[str, Any]] = []

    # -- lifecycle -------------------------------------------------------------

    async def initialize(self) -> None:
        self._bus.subscribe("data.analyzed", self._on_data_analyzed)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        self._bus.unsubscribe("data.analyzed", self._on_data_analyzed)
        self._transition_state(AgentState.STOPPED)

    # -- event handler ---------------------------------------------------------

    async def _on_data_analyzed(self, message: Message) -> None:
        result = message.payload.get("result")
        if result:
            await self.execute({"analysis_result": result})

    # -- core logic ------------------------------------------------------------

    async def execute(self, payload: Any = None) -> Dict[str, Any]:
        payload = payload or {}
        analysis: Optional[Dict[str, Any]] = payload.get("analysis_result")

        if analysis is None:
            analysis = self._memory.get("analysis", "last_result")
        if analysis is None:
            analysis = {
                "summary": "No analysis available.",
                "insights": [],
                "confidence": 0.0,
            }

        confidence: float = analysis.get("confidence", 0.0)
        recommendation = self._decide(analysis)
        priority = self._calculate_priority(confidence)

        decision: Dict[str, Any] = {
            "analysis_result": analysis,
            "recommendation": recommendation,
            "priority": priority,
        }
        self._decisions.append(decision)
        self._memory.set("decision", "last_decision", decision)
        await self._bus.publish_event(
            "decision.made",
            {"decision": decision},
            sender=self.id,
        )
        return decision

    @staticmethod
    def _decide(result: Dict[str, Any]) -> str:
        confidence = result.get("confidence", 0.0)
        summary = result.get("summary", "")
        if confidence >= 0.8:
            return f"High confidence ({confidence:.0%}): {summary} Act on these insights."
        if confidence >= 0.5:
            return f"Moderate confidence ({confidence:.0%}): {summary} Review insights before acting."
        return "Low confidence: Insufficient data. Collect more data before making decisions."

    @staticmethod
    def _calculate_priority(confidence: float) -> int:
        if confidence >= 0.8:
            return 1
        if confidence >= 0.6:
            return 2
        if confidence >= 0.4:
            return 3
        return 4

    def get_decisions(self) -> List[Dict[str, Any]]:
        return list(self._decisions[-20:])
